"""Deterministic trust scoring. No LLM ever sets a number here.

MTS (Metric Trust Score) and RTS (Recommendation Trust Score) follow PRD sections 1.4-1.5.
Every component returns its raw 0-100 score plus the evidence strings behind it.
"""

from __future__ import annotations

from datetime import datetime

from . import formula as fx
from .graph import upstream_closure
from .models import Component, Conflict, Metric, Recommendation, TrustScore, zone_for
from .store import Store

MTS_VERSION = "mts-1.0"
RTS_VERSION = "rts-1.0"

MTS_WEIGHTS = {"definition": 0.30, "ownership": 0.20, "lineage": 0.20, "usage": 0.15, "freshness": 0.15}
RTS_WEIGHTS = {"explainability": 0.25, "confidence": 0.15, "data_quality": 0.25,
               "historical_accuracy": 0.20, "rule_compliance": 0.15}

PENALTY = {"critical": 15, "warning": 5}
REFERENCE_PENALTY = 5  # a certified metric involved in a conflict is the reference, not the culprit
PENALTY_CAP = 30
RTS_INPUT_HEADROOM = 20
MIN_HISTORY = 20
NO_EVIDENCE_CEILING = 45  # confidence alone is not trust
CRITICAL_RULE_CEILING = 40  # a critical policy breach must be approved by a human before acting
DEFINITION_CODES = {"C1", "C5"}


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- MTS components

def definition_consistency(store: Store, m: Metric) -> Component:
    ev: list[str] = []
    fix = None
    if not m.glossary_term_id:
        ev.append("Not linked to a business glossary term")
        return Component("definition", "Definition consistency", MTS_WEIGHTS["definition"], 60.0, ev,
                         "Link this metric to a glossary term")
    g = store.glossary[m.glossary_term_id]
    peers = [p for p in store.metrics_for_term(g.id) if p.certification != "deprecated"]
    variants = {p.formula_hash for p in peers}
    rivals = len(variants) - 1
    certified = [p for p in peers if p.certification == "certified"]
    is_reference = m.certification == "certified" or (certified and certified[0].formula_hash == m.formula_hash)

    if rivals == 0:
        raw = 100.0
        ev.append(f"All {len(peers)} implementation(s) of '{g.term}' share one formula")
    elif is_reference:
        raw = 100.0 - 2 * rivals
        ev.append(f"Certified reference; {rivals} rival variant(s) of '{g.term}' exist elsewhere")
    else:
        raw = 100.0 - 15 * rivals
        ev.append(f"{len(variants)} different formulas exist for '{g.term}'")
        fix = f"Align to the certified definition of '{g.term}' or rename to a distinct concept"

    align = fx.glossary_alignment(m.formula, g.required_components)
    ev.append(f"Glossary alignment {align:.2f}")
    if align < 0.5:
        raw = min(raw, 40.0)
        fix = fix or "Formula is missing most components of the glossary definition"
    elif align < 0.85:
        raw = min(raw, 60.0)
        missing = [c for c in g.required_components if c not in m.formula_tokens]
        ev.append("Missing: " + ", ".join(missing))
        fix = fix or f"Add {', '.join(missing)} to match the glossary"
    return Component("definition", "Definition consistency", MTS_WEIGHTS["definition"], clamp(raw), ev, fix)


def ownership_clarity(store: Store, m: Metric) -> Component:
    ev: list[str] = []
    if not m.owner_email:
        ev.append("No named owner")
        if m.team:
            ev.append(f"Team on record: {m.team} (a team is not an accountable owner)")
        return Component("ownership", "Ownership clarity", MTS_WEIGHTS["ownership"], 0.0, ev, "Assign a named owner")
    raw = 60.0
    ev.append(f"Owner: {m.owner_email}")
    fix = None
    if m.team:
        raw += 20
        ev.append(f"Team: {m.team}")
    steward = store.glossary[m.glossary_term_id].steward_email if m.glossary_term_id else None
    if steward:
        raw += 20
        ev.append(f"Steward: {steward}")
    else:
        fix = "Assign a steward via a glossary term"
    return Component("ownership", "Ownership clarity", MTS_WEIGHTS["ownership"], clamp(raw), ev, fix)


def lineage_completeness(store: Store, m: Metric, on_cycle: list[str] | None) -> Component:
    ev: list[str] = []
    if not m.data_product_id:
        return Component("lineage", "Lineage completeness", MTS_WEIGHTS["lineage"], 0.0,
                         ["No data product calculates this metric"], "Map the metric to its data product")
    edges, visited = upstream_closure(store, m.data_product_id)
    hops = len(edges) + 1  # + the CALCULATES hop
    documented = sum(e.documented for e in edges) + 1
    reaches_source = any(store.label_of(n) == "SourceSystem" for n in visited)
    raw = 100.0 * documented / hops
    ev.append(f"{documented} of {hops} lineage hops documented")
    fix = None
    if not reaches_source:
        raw = min(raw, 50.0)
        ev.append("Lineage does not reach a source system")
        fix = "Document the path to the source system"
    undocumented = [f"{e.from_name} → {e.to_name}" for e in edges if not e.documented]
    if undocumented:
        fix = fix or "Document " + "; ".join(undocumented[:2])
    if on_cycle:
        raw = raw * 0.5
        ev.append("Sits downstream of circular lineage: " + " → ".join(store.name_of(n) for n in on_cycle))
        fix = "Break the lineage cycle"
    return Component("lineage", "Lineage completeness", MTS_WEIGHTS["lineage"], clamp(raw), ev, fix)


def usage_consistency(store: Store, m: Metric) -> Component:
    consumers = store.consumers(m.id)
    if not consumers:
        return Component("usage", "Usage consistency", MTS_WEIGHTS["usage"], 70.0,
                         ["Not used on any dashboard"], None)
    overrides = [d for d in consumers if m.id in d.local_overrides]
    raw = 100.0 * (1 - len(overrides) / len(consumers))
    ev = [f"{len(consumers) - len(overrides)} of {len(consumers)} dashboards use it as defined"]
    fix = None
    if overrides:
        ev.append("Undocumented overrides on: " + ", ".join(d.name for d in overrides))
        fix = "Promote the override to a governed metric or remove it"
    if m.glossary_term_id and m.certification != "certified":
        rivals_on_exec = {
            p.id for p in store.metrics_for_term(m.glossary_term_id)
            if p.id != m.id and p.certification != "deprecated"
            and any(d.audience == "exec" for d in store.consumers(p.id))
        }
        on_exec = any(d.audience == "exec" for d in consumers)
        if on_exec and rivals_on_exec:
            raw -= 10
            ev.append("A rival definition is also shown to executives")
    return Component("usage", "Usage consistency", MTS_WEIGHTS["usage"], clamp(raw), ev, fix)


def freshness(m: Metric, now: datetime) -> Component:
    if not m.last_refreshed:
        return Component("freshness", "Freshness", MTS_WEIGHTS["freshness"], 0.0, ["No refresh recorded"],
                         "Report refresh timestamps")
    age_h = (now - m.last_refreshed).total_seconds() / 3600
    sla = m.refresh_sla_hours
    if age_h <= sla:
        raw = 100.0
    elif age_h >= 3 * sla:
        raw = 0.0
    else:
        raw = 100.0 * (1 - (age_h - sla) / (2 * sla))
    ev = [f"Refreshed {_age(age_h)} ago, SLA {_age(sla)}"]
    fix = None if raw == 100 else "Fix the refresh schedule or relax the SLA"
    return Component("freshness", "Freshness", MTS_WEIGHTS["freshness"], clamp(raw), ev, fix)


def _age(hours: float) -> str:
    if hours < 48:
        return f"{hours:.0f} h"
    return f"{hours / 24:.0f} days"


# ---------------------------------------------------------------- MTS

def score_metric(store: Store, m: Metric, conflicts: list[Conflict], now: datetime,
                 on_cycle: list[str] | None = None, weights: dict[str, float] | None = None,
                 version: str = MTS_VERSION) -> TrustScore:
    comps = [
        definition_consistency(store, m),
        ownership_clarity(store, m),
        lineage_completeness(store, m, on_cycle),
        usage_consistency(store, m),
        freshness(m, now),
    ]
    if weights:
        for c in comps:
            c.weight = weights[c.key]
    base = sum(c.weighted for c in comps)
    penalties: list[dict] = []
    definition_penalised = False
    open_mine = sorted((c for c in conflicts if c.status == "open" and m.id in c.entity_ids),
                       key=lambda c: (c.code not in DEFINITION_CODES, c.severity != "critical"))
    for c in open_mine:
        # C1 and C5 describe the same root cause (a divergent definition): charge it once, at the worst severity.
        if c.code in DEFINITION_CODES:
            if definition_penalised:
                penalties.append({"conflict_id": c.id, "code": c.code, "severity": c.severity, "points": 0,
                                  "note": "same root cause as a definition conflict already counted"})
                continue
            definition_penalised = True
        pts = REFERENCE_PENALTY if m.certification == "certified" else PENALTY.get(c.severity, 0)
        penalties.append({"conflict_id": c.id, "code": c.code, "severity": c.severity, "points": -pts})
    total_pen = min(PENALTY_CAP, sum(-p["points"] for p in penalties))
    score = round(clamp(base - total_pen), 1)
    return TrustScore("metric", m.id, score, zone_for(score), comps, penalties, version)


# ---------------------------------------------------------------- RTS

def score_recommendation(store: Store, r: Recommendation, mts: dict[str, float]) -> TrustScore:
    comps: list[Component] = []

    # Explainability
    ev, raw = [], 0.0
    if r.input_features:
        raw += 40
        ev.append(f"{len(r.input_features)} feature attributions provided")
    else:
        ev.append("No feature attributions")
    if r.evidence:
        resolved = [e for e in r.evidence if store.exists(e)]
        raw += 40 * len(resolved) / len(r.evidence)
        ev.append(f"{len(resolved)} of {len(r.evidence)} evidence links resolve to graph nodes")
    else:
        ev.append("No evidence cited")
    if r.rationale:
        raw += 20
        ev.append("Natural-language rationale present")
    else:
        ev.append("No rationale")
    comps.append(Component("explainability", "Explainability", RTS_WEIGHTS["explainability"], clamp(raw), ev,
                           None if raw >= 80 else "Cite evidence and attach a rationale"))

    # Historical accuracy
    if r.accepted_90d >= MIN_HISTORY:
        acc = r.success_90d / r.accepted_90d
        hist_raw = 100 * acc
        hist_ev = [f"{r.success_90d} of {r.accepted_90d} accepted recommendations succeeded (90 days)"]
    else:
        acc = None
        hist_raw = 50.0
        hist_ev = [f"Only {r.accepted_90d} observed outcomes; neutral until {MIN_HISTORY}"]

    # Confidence, calibrated by history
    if acc is not None:
        calibrated = (r.raw_confidence + acc) / 2
        conf_ev = [f"Model confidence {r.raw_confidence:.2f}, calibrated to {calibrated:.2f} using history"]
    else:
        calibrated = r.raw_confidence * 0.8
        conf_ev = [f"Model confidence {r.raw_confidence:.2f}, discounted to {calibrated:.2f} (no calibration history)"]
    comps.append(Component("confidence", "Confidence", RTS_WEIGHTS["confidence"], clamp(100 * calibrated), conf_ev))

    # Data quality = attribution-weighted MTS of inputs
    known = {k: w for k, w in r.input_features.items() if k in mts}
    if known:
        wsum = sum(known.values())
        dq = sum(mts[k] * w for k, w in known.items()) / wsum
        dq_ev = [f"{store.name_of(k)}: {mts[k]:.0f} (weight {w:.2f})" for k, w in known.items()]
    else:
        dq, dq_ev = 0.0, ["No scored input metrics"]
    comps.append(Component("data_quality", "Data quality", RTS_WEIGHTS["data_quality"], clamp(dq), dq_ev,
                           None if dq >= 80 else "Raise the trust of the input metrics"))

    comps.append(Component("historical_accuracy", "Historical accuracy", RTS_WEIGHTS["historical_accuracy"],
                           clamp(hist_raw), hist_ev, None if acc is not None else "Log outcomes via the API"))

    # Business-rule compliance
    viol = r.rule_violations
    rc = 100.0 - 25 * len(viol)
    rc_ev = ["No rule violations"] if not viol else [
        f"Violates: {store.rules[v].name if v in store.rules else v}" for v in viol]
    comps.append(Component("rule_compliance", "Business-rule compliance", RTS_WEIGHTS["rule_compliance"],
                           clamp(rc), rc_ev, None if not viol else "Route for approval before acting"))

    base = sum(c.weighted for c in comps)
    penalties: list[dict] = []
    if viol:
        # A critical rule violation is a hard stop: the recommendation cannot be trusted as-is.
        crit = [v for v in viol if store.rules.get(v) and store.rules[v].severity == "critical"]
        if crit:
            penalties.append({"code": "RULE", "rule": crit[0], "points": -15})
    score = base + sum(p["points"] for p in penalties)

    cap = None
    if known:
        weakest = min(known, key=lambda k: mts[k])
        ceiling = mts[weakest] + RTS_INPUT_HEADROOM
        if score > ceiling:
            cap = {"metric_id": weakest, "metric": store.name_of(weakest), "ceiling": round(ceiling, 1)}
            score = ceiling
    if penalties and score > CRITICAL_RULE_CEILING:
        cap = {"reason": "critical_rule_violation", "ceiling": CRITICAL_RULE_CEILING,
               "metric": f"critical rule '{penalties[0]['rule']}'", "metric_id": None}
        score = CRITICAL_RULE_CEILING
    if not r.evidence and score > NO_EVIDENCE_CEILING:
        cap = {"reason": "no_evidence", "ceiling": NO_EVIDENCE_CEILING,
               "metric": "no cited evidence", "metric_id": None}
        score = NO_EVIDENCE_CEILING
    score = round(clamp(score), 1)
    return TrustScore("recommendation", r.id, score, zone_for(score), comps, penalties, RTS_VERSION, cap=cap)
