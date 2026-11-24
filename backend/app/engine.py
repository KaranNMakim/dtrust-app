"""TrustEngine: ties store, conflict rules, scoring and the graph together.

Recompute order (PRD 7.2): detect conflicts -> score metrics -> score recommendations
-> mirror onto graph. Scores are appended to an in-memory history (append-only, like
the `trust_score` table) so trends and "why did this drop?" work.
"""

from __future__ import annotations

import threading
from dataclasses import asdict
from datetime import datetime

from . import conflicts as conflict_rules
from .graph import build_graph, find_cycles, lineage_paths, metrics_on_cycles, neighbourhood
from .models import Conflict, TrustScore
from .scoring import MTS_VERSION, MTS_WEIGHTS, score_metric, score_recommendation
from .store import Store


class ActionError(ValueError):
    pass


class TrustEngine:
    def __init__(self, store: Store, now_fn, explainer=None):
        self.store = store
        self.now_fn = now_fn
        self.explainer = explainer  # optional LLM explainer: (TrustScore, name) -> str
        self._lock = threading.RLock()
        self._conflict_status: dict[str, tuple[str, str | None]] = {}
        self.weights: dict[str, float] = dict(MTS_WEIGHTS)
        self.scoring_version = MTS_VERSION
        self.conflicts: list[Conflict] = []
        self.metric_scores: dict[str, TrustScore] = {}
        self.rec_scores: dict[str, TrustScore] = {}
        self.history: dict[str, list[dict]] = {}
        self.graph: dict = {"nodes": [], "edges": []}
        self.recompute()

    # ------------------------------------------------------------ pipeline
    def recompute(self) -> dict:
        with self._lock:
            now: datetime = self.now_fn()
            found = conflict_rules.detect(self.store)
            for c in found:
                if c.id in self._conflict_status:
                    c.status, c.resolution_note = self._conflict_status[c.id]
            self.conflicts = found

            cycles = find_cycles(self.store)
            on_cycle = metrics_on_cycles(self.store, cycles)
            self.metric_scores = {
                m.id: score_metric(self.store, m, found, now, on_cycle.get(m.id), self.weights, self.scoring_version)
                for m in self.store.metrics.values()
            }
            mts = {k: v.score for k, v in self.metric_scores.items()}
            self.rec_scores = {
                r.id: score_recommendation(self.store, r, mts) for r in self.store.recommendations.values()
            }
            for ts in list(self.metric_scores.values()) + list(self.rec_scores.values()):
                ts.explanation = self._explain(ts)
                hist = self.history.setdefault(ts.entity_id, [])
                if not hist or hist[-1]["score"] != ts.score:
                    hist.append({"score": ts.score, "zone": ts.zone, "computed_at": now.isoformat()})

            self.graph = build_graph(self.store, self.score_map())
            return {"metrics": len(self.metric_scores), "recommendations": len(self.rec_scores),
                    "conflicts_open": sum(c.status == "open" for c in found)}

    def score_map(self) -> dict[str, dict]:
        out = {k: {"score": v.score, "zone": v.zone} for k, v in self.metric_scores.items()}
        out.update({k: {"score": v.score, "zone": v.zone} for k, v in self.rec_scores.items()})
        # Dashboards inherit the weakest metric they show; data products the weakest metric they calculate.
        for d in self.store.dashboards.values():
            vals = [self.metric_scores[m].score for m in d.metric_ids if m in self.metric_scores]
            if vals:
                s = min(vals)
                out[d.id] = {"score": s, "zone": _zone(s)}
        dp_vals: dict[str, list[float]] = {}
        for m in self.store.metrics.values():
            if m.data_product_id:
                dp_vals.setdefault(m.data_product_id, []).append(self.metric_scores[m.id].score)
        for dp, vals in dp_vals.items():
            out.setdefault(dp, {"score": min(vals), "zone": _zone(min(vals))})
        return out

    def _explain(self, ts: TrustScore) -> str:
        name = self.store.name_of(ts.entity_id)
        if self.explainer:
            try:
                return self.explainer(ts, name)
            except Exception:  # never let the LLM break scoring
                pass
        return template_explanation(ts, name)

    # ------------------------------------------------------------ reads
    def index(self) -> dict:
        """Enterprise Trust Index: viewer-weighted average MTS of active metrics."""
        active = [m for m in self.store.metrics.values() if m.certification != "deprecated"]
        weights = {m.id: 1 + sum(d.monthly_viewers for d in self.store.consumers(m.id)) for m in active}
        total_w = sum(weights.values()) or 1
        idx = sum(self.metric_scores[m.id].score * weights[m.id] for m in active) / total_w
        zones = {"green": 0, "yellow": 0, "red": 0}
        for m in active:
            zones[self.metric_scores[m.id].zone] += 1
        open_conf = [c for c in self.conflicts if c.status == "open"]
        return {
            "index": round(idx, 1),
            "zone": _zone(idx),
            "metrics": len(active),
            "certified": sum(m.certification == "certified" for m in active),
            "zones": zones,
            "conflicts_open": len(open_conf),
            "conflicts_critical": sum(c.severity == "critical" for c in open_conf),
            "top_conflicts": [conflict_dict(c) for c in open_conf[:5]],
            "recommendations": {z: sum(r.zone == z for r in self.rec_scores.values()) for z in zones},
        }

    def metric_detail(self, metric_id: str) -> dict:
        m = self._metric(metric_id)
        ts = self.metric_scores[m.id]
        return {
            "id": m.id, "name": m.name, "formula": m.formula, "grain": m.grain,
            "owner_email": m.owner_email, "team": m.team,
            "glossary_term": self.store.glossary[m.glossary_term_id].term if m.glossary_term_id else None,
            "glossary_term_id": m.glossary_term_id,
            "data_product": self.store.name_of(m.data_product_id) if m.data_product_id else None,
            "certification": m.certification,
            "last_refreshed": m.last_refreshed.isoformat() if m.last_refreshed else None,
            "refresh_sla_hours": m.refresh_sla_hours,
            "trust_score": ts.score, "zone": ts.zone,
            "explanation": ts.explanation,
        }

    def metric_usage(self, metric_id: str) -> list[dict]:
        m = self._metric(metric_id)
        return [{"dashboard_id": d.id, "name": d.name, "tool": d.tool, "audience": d.audience,
                 "monthly_viewers": d.monthly_viewers, "owner_email": d.owner_email,
                 "local_override": d.local_overrides.get(m.id)} for d in self.store.consumers(m.id)]

    def metric_lineage(self, metric_id: str) -> list[dict]:
        return lineage_paths(self.store, self._metric(metric_id).id)

    def neighbourhood(self, node_id: str, depth: int = 2, limit: int = 500) -> dict:
        if not any(n["id"] == node_id for n in self.graph["nodes"]):
            raise KeyError(node_id)
        return neighbourhood(self.graph, node_id, depth, limit)

    # ------------------------------------------------------------ actions
    def certify(self, metric_id: str, actor: str, reason: str | None = None) -> dict:
        with self._lock:
            m = self._metric(metric_id)
            ts = self.metric_scores[m.id]
            if ts.score < 80:
                raise ActionError(f"{m.name} scores {ts.score}; certification needs 80 or more. "
                                  f"Fix: {_top_fix(ts)}")
            if m.glossary_term_id:
                for peer in self.store.metrics_for_term(m.glossary_term_id):
                    if peer.id != m.id and peer.certification == "certified":
                        raise ActionError(f"{peer.name} is already certified for this term; deprecate it first")
            m.certification = "certified"
            self._audit(actor, "certify", m.id, reason)
            self.recompute()
            return self.metric_detail(m.id)

    def deprecate(self, metric_id: str, actor: str, reason: str | None = None,
                  replacement_id: str | None = None) -> dict:
        with self._lock:
            m = self._metric(metric_id)
            if replacement_id:
                self._metric(replacement_id)
            m.certification = "deprecated"
            self._audit(actor, "deprecate", m.id, reason, {"replacement_id": replacement_id})
            self.recompute()
            return self.metric_detail(m.id)

    def assign_owner(self, metric_id: str, owner_email: str, actor: str) -> dict:
        with self._lock:
            m = self._metric(metric_id)
            m.owner_email = owner_email
            self._audit(actor, "assign_owner", m.id, None, {"owner_email": owner_email})
            self.recompute()
            return self.metric_detail(m.id)

    def update_conflict(self, conflict_id: str, status: str, actor: str, note: str | None = None) -> dict:
        if status not in {"open", "resolved", "dismissed"}:
            raise ActionError("status must be open, resolved or dismissed")
        with self._lock:
            c = next((c for c in self.conflicts if c.id == conflict_id), None)
            if not c:
                raise KeyError(conflict_id)
            self._conflict_status[c.id] = (status, note)
            self._audit(actor, f"conflict_{status}", c.id, note)
            self.recompute()
            return conflict_dict(next(x for x in self.conflicts if x.id == conflict_id))

    def log_outcome(self, rec_id: str, accepted: bool, success: bool | None, actor: str) -> dict:
        with self._lock:
            r = self.store.recommendations.get(rec_id)
            if not r:
                raise KeyError(rec_id)
            if accepted:
                r.accepted_90d += 1
                if success:
                    r.success_90d += 1
            self._audit(actor, "log_outcome", rec_id, None, {"accepted": accepted, "success": success})
            self.recompute()
            return score_dict(self.rec_scores[rec_id], self.store)

    def set_weights(self, weights: dict[str, float] | None, actor: str) -> dict:
        with self._lock:
            if weights is None:
                self.weights, self.scoring_version = dict(MTS_WEIGHTS), MTS_VERSION
            else:
                if set(weights) != set(MTS_WEIGHTS) or abs(sum(weights.values()) - 1) > 0.01:
                    raise ActionError("weights must cover all five components and sum to 1")
                self.weights, self.scoring_version = dict(weights), MTS_VERSION + "-calibrated"
            self._audit(actor, "set_weights", "mts", None, {"weights": self.weights})
            return self.recompute()

    def rename_variant(self, metric_id: str, term: str, definition: str, actor: str,
                       new_name: str | None = None) -> dict:
        """Give a divergent variant its own business term (e.g. 'Bookings') instead of fighting over 'Revenue'."""
        from .definition import parse
        from .extractors.common import snake
        from .models import GlossaryTerm

        with self._lock:
            m = self._metric(metric_id)
            gid = "g_" + snake(term)
            if gid in self.store.glossary and self.store.glossary[gid].term.lower() != term.lower():
                raise ActionError(f"Glossary id {gid} is taken")
            if gid not in self.store.glossary:
                d = parse(m.formula)
                required = sorted(t.column for t in d.terms + d.denominator if t.is_simple)
                self.store.glossary[gid] = GlossaryTerm(gid, term, definition, m.owner_email, required, [term.lower()])
                self.store.node_names[gid] = ("GlossaryTerm", term)
            old = m.glossary_term_id
            m.glossary_term_id = gid
            if new_name:
                m.name = new_name
                self.store.node_names[m.id] = ("Metric", new_name)
            self._audit(actor, "rename_variant", m.id, None, {"from_term": old, "to_term": gid, "new_name": new_name})
            self.recompute()
            return self.metric_detail(m.id)

    def _audit(self, actor: str, action: str, entity_id: str, reason: str | None, payload: dict | None = None):
        self.store.audit.append({"actor": actor, "action": action, "entity_id": entity_id,
                                 "reason": reason, "payload": payload or {},
                                 "created_at": self.now_fn().isoformat()})

    def _metric(self, metric_id: str):
        m = self.store.metrics.get(metric_id)
        if not m:
            raise KeyError(metric_id)
        return m


# ---------------------------------------------------------------- serialisers & helpers

def _zone(s: float) -> str:
    return "green" if s >= 80 else "yellow" if s >= 50 else "red"


def _top_fix(ts: TrustScore) -> str:
    weakest = min(ts.components, key=lambda c: c.raw)
    return weakest.fix or f"improve {weakest.label.lower()}"


def score_dict(ts: TrustScore, store: Store) -> dict:
    return {
        "entity_type": ts.entity_type,
        "entity_id": ts.entity_id,
        "name": store.name_of(ts.entity_id),
        "score": ts.score,
        "zone": ts.zone,
        "scoring_version": ts.scoring_version,
        "components": [{**asdict(c), "weighted": round(c.weighted, 1)} for c in ts.components],
        "penalties": ts.penalties,
        "cap": ts.cap,
        "explanation": ts.explanation,
    }


def conflict_dict(c: Conflict) -> dict:
    return asdict(c)


def template_explanation(ts: TrustScore, name: str) -> str:
    """Deterministic two-sentence explanation, used when no LLM is configured."""
    strongest = max(ts.components, key=lambda c: c.raw)
    weakest = min(ts.components, key=lambda c: c.raw)
    verdict = {"green": "can be trusted", "yellow": "should be used with caution", "red": "should not be trusted"}[ts.zone]
    s1 = f"{name} scores {ts.score:.0f} and {verdict}."
    if weakest.raw >= 90:
        s2 = f"All components are strong; best is {strongest.label.lower()} ({strongest.evidence[0]})."
    else:
        s2 = f"The main drag is {weakest.label.lower()}: {weakest.evidence[0]}."
    if ts.cap:
        if ts.cap.get("metric_id"):
            s2 += f" Capped at {ts.cap['ceiling']:.0f} by its weakest input, {ts.cap['metric']}."
        else:
            s2 += f" Capped at {ts.cap['ceiling']:.0f}: {ts.cap['metric']}."
    return f"{s1} {s2}"
