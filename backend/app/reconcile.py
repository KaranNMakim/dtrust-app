"""Metric reconciliation: why do these two numbers disagree?

Given two metrics (optionally each in the context of a dashboard), produce:

1. **Causes**: every structural difference, classified into the seven usual reasons
   two dashboards drift apart: definition, filters, time logic, source, refresh,
   mapping, late adjustments.
2. **Bridge**: when component values are available for a period, a numeric walk
   from number A to number B, one step per cause, with an honest "unexplained"
   residual against what each dashboard actually reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .definition import LATE_ADJUSTMENT_COLUMNS, Definition, Term, humanize, parse
from .graph import upstream_closure
from .store import Store

CAUSES = {
    "definition": "Different definition",
    "filters": "Hidden filters",
    "time_logic": "Different time logic",
    "source": "Different source of truth",
    "refresh": "Refresh timing",
    "mapping": "Mappings, hierarchies and units",
    "late_adjustments": "Late adjustments",
    "unexplained": "Unexplained",
}

BASE_MEASURE_NOTES = {
    ("opportunity_amount", "invoice_amount"): "bookings at close date vs invoiced sales",
    ("order_value", "invoice_amount"): "gross order value vs invoiced sales",
}


@dataclass
class Side:
    metric_id: str
    dashboard_id: str | None
    name: str
    dashboard: str | None
    definition: Definition
    filters: list[str] = field(default_factory=list)  # formula + dashboard overrides


def _side(store: Store, metric_id: str, dashboard_id: str | None) -> Side:
    m = store.metrics[metric_id]
    d = parse(m.formula)
    filters = list(d.filters)
    dash_name = None
    if dashboard_id:
        dash = store.dashboards[dashboard_id]
        dash_name = dash.name
        if metric_id not in dash.metric_ids:
            raise ValueError(f"{dash.name} does not show {m.name}")
        if metric_id in dash.local_overrides:
            filters.append(dash.local_overrides[metric_id])
    return Side(metric_id, dashboard_id, m.name, dash_name, d, filters)


def _sources(store: Store, metric_id: str) -> set[str]:
    m = store.metrics[metric_id]
    if not m.data_product_id:
        return set()
    _, visited = upstream_closure(store, m.data_product_id)
    return {store.name_of(n) for n in visited if store.label_of(n) == "SourceSystem"}


def _cols(terms: list[Term]) -> dict[str, Term]:
    return {t.column: t for t in terms if not t.is_constant}


def _finding(cause: str, finding: str, detail: str = "", impact: float | None = None, key: str | None = None) -> dict:
    return {"cause": cause, "label": CAUSES[cause], "finding": finding, "detail": detail, "impact": impact, "key": key}


def structural_causes(store: Store, a: Side, b: Side) -> list[dict]:
    ma, mb = store.metrics[a.metric_id], store.metrics[b.metric_id]
    da, db = a.definition, b.definition
    out: list[dict] = []

    # ---- definition & late adjustments
    if da.kind != db.kind:
        out.append(_finding("definition", f"{a.name} is {da.kind}; {b.name} is {db.kind}",
                            "They measure different kinds of quantity and cannot be bridged numerically."))
    elif da.kind == "additive":
        base_a, base_b = _cols(da.base_terms), _cols(db.base_terms)
        if set(base_a) != set(base_b):
            only_a, only_b = sorted(set(base_a) - set(base_b)), sorted(set(base_b) - set(base_a))
            note = BASE_MEASURE_NOTES.get((tuple(only_a)[0] if only_a else "", tuple(only_b)[0] if only_b else ""), "")
            out.append(_finding(
                "definition",
                f"Different base measure: {', '.join(map(humanize, only_a)) or 'none'} vs {', '.join(map(humanize, only_b)) or 'none'}",
                note.capitalize() if note else "The two numbers start from different events or columns.",
                key="base",
            ))
        ded_a, ded_b = _cols(da.deduction_terms), _cols(db.deduction_terms)
        for col in sorted(set(ded_b) - set(ded_a)):
            cause = "late_adjustments" if col in LATE_ADJUSTMENT_COLUMNS else "definition"
            out.append(_finding(cause, f"{a.name} does not deduct {humanize(col)}; {b.name} does",
                                "Booked weeks after the sale; operational views rarely see it." if cause == "late_adjustments" else "",
                            key=f"ded:{col}"))
        for col in sorted(set(ded_a) - set(ded_b)):
            cause = "late_adjustments" if col in LATE_ADJUSTMENT_COLUMNS else "definition"
            out.append(_finding(cause, f"{a.name} deducts {humanize(col)}; {b.name} does not", key=f"ded:{col}"))
    else:  # ratio
        for part, ta, tb in (("numerator", da.terms, db.terms), ("denominator", da.denominator, db.denominator)):
            ka, kb = {t.key() for t in ta}, {t.key() for t in tb}
            if ka != kb:
                out.append(_finding("definition", f"Different {part}: {' '.join(sorted(ka))} vs {' '.join(sorted(kb))}"))

    # ---- filters
    fa, fb = set(a.filters), set(b.filters)
    for f in sorted(fa - fb):
        where = f"on {a.dashboard}" if a.dashboard and f not in da.filters else "in the formula"
        out.append(_finding("filters", f"{a.name} applies {f} {where}", "Invisible on the tile: the label stays the same.",
                            key=f"flt:{f}"))
    for f in sorted(fb - fa):
        where = f"on {b.dashboard}" if b.dashboard and f not in db.filters else "in the formula"
        out.append(_finding("filters", f"{b.name} applies {f} {where}", "Invisible on the tile: the label stays the same.",
                            key=f"flt:{f}"))

    # ---- time logic
    if ma.time_basis and mb.time_basis and ma.time_basis != mb.time_basis:
        out.append(_finding("time_logic", f"Dated by {humanize(ma.time_basis)} vs {humanize(mb.time_basis)}",
                            "The same transaction can fall in different periods."))
    if ma.calendar and mb.calendar and ma.calendar != mb.calendar:
        out.append(_finding("time_logic", f"{ma.calendar.capitalize()} vs {mb.calendar} calendar",
                            "Month and quarter boundaries differ."))
    if ma.grain != mb.grain:
        out.append(_finding("time_logic", f"{ma.grain.capitalize()} vs {mb.grain} grain"))

    # ---- source
    sa, sb = _sources(store, a.metric_id), _sources(store, b.metric_id)
    if sa != sb:
        out.append(_finding("source", f"Sourced from {', '.join(sorted(sa)) or 'unknown'} vs {', '.join(sorted(sb)) or 'unknown'}",
                            "Each system captures the transaction at a different moment in its life."))

    # ---- refresh
    if ma.last_refreshed and mb.last_refreshed:
        gap_h = abs((ma.last_refreshed - mb.last_refreshed).total_seconds()) / 3600
        if gap_h > min(ma.refresh_sla_hours, mb.refresh_sla_hours):
            older = a.name if ma.last_refreshed < mb.last_refreshed else b.name
            out.append(_finding("refresh", f"Refreshed {gap_h / 24:.1f} days apart; {older} is older",
                                f"SLAs: {ma.refresh_sla_hours:.0f} h vs {mb.refresh_sla_hours:.0f} h"))

    # ---- mapping & units
    if ma.hierarchy_version and mb.hierarchy_version and ma.hierarchy_version != mb.hierarchy_version:
        out.append(_finding("mapping", f"Hierarchy mapping {ma.hierarchy_version} vs {mb.hierarchy_version}",
                            "Customers or products sit in different regions or categories."))
    if ma.currency and mb.currency and ma.currency != mb.currency:
        out.append(_finding("mapping", f"Reported in {ma.currency} vs {mb.currency}", "FX rate and conversion date matter."))
    return out


# ---------------------------------------------------------------- numeric bridge

def _value(d: Definition, vals: dict[str, float]) -> float | None:
    total = 0.0
    for t in d.terms:
        if t.is_constant:
            total += t.sign * float(t.column)
        elif t.is_simple and t.agg in (None, "SUM") and t.column in vals:
            total += t.sign * vals[t.column]
        else:
            return None
    return total


def _exclusion(store: Store, side: Side, period: str) -> list[tuple[str, float]]:
    out = []
    for fi in store.filter_impacts:
        if fi["period"] != period or fi["metric_id"] != side.metric_id:
            continue
        dash = fi.get("dashboard_id") or None
        if dash and dash != side.dashboard_id:
            continue
        out.append((fi["expression"], fi["excluded_value"]))
    return out


def _reported(store: Store, side: Side, period: str) -> float | None:
    for r in store.reported_values:
        if r["period"] == period and r["metric_id"] == side.metric_id and (r.get("dashboard_id") or None) == side.dashboard_id:
            return r["value"]
    if side.dashboard_id is None:
        # No dashboard context: use a dashboard that shows the metric as defined (no local override).
        for r in store.reported_values:
            dash = store.dashboards.get(r.get("dashboard_id") or "")
            if r["period"] == period and r["metric_id"] == side.metric_id and (
                    dash is None or side.metric_id not in dash.local_overrides):
                return r["value"]
    return None


def bridge(store: Store, a: Side, b: Side, period: str | None, causes: list[dict]) -> dict | None:
    if a.definition.kind != "additive" or b.definition.kind != "additive" or not store.component_values:
        return None
    ca_, cb_ = store.metrics[a.metric_id].currency, store.metrics[b.metric_id].currency
    if ca_ and cb_ and ca_ != cb_:
        return None  # different units: a numeric bridge would mislead
    period = period or max(store.component_values)
    vals = store.component_values.get(period, {})
    base_a, base_b = _value(a.definition, vals), _value(b.definition, vals)
    if base_a is None or base_b is None:
        return None
    excl_a, excl_b = _exclusion(store, a, period), _exclusion(store, b, period)
    model_a = base_a - sum(v for _, v in excl_a)
    model_b = base_b - sum(v for _, v in excl_b)

    steps: list[dict] = []
    rep_a, rep_b = _reported(store, a, period), _reported(store, b, period)
    hint = "; ".join(c["finding"] for c in causes if c["cause"] in ("mapping", "time_logic", "refresh")) or "no structural cause found"
    start = rep_a if rep_a is not None else model_a
    if rep_a is not None and abs(rep_a - model_a) > 0.05:
        steps.append({"label": f"Unexplained in {a.name}", "cause": "unexplained", "delta": round(model_a - rep_a, 2),
                      "note": f"Likely: {hint}", "key": "unexplained:a"})
    for expr, v in excl_a:
        steps.append({"label": f"Remove filter {expr}", "cause": "filters", "delta": round(v, 2), "key": f"flt:{expr}"})

    da, db = a.definition, b.definition
    ca, cb = _cols(da.base_terms), _cols(db.base_terms)
    if set(ca) != set(cb):
        delta = sum(vals[c] for c in set(cb) - set(ca)) - sum(vals[c] for c in set(ca) - set(cb))
        names = f"{', '.join(map(humanize, sorted(set(ca) - set(cb))))} → {', '.join(map(humanize, sorted(set(cb) - set(ca))))}"
        steps.append({"label": f"Base measure: {names}", "cause": "definition", "delta": round(delta, 2), "key": "base"})
    xa, xb = _cols(da.deduction_terms), _cols(db.deduction_terms)
    for col in sorted(set(xa) - set(xb)):
        cause = "late_adjustments" if col in LATE_ADJUSTMENT_COLUMNS else "definition"
        steps.append({"label": f"Add back {humanize(col)}", "cause": cause, "delta": round(vals[col], 2), "key": f"ded:{col}"})
    for col in sorted(set(xb) - set(xa), key=lambda c: (c in LATE_ADJUSTMENT_COLUMNS, c)):
        cause = "late_adjustments" if col in LATE_ADJUSTMENT_COLUMNS else "definition"
        steps.append({"label": f"Deduct {humanize(col)}", "cause": cause, "delta": round(-vals[col], 2), "key": f"ded:{col}"})
    for expr, v in excl_b:
        steps.append({"label": f"Apply filter {expr}", "cause": "filters", "delta": round(-v, 2), "key": f"flt:{expr}"})
    end = rep_b if rep_b is not None else model_b
    if rep_b is not None and abs(rep_b - model_b) > 0.05:
        steps.append({"label": f"Unexplained in {b.name}", "cause": "unexplained", "delta": round(rep_b - model_b, 2),
                      "note": f"Likely: {hint}", "key": "unexplained:b"})

    running = start
    for s in steps:
        running += s["delta"]
        s["running"] = round(running, 2)
    gap = end - start
    unexplained = sum(abs(s["delta"]) for s in steps if s["cause"] == "unexplained")
    explained_share = 1 - unexplained / abs(gap) if gap else 1.0
    return {
        "period": period,
        "unit": store.component_units.get(period, ""),
        "start": round(start, 2),
        "end": round(end, 2),
        "start_source": "reported" if rep_a is not None else "modelled",
        "end_source": "reported" if rep_b is not None else "modelled",
        "gap": round(gap, 2),
        "explained_share": round(max(0.0, explained_share), 3),
        "steps": steps,
        "closes": abs(running - end) < 0.05,
    }


def reconcile(store: Store, metric_a: str, metric_b: str, dashboard_a: str | None = None,
              dashboard_b: str | None = None, period: str | None = None) -> dict:
    for mid in (metric_a, metric_b):
        if mid not in store.metrics:
            raise KeyError(mid)
    a, b = _side(store, metric_a, dashboard_a), _side(store, metric_b, dashboard_b)
    causes = structural_causes(store, a, b)
    br = bridge(store, a, b, period, causes)
    if br:
        by_key = {s["key"]: s["delta"] for s in br["steps"]}
        for c in causes:
            if c["key"] in by_key:
                c["impact"] = round(by_key[c["key"]], 2)
        causes.sort(key=lambda c: -abs(c["impact"] or 0))
    return {
        "a": _side_dict(store, a),
        "b": _side_dict(store, b),
        "causes": causes,
        "cause_counts": {k: sum(c["cause"] == k for c in causes) for k in CAUSES if any(c["cause"] == k for c in causes)},
        "bridge": br,
        "summary": _summary(a, b, causes, br),
    }


def _side_dict(store: Store, s: Side) -> dict:
    m = store.metrics[s.metric_id]
    return {"metric_id": s.metric_id, "name": s.name, "dashboard_id": s.dashboard_id, "dashboard": s.dashboard,
            "formula": m.formula, "filters": s.filters, "definition": s.definition.to_dict(),
            "time_basis": m.time_basis, "calendar": m.calendar, "currency": m.currency,
            "hierarchy_version": m.hierarchy_version, "certification": m.certification}


def _fmt(x: float) -> str:
    return f"{x:,.1f}"


def _summary(a: Side, b: Side, causes: list[dict], br: dict | None) -> str:
    la = a.name + (f" on {a.dashboard}" if a.dashboard else "")
    lb = b.name + (f" on {b.dashboard}" if b.dashboard else "")
    if not causes:
        return f"{la} and {lb} share the same definition, filters, time logic and sources."
    kinds = sorted({c["label"].lower() for c in causes if c["cause"] != "unexplained"})
    if not br:
        return f"{la} and {lb} differ in {len(causes)} way(s): {', '.join(kinds)}."
    biggest = sorted((s for s in br["steps"] if s["cause"] != "unexplained"), key=lambda s: -abs(s["delta"]))[:3]
    parts = ", ".join(f"{s['label'][0].lower() + s['label'][1:]} {s['delta']:+,.1f}" for s in biggest)
    unexplained = round(sum(s["delta"] for s in br["steps"] if s["cause"] == "unexplained"), 1)
    tail = f" {abs(unexplained):,.1f} is unexplained and needs a look." if unexplained else " The bridge fully closes."
    return (f"{la} shows {_fmt(br['start'])} vs {lb} {_fmt(br['end'])} {br['unit']} in {br['period']} "
            f"(gap {br['gap']:+,.1f}). {br['explained_share']:.0%} of the gap is explained; largest drivers: {parts}.{tail}")
