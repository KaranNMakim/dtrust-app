"""Turn a conflict into a migration plan, because changing a KPI definition is a release, not a config change.

The plan names the canonical metric, says what to do with every variant (deprecate,
or rename to a distinct concept when it measures something genuinely different),
shows the reconciliation bridge for each, lists affected dashboards, and sequences
the steps: decide, restate, run side by side, re-baseline targets, retire.
"""

from __future__ import annotations

from .definition import parse
from .reconcile import reconcile

RENAME_SUGGESTIONS = {
    "opportunity_amount": ("Bookings", "Value of closed-won opportunities by close date, before invoicing, returns, discounts and rebates."),
    "order_value": ("Gross Merchandise Value", "Gross value of customer orders by order date, before refunds, returns and discounts."),
    "gross_revenue": ("Gross Revenue", "Revenue before returns, discounts and rebates."),
}


def _dashboards(engine, metric_ids: list[str]) -> list[dict]:
    seen = {}
    for mid in metric_ids:
        for d in engine.store.consumers(mid):
            row = seen.setdefault(d.id, {"dashboard_id": d.id, "name": d.name, "audience": d.audience,
                                         "monthly_viewers": d.monthly_viewers, "owner_email": d.owner_email,
                                         "shows": []})
            row["shows"].append(engine.store.name_of(mid))
    return sorted(seen.values(), key=lambda r: (r["audience"] != "exec", -r["monthly_viewers"]))


def plan(engine, conflict_id: str) -> dict:
    c = next((x for x in engine.conflicts if x.id == conflict_id), None)
    if not c:
        raise KeyError(conflict_id)
    store = engine.store
    builder = {"C1": _plan_c1, "C2": _plan_c2, "C3": _plan_c3, "C4": _plan_c4, "C5": _plan_c5}[c.code]
    out = builder(engine, c)
    out.update({"conflict_id": c.id, "code": c.code, "title": c.title, "severity": c.severity})
    out.setdefault("affected_dashboards", _dashboards(engine, [e for e in c.entity_ids if e in store.metrics]))
    return out


def _plan_c1(engine, c) -> dict:
    store = engine.store
    members = [store.metrics[m] for m in c.entity_ids if m in store.metrics]
    members.sort(key=lambda m: (m.certification != "certified", -engine.metric_scores[m.id].score))
    canon = members[0]
    term = store.glossary[canon.glossary_term_id].term if canon.glossary_term_id else canon.name
    steward = store.glossary[canon.glossary_term_id].steward_email if canon.glossary_term_id else canon.owner_email
    variants = []
    for v in members[1:]:
        rec = reconcile(store, v.id, canon.id)
        d = parse(v.formula)
        base_cols = {t.column for t in d.base_terms}
        canon_base = {t.column for t in parse(canon.formula).base_terms}
        different_concept = bool(base_cols) and not (base_cols & canon_base)
        if different_concept:
            col = sorted(base_cols)[0]
            new_term, definition = RENAME_SUGGESTIONS.get(col, (f"{v.name} (distinct)", f"Variant of {term} based on {col}."))
            if d.deduction_terms and new_term.startswith("Gross "):
                new_term = "Net " + new_term[len("Gross "):]
                deducted = ", ".join(t.column.replace("_", " ") for t in d.deduction_terms)
                definition = f"{new_term}: {col.replace('_', ' ')} less {deducted}. Not recognised revenue."

            action = {"type": "rename", "label": f"Rename to '{new_term}' as its own business term",
                      "endpoint": f"POST /api/v1/metrics/{v.id}/rename-term",
                      "body": {"term": new_term, "definition": definition, "new_name": new_term}}
            why = f"It measures a different event ({', '.join(sorted(base_cols))}), so it deserves its own name, not deprecation."
        else:
            action = {"type": "deprecate", "label": f"Deprecate and repoint tiles to {canon.name}",
                      "endpoint": f"POST /api/v1/metrics/{v.id}/deprecate",
                      "body": {"reason": f"Superseded by {canon.name}", "replacement_id": canon.id}}
            why = f"Same concept as {canon.name} with a different calculation; one version should survive."
        variants.append({
            "metric_id": v.id, "name": v.name, "trust_score": engine.metric_scores[v.id].score,
            "owner_email": v.owner_email, "used_in": len(store.consumers(v.id)),
            "action": action, "why": why, "reconciliation": rec["summary"],
            "bridge": rec["bridge"],
        })
    dashboards = _dashboards(engine, [m.id for m in members])
    exec_dash = [d["name"] for d in dashboards if d["audience"] == "exec"]
    steps = [
        {"step": 1, "title": "Decide and announce", "owner": steward,
         "detail": f"{canon.name} is the definition of '{term}'. Share this plan and each variant's reconciliation with its owner."},
        {"step": 2, "title": "Name the genuinely different concepts",
         "owner": "Metric owners", "detail": "Rename variants that measure a different event (e.g. Bookings) instead of deprecating them."},
        {"step": 3, "title": "Restate history", "owner": steward,
         "detail": "Recompute the canonical metric for every period used in targets and trend charts, so the change shows as a restatement, not a drop."},
        {"step": 4, "title": "Run side by side for one reporting cycle", "owner": "Dashboard owners",
         "detail": "Show old and new tiles together, labelled, on: " + (", ".join(exec_dash) or "the affected dashboards") + "."},
        {"step": 5, "title": "Re-baseline targets and incentives", "owner": "Finance and HR",
         "detail": "Translate targets set on the old definition using the reconciliation bridge, so no team is penalised by the change."},
        {"step": 6, "title": "Retire the old versions", "owner": "Data steward",
         "detail": "Deprecate remaining variants, remove old tiles, and confirm this conflict closes on the next recompute."},
    ]
    return {"canonical": {"metric_id": canon.id, "name": canon.name, "trust_score": engine.metric_scores[canon.id].score,
                          "certification": canon.certification, "owner_email": canon.owner_email},
            "term": term, "variants": variants, "steps": steps, "affected_dashboards": dashboards,
            "impact": {"dashboards": len(dashboards), "exec_dashboards": len(exec_dash),
                       "monthly_viewers": sum(d["monthly_viewers"] for d in dashboards)}}


def _plan_c2(engine, c) -> dict:
    m = engine.store.metrics[c.entity_ids[0]]
    rows = c.detail.get("overrides", [])
    return {"steps": [
        {"step": 1, "title": "Ask why the override exists", "owner": rows[0]["dashboard"] if rows else "Dashboard owner",
         "detail": "; ".join(f"{r['dashboard']}: {r['expression']}" for r in rows)},
        {"step": 2, "title": "Promote it or remove it", "owner": m.owner_email or "Metric owner",
         "detail": f"If the view is needed, publish it as a governed metric (e.g. '{m.name} excl. filter') with its own owner; otherwise remove the filter."},
        {"step": 3, "title": "Label the tile", "owner": "Dashboard owner", "detail": "Any remaining filter must be visible on the tile title."},
    ]}


def _plan_c3(engine, c) -> dict:
    m = engine.store.metrics[c.entity_ids[0]]
    steward = engine.store.glossary[m.glossary_term_id].steward_email if m.glossary_term_id else None
    return {"steps": [
        {"step": 1, "title": "Assign a named owner", "owner": steward or "Data governance lead",
         "detail": f"{m.team or 'The team on record'} must nominate a person. Suggested interim owner: {steward or 'the domain steward'}.",
         "action": {"type": "assign_owner", "endpoint": f"POST /api/v1/metrics/{m.id}/owner"}},
        {"step": 2, "title": "Decide: keep, merge or retire", "owner": "New owner",
         "detail": "An orphan often duplicates a governed metric. Reconcile it against the certified version before keeping it."},
    ]}


def _plan_c4(engine, c) -> dict:
    store = engine.store
    cyc = c.detail.get("cycle", [])
    undocumented = [f"{e.from_name} → {e.to_name}" for e in store.lineage
                    if e.from_id in cyc and e.to_id in cyc and not e.documented]
    return {"steps": [
        {"step": 1, "title": "Find the edge that should not exist", "owner": "Data platform team",
         "detail": "Likely candidates (undocumented edges inside the cycle): " + (", ".join(undocumented) or "none found")},
        {"step": 2, "title": "Break the cycle", "owner": "Data product owners",
         "detail": "Move the shared logic into an upstream data product both can depend on."},
        {"step": 3, "title": "Re-run affected metrics", "owner": "Data platform team",
         "detail": "Recompute: " + ", ".join(store.name_of(m) for m in c.detail.get("affected_metrics", []))},
    ]}


def _plan_c5(engine, c) -> dict:
    m = engine.store.metrics[c.entity_ids[0]]
    missing = c.detail.get("missing_components", [])
    return {"steps": [
        {"step": 1, "title": "Align the formula or rename the metric", "owner": m.owner_email or "Metric owner",
         "detail": f"Missing from the glossary definition: {', '.join(missing) or 'n/a'}. Either add them or give the metric a distinct name."},
    ]}
