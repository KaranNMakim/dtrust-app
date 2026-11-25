"""FastAPI service. All routes under /api/v1 (PRD section 6).

Run:  uvicorn app.main:app --reload
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from . import __version__
from . import exports as exporter
from .ask import ask as run_ask
from .calibration import calibrate
from .extractors import extract_dbt, extract_powerbi, extract_tableau
from .migration import plan as migration_plan
from .explain import explain as explain_issue, impact_for
from .reconcile import reconcile as run_reconcile
from .config import settings
from .engine import ActionError, TrustEngine, conflict_dict, score_dict
from .llm import ClaudeGateway
from .store import Store
from .humanize import HumanizedRoute
from .tenancy import (apply_extract, apply_ingest, bind_user, charge, current_email, current_workspace, engine, llm,
                      own_data_only, paid_action, record, user_ask_log)

log = logging.getLogger("decision_trust")
logging.basicConfig(level=logging.INFO)

neo4j_graph = None  # Neo4j projection is single-tenant; per-user workspaces use the in-memory graph



router = APIRouter(dependencies=[Depends(bind_user)], route_class=HumanizedRoute)


def problem(status: int, title: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"type": "about:blank", "title": title, "status": status, "detail": detail})


def actor() -> str:
    return current_email()


def _sync_graph() -> None:
    if neo4j_graph:
        try:
            neo4j_graph.sync(engine.graph)
        except Exception as exc:  # noqa: BLE001
            log.warning("Neo4j sync failed: %s", exc)


# ---------------------------------------------------------------- health & index

@router.get("/api/v1/health")
def health():
    return {"status": "ok", "version": __version__, "claude": llm.enabled, "neo4j": neo4j_graph is not None,
            "metrics": len(engine.store.metrics), "workspace": current_workspace()}


@router.get("/api/v1/index")
def index():
    return engine.index()


# ---------------------------------------------------------------- metrics

@router.get("/api/v1/metrics")
def list_metrics(zone: str | None = None, certification: str | None = None, team: str | None = None,
                 q: str | None = None):
    rows = [engine.metric_detail(mid) for mid in engine.store.metrics]
    if zone:
        rows = [r for r in rows if r["zone"] == zone]
    if certification:
        rows = [r for r in rows if r["certification"] == certification]
    if team:
        rows = [r for r in rows if (r["team"] or "").lower() == team.lower()]
    if q:
        rows = [r for r in rows if q.lower() in (r["name"] + r["formula"]).lower()]
    for r in rows:
        r["used_in"] = len(engine.store.consumers(r["id"]))
    return sorted(rows, key=lambda r: -r["trust_score"])


def _metric_or_404(metric_id: str) -> None:
    if metric_id not in engine.store.metrics:
        raise problem(404, "Metric not found", metric_id)


@router.get("/api/v1/metrics/{metric_id}")
def get_metric(metric_id: str):
    _metric_or_404(metric_id)
    return engine.metric_detail(metric_id)


@router.get("/api/v1/metrics/{metric_id}/score")
def metric_score(metric_id: str):
    _metric_or_404(metric_id)
    return score_dict(engine.metric_scores[metric_id], engine.store)


@router.get("/api/v1/metrics/{metric_id}/score/history")
def metric_history(metric_id: str):
    _metric_or_404(metric_id)
    return engine.history.get(metric_id, [])


@router.get("/api/v1/metrics/{metric_id}/lineage")
def metric_lineage(metric_id: str):
    _metric_or_404(metric_id)
    return engine.metric_lineage(metric_id)


@router.get("/api/v1/metrics/{metric_id}/usage")
def metric_usage(metric_id: str):
    _metric_or_404(metric_id)
    return engine.metric_usage(metric_id)


class ActionBody(BaseModel):
    reason: str | None = None


class DeprecateBody(ActionBody):
    replacement_id: str | None = None


class OwnerBody(BaseModel):
    owner_email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+$")


def _act(fn, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
    except KeyError as exc:
        raise problem(404, "Not found", str(exc)) from exc
    except ActionError as exc:
        raise problem(422, "Action not allowed", str(exc)) from exc
    _sync_graph()
    record("action", {"method": fn.__name__, "args": list(args), "kwargs": kwargs})
    return out


@router.post("/api/v1/metrics/{metric_id}/certify")
def certify(metric_id: str, body: ActionBody, who: str = Depends(actor)):
    return _act(engine.certify, metric_id, who, body.reason)


@router.post("/api/v1/metrics/{metric_id}/deprecate")
def deprecate(metric_id: str, body: DeprecateBody, who: str = Depends(actor)):
    return _act(engine.deprecate, metric_id, who, body.reason, body.replacement_id)


@router.post("/api/v1/metrics/{metric_id}/owner")
def assign_owner(metric_id: str, body: OwnerBody, who: str = Depends(actor)):
    return _act(engine.assign_owner, metric_id, body.owner_email, who)


class RenameBody(BaseModel):
    term: str = Field(..., min_length=2, max_length=80)
    definition: str = Field(..., min_length=5)
    new_name: str | None = None


@router.post("/api/v1/metrics/{metric_id}/rename-term")
def rename_term(metric_id: str, body: RenameBody, who: str = Depends(actor)):
    """Give a divergent variant its own business term (e.g. Bookings) instead of deprecating it."""
    return _act(engine.rename_variant, metric_id, body.term, body.definition, who, body.new_name)


@router.get("/api/v1/metrics/{metric_id}/export")
def export_metric(metric_id: str, format: Literal["dbt", "databricks"] = "dbt", uid: str | None = Depends(paid_action)):
    _metric_or_404(metric_id)
    out = exporter.export(engine.store, metric_id, format)
    charge(uid, "export", f"{engine.store.name_of(metric_id)} ({format})")
    return out


# ---------------------------------------------------------------- dashboards & reconciliation

@router.get("/api/v1/dashboards")
def list_dashboards():
    sm = engine.score_map()
    return [{"id": d.id, "name": d.name, "tool": d.tool, "audience": d.audience,
             "monthly_viewers": d.monthly_viewers, "metric_ids": d.metric_ids,
             "local_overrides": d.local_overrides, "trust_score": sm.get(d.id, {}).get("score"),
             "zone": sm.get(d.id, {}).get("zone")} for d in engine.store.dashboards.values()]


@router.get("/api/v1/reconcile")
def reconcile(a: str, b: str, dashboard_a: str | None = None, dashboard_b: str | None = None,
              period: str | None = None, uid: str | None = Depends(paid_action)):
    """Why do two numbers disagree? Causes by category plus a numeric bridge when component values exist."""
    try:
        out = run_reconcile(engine.store, a, b, dashboard_a or None, dashboard_b or None, period)
        charge(uid, "reconcile", f"{engine.store.name_of(a)} vs {engine.store.name_of(b)}")
        return out
    except KeyError as exc:
        raise problem(404, "Not found", f"{exc.args[0]} isn't in this workspace") from exc
    except ValueError as exc:
        raise problem(422, "Cannot reconcile", str(exc)) from exc


# ---------------------------------------------------------------- calibration

@router.get("/api/v1/calibration")
def calibration():
    return calibrate(engine)


class WeightsBody(BaseModel):
    weights: dict[str, float] | None = None  # null = reset to defaults


@router.post("/api/v1/calibration/apply")
def apply_weights(body: WeightsBody, who: str = Depends(actor)):
    weights = body.weights if body.weights is not None else None
    out = _act(engine.set_weights, weights, who)
    return {**out, "weights": engine.weights, "scoring_version": engine.scoring_version}


@router.get("/api/v1/incidents")
def incidents():
    return [{"date": i.date, "metric_id": i.metric_id, "metric": engine.store.name_of(i.metric_id),
             "type": i.type, "severity": i.severity, "note": i.note} for i in engine.store.incidents]


# ---------------------------------------------------------------- recommendations

@router.get("/api/v1/recommendations")
def list_recommendations():
    out = []
    for rid, ts in engine.rec_scores.items():
        r = engine.store.recommendations[rid]
        out.append({"id": rid, "title": r.title, "model": f"{r.model} {r.version}".strip(),
                    "model_confidence": r.raw_confidence, "trust_score": ts.score, "zone": ts.zone,
                    "explanation": ts.explanation})
    return sorted(out, key=lambda x: x["trust_score"])


@router.get("/api/v1/recommendations/{rec_id}/score")
def rec_score(rec_id: str):
    if rec_id not in engine.rec_scores:
        raise problem(404, "Recommendation not found", rec_id)
    return score_dict(engine.rec_scores[rec_id], engine.store)


class OutcomeBody(BaseModel):
    accepted: bool
    outcome_success: bool | None = None


@router.post("/api/v1/recommendations/{rec_id}/outcome")
def rec_outcome(rec_id: str, body: OutcomeBody, who: str = Depends(actor)):
    return _act(engine.log_outcome, rec_id, body.accepted, body.outcome_success, who)


# ---------------------------------------------------------------- conflicts

@router.get("/api/v1/conflicts")
def list_conflicts(code: str | None = None, status: str | None = "open", severity: str | None = None):
    rows = engine.conflicts
    if code:
        rows = [c for c in rows if c.code == code]
    if status:
        rows = [c for c in rows if c.status == status]
    if severity:
        rows = [c for c in rows if c.severity == severity]
    return [{**conflict_dict(c), "impact": impact_for(engine, c)} for c in rows]


class ConflictPatch(BaseModel):
    status: Literal["open", "resolved", "dismissed"]
    note: str | None = None


@router.get("/api/v1/conflicts/{conflict_id}/plan")
def conflict_plan(conflict_id: str):
    try:
        return migration_plan(engine, conflict_id)
    except KeyError as exc:
        raise problem(404, "Conflict not found", conflict_id) from exc


@router.get("/api/v1/conflicts/{conflict_id}/explain")
def conflict_explain(conflict_id: str):
    """Plain-language explanation of an issue: what, where from, why it matters, what a fix changes."""
    try:
        return explain_issue(engine, conflict_id)
    except KeyError as exc:
        raise problem(404, "Issue not found", "That issue no longer exists. It may already be fixed.") from exc


class VariantChoice(BaseModel):
    metric_id: str
    action: Literal["rename", "retire"]
    term: str | None = None
    definition: str | None = None
    new_name: str | None = None


class ChecklistItem(BaseModel):
    title: str
    owner: str | None = None
    done: bool = False


class FixBody(BaseModel):
    canonical_id: str | None = None
    variants: list[VariantChoice] = []
    owner_email: str | None = Field(None, pattern=r"^[^@\s]+@[^@\s]+$")
    reason: str | None = None
    checklist: list[ChecklistItem] = []


@router.post("/api/v1/conflicts/{conflict_id}/preview")
def conflict_preview(conflict_id: str, body: FixBody):
    """Free: what would this fix change? Nothing is modified."""
    try:
        return engine.preview_fix(conflict_id, body.canonical_id, [v.model_dump() for v in body.variants],
                                  body.owner_email)
    except KeyError as exc:
        raise problem(404, "Issue not found", "That issue no longer exists. It may already be fixed.") from exc


@router.post("/api/v1/conflicts/{conflict_id}/fix")
def conflict_fix(conflict_id: str, body: FixBody, who: str = Depends(actor), uid: str | None = Depends(paid_action)):
    """Apply a guided fix and write a decision record. Free in the demo; 1 credit in your own workspace."""
    from datetime import datetime, timezone

    out = _act(engine.apply_fix, conflict_id, who, body.reason or "", body.canonical_id,
               [v.model_dump() for v in body.variants], body.owner_email,
               [c.model_dump() for c in body.checklist], datetime.now(timezone.utc).isoformat(timespec="seconds"))
    charge(uid, "fix", out["issue_title"])
    return out


class DismissBody(BaseModel):
    reason: str = Field(..., min_length=3)


@router.post("/api/v1/conflicts/{conflict_id}/dismiss")
def conflict_dismiss(conflict_id: str, body: DismissBody, who: str = Depends(actor)):
    from datetime import datetime, timezone

    return _act(engine.dismiss_issue, conflict_id, who, body.reason,
                datetime.now(timezone.utc).isoformat(timespec="seconds"))


@router.get("/api/v1/decisions")
def list_decisions():
    return list(reversed(engine.decisions))


class ChecklistToggle(BaseModel):
    done: bool


@router.patch("/api/v1/decisions/{decision_id}/checklist/{index}")
def toggle_checklist(decision_id: str, index: int, body: ChecklistToggle, who: str = Depends(actor)):
    return _act(engine.set_checklist_item, decision_id, index, body.done, who)


@router.patch("/api/v1/conflicts/{conflict_id}")
def patch_conflict(conflict_id: str, body: ConflictPatch, who: str = Depends(actor)):
    return _act(engine.update_conflict, conflict_id, body.status, who, body.note)


# ---------------------------------------------------------------- graph

@router.get("/api/v1/graph")
def full_graph():
    return engine.graph


@router.get("/api/v1/graph/neighbourhood/{node_id}")
def graph_neighbourhood(node_id: str, depth: int = Query(2, ge=1, le=4), limit: int = Query(500, ge=10, le=2000)):
    try:
        if neo4j_graph:
            return neo4j_graph.neighbourhood(node_id, depth, limit)
        return engine.neighbourhood(node_id, depth, limit)
    except KeyError as exc:
        raise problem(404, "Node not found", node_id) from exc


# ---------------------------------------------------------------- ask

class AskBody(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@router.post("/api/v1/ask")
def ask(body: AskBody, who: str = Depends(actor), uid: str | None = Depends(paid_action)):
    out = run_ask(engine, body.question, llm)
    charge(uid, "ask", body.question)
    user_ask_log().append({"answer_id": out["answer_id"], "user": who, "question": body.question,
                    "intent": out["intent"], "citations": out.get("citations", []),
                    "latency_ms": out["latency_ms"], "feedback": 0})
    return out


class FeedbackBody(BaseModel):
    value: Literal[-1, 0, 1]


@router.post("/api/v1/ask/{answer_id}/feedback")
def ask_feedback(answer_id: str, body: FeedbackBody):
    for row in user_ask_log():
        if row["answer_id"] == answer_id:
            row["feedback"] = body.value
            return row
    raise problem(404, "Answer not found", answer_id)


# ---------------------------------------------------------------- ingest & admin

REQUIRED_COLUMNS = {
    "glossary": {"term_id", "term", "definition"},
    "metric": {"metric_id", "name", "formula"},
    "dashboard": {"dashboard_id", "name", "metrics"},
    "lineage": {"from_type", "from_id", "relation", "to_type", "to_id"},
    "recommendation": {"rec_id", "model", "title", "raw_confidence"},
}


@router.post("/api/v1/ingest/{source_type}")
async def ingest(source_type: Literal["glossary", "metric", "dashboard", "lineage", "recommendation"],
                 file: UploadFile = File(...), mode: Literal["upsert", "replace"] = "upsert",
                 who: str = Depends(actor)):
    own_data_only()
    uid = paid_action()
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise problem(422, "Empty file", "No rows found")
    missing = REQUIRED_COLUMNS[source_type] - set(rows[0].keys())
    if missing:
        raise problem(422, "Missing columns", ", ".join(sorted(missing)))
    store = engine.store
    ok, errors = apply_ingest(engine, source_type, rows, mode)
    summary = engine.recompute()
    charge(uid, "ingest", f"{source_type}: {file.filename}")
    record("ingest", {"source_type": source_type, "rows": rows, "mode": mode})
    _sync_graph()
    store.audit.append({"actor": who, "action": f"ingest_{source_type}", "entity_id": file.filename,
                        "reason": None, "payload": {"rows": ok, "errors": len(errors)}})
    return {"source_type": source_type, "rows_ingested": ok, "errors": errors, **summary}


@router.post("/api/v1/extract/{tool}")
async def extract(tool: Literal["powerbi", "tableau", "dbt"], file: UploadFile = File(...),
                  file2: UploadFile | None = File(None), commit: bool = False,
                  dashboard: str | None = None, who: str = Depends(actor)):
    """Preview is free; commit=true uses one credit (own workspace only)."""
    uid = None
    if commit:
        own_data_only()
        uid = paid_action()
    """Read metric definitions from a Power BI model (.tmdl / model.bim), a Tableau workbook (.twb / .twbx),
    or dbt artifacts (target/manifest.json and/or target/semantic_manifest.json, as file and file2).
    commit=false returns a preview; commit=true adds them to the workspace and recomputes."""
    data = await file.read()
    name = file.filename or tool
    try:
        if tool == "dbt":
            files = [(name, data)]
            if file2 is not None:
                files.append((file2.filename or "file2", await file2.read()))
            res = extract_dbt(files, engine.store.glossary)
            name = res.source_name
        elif tool == "powerbi":
            res = extract_powerbi(data.decode("utf-8-sig"), name, engine.store.glossary, dashboard or name.rsplit(".", 1)[0])
        else:
            res = extract_tableau(data, name, engine.store.glossary)
    except Exception as exc:  # noqa: BLE001
        raise problem(422, "Could not read file", str(exc)) from exc
    out = res.to_dict()
    if commit:
        apply_extract(engine, res.metrics, res.dashboards, res.lineage, res.nodes)
        out["summary"] = engine.recompute()
        charge(uid, "extract", name)
        record("extract", {"metrics": res.metrics, "dashboards": res.dashboards, "lineage": res.lineage,
                           "nodes": res.nodes})
        _sync_graph()
        engine.store.audit.append({"actor": who, "action": f"extract_{tool}", "entity_id": name, "reason": None,
                                   "payload": {"metrics": len(res.metrics), "dashboards": len(res.dashboards),
                                               "lineage": len(res.lineage)}})
        new_conflicts = [conflict_dict(c) for c in engine.conflicts
                         if c.status == "open" and any(r["metric_id"] in c.entity_ids for r in res.metrics)]
        out["new_conflicts"] = new_conflicts
    return out


@router.post("/api/v1/scores/recompute")
def recompute():
    out = engine.recompute()
    _sync_graph()
    return out


@router.get("/api/v1/audit")
def audit():
    return list(reversed(engine.store.audit))
