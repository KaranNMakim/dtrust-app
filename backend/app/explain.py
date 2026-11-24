"""Explain an issue in plain business language: what's wrong, where it comes from, why it matters,
and what fixing it would change. Powers the issue cards and the guided "Fix this" flow."""

from __future__ import annotations

import re

from .definition import parse
from .graph import blast_radius, upstream_closure
from .migration import plan as migration_plan
from .reconcile import reconcile

TYPE_LABEL = {
    "C1": "Same name, different formulas",
    "C2": "Calculated differently on some dashboards",
    "C3": "Nobody owns this metric",
    "C4": "Data loops back on itself",
    "C5": "Doesn't match the official definition",
}

_AGG_WORDS = {"COUNT": "number of {}", "COUNT_DISTINCT": "number of distinct {}", "AVG": "average {}",
              "MIN": "lowest {}", "MAX": "highest {}", "MAPE": "forecast error (MAPE) of {}"}


_ID = re.compile(r"\b(?:m|d|g|dp|src|pbi|tab)_[a-z0-9_]+\b")


def _words(text: str) -> str:
    """Underscores to spaces, except inside metric ids, which the display-name pass turns into names."""
    text = re.sub(r"_rows\b", "", text)
    parts = _ID.split(text)
    ids = _ID.findall(text)
    out = parts[0].replace("_", " ")
    for i, part in enumerate(parts[1:]):
        out += ids[i] + part.replace("_", " ")
    out = out.replace("=TRUE", "").replace("= TRUE", "")
    return re.sub(r"\s+", " ", out).strip()


def plain_filter(f: str) -> str:
    m = re.match(r"\s*([a-z_][a-z0-9_]*)\s*(<>|!=|=)\s*'?([^']*)'?\s*$", f, flags=re.I)
    if m:
        field, op, val = _words(m.group(1)), m.group(2), m.group(3)
        return f"excludes {field} {val}" if op in ("<>", "!=") else f"only {field} {val}"
    m = re.match(r"\s*([a-z_][a-z0-9_]*)\s+(NOT\s+)?IN\s*\((.+)\)\s*$", f, flags=re.I)
    if m:
        vals = ", ".join(v.strip(" '\"") for v in m.group(3).split(","))
        return f"{'excludes' if m.group(2) else 'only'} {_words(m.group(1))} {vals}"
    return _words(f)


def plain_formula(formula: str) -> str:
    """'SUM(invoice_amount)-SUM(returns)' -> 'invoice amount − returns'."""
    try:
        d = parse(formula)
    except Exception:  # noqa: BLE001
        return _words(formula)

    def term(t) -> str:
        col = t.column
        cond = None
        mm = re.match(r"(.+?)\s+WHERE\s+(.+)", col, flags=re.I)
        if mm:
            col, cond = mm.group(1), mm.group(2)
        base = _words(col)
        if t.agg in _AGG_WORDS:
            base = _AGG_WORDS[t.agg].format(base or "orders")
        if cond:
            base += f" where {_words(cond).replace(' AND ', ' and ')}"
        return base.replace(" AND ", " and ")

    def side(terms) -> str:
        out = ""
        for i, t in enumerate(terms):
            w = term(t)
            out += w if i == 0 and t.sign > 0 else (f" {'+' if t.sign > 0 else '−'} {w}" if i else f"−{w}")
        return out.strip()

    text = f"({side(d.terms)}) ÷ ({side(d.denominator)})" if d.kind == "ratio" else side(d.terms)
    if d.filters:
        text += " · " + "; ".join(plain_filter(f) for f in d.filters)
    return text


def _sources(engine, metric_id: str) -> list[str]:
    m = engine.store.metrics[metric_id]
    if not m.data_product_id:
        return []
    _, visited = upstream_closure(engine.store, m.data_product_id)
    return sorted(engine.store.name_of(n) for n in visited if engine.store.label_of(n) == "SourceSystem")


def _metric_row(engine, metric_id: str, recommended: bool = False) -> dict:
    s = engine.store
    m = s.metrics[metric_id]
    return {
        "metric_id": m.id,
        "name": m.name,
        "formula_plain": plain_formula(m.formula),
        "owner": m.owner_email,
        "team": m.team,
        "source_systems": _sources(engine, m.id),
        "dashboards": [d.name for d in s.consumers(m.id)],
        "trust_score": engine.metric_scores[m.id].score,
        "approved": m.certification == "certified",
        "recommended": recommended,
    }


def _impact(engine, metric_ids: list[str]) -> dict:
    br = blast_radius(engine.store, [m for m in metric_ids if m in engine.store.metrics])
    exec_names = sorted({d.name for mid in metric_ids if mid in engine.store.metrics
                         for d in engine.store.consumers(mid) if d.audience == "exec"})
    return {"dashboards": br["dashboards"], "exec_dashboards": br["exec_dashboards"],
            "viewers": br["viewers"], "exec_dashboard_names": exec_names}


def impact_for(engine, conflict) -> dict:
    return _impact(engine, [e for e in conflict.entity_ids if e in engine.store.metrics])


def _severity_reason(conflict, impact: dict) -> str:
    if conflict.code == "C4":
        return "A data loop can quietly corrupt every number that depends on it."
    if conflict.severity == "critical":
        if impact["exec_dashboards"]:
            return "Shown on executive dashboards, so leaders may be acting on it."
        return "Used on many dashboards, so the risk spreads widely."
    return "Not on executive dashboards yet, but it erodes trust over time."


def _gap(engine, metric_ids: list[str], canonical_id: str) -> dict | None:
    """Find a pair of reported dashboard numbers to show how big the disagreement is."""
    s = engine.store
    reported = {(r["metric_id"], r.get("dashboard_id") or None) for r in s.reported_values}
    canon_dash = [d for (m, d) in reported if m == canonical_id]
    variants = sorted((m for m in metric_ids if m != canonical_id and m in s.metrics),
                      key=lambda m: -sum(d.audience == "exec" for d in s.consumers(m)))
    for v in variants:
        for (m, d) in reported:
            if m != v:
                continue
            for cd in canon_dash:
                try:
                    r = reconcile(s, v, canonical_id, d, cd)
                except (KeyError, ValueError):
                    continue
                br = r["bridge"]
                if br:
                    la = r["a"]["dashboard"] or r["a"]["name"]
                    lb = r["b"]["dashboard"] or r["b"]["name"]
                    return {"a_label": la, "a_value": br["start"], "b_label": lb, "b_value": br["end"],
                            "unit": br["unit"], "gap": br["gap"], "explained_share": br["explained_share"],
                            "metric_a": v, "metric_b": canonical_id, "dashboard_a": d, "dashboard_b": cd}
    return None


def _fmt(x: float) -> str:
    return f"{x:,.1f}"


def explain(engine, conflict_id: str) -> dict:
    c = next((x for x in engine.conflicts if x.id == conflict_id), None)
    if not c:
        raise KeyError(conflict_id)
    s = engine.store
    impact = impact_for(engine, c)
    out = {
        "id": c.id, "code": c.code, "type_label": TYPE_LABEL.get(c.code, "Data issue"), "title": c.title,
        "severity": c.severity, "severity_label": "Urgent" if c.severity == "critical" else "Should fix",
        "severity_reason": _severity_reason(c, impact), "status": c.status, "impact": impact,
        "sources": [], "visual": None, "gap": None, "fix": None, "effect": None,
    }
    plan = migration_plan(engine, c.id)
    out["checklist"] = [{"title": st["title"], "owner": st.get("owner"), "detail": st.get("detail")}
                        for st in plan.get("steps", [])]

    if c.code == "C1":
        canon_id = plan["canonical"]["metric_id"]
        term = plan["term"]
        members = [m for m in c.entity_ids if m in s.metrics]
        out["what"] = (f"{len(members)} metrics are all called '{term}', but each uses a different formula. "
                       f"People quoting '{term}' in the same meeting can be quoting different numbers.")
        out["sources"] = [_metric_row(engine, canon_id, True)] + [_metric_row(engine, m) for m in members if m != canon_id]
        out["gap"] = _gap(engine, members, canon_id)
        variants = [{"metric_id": v["metric_id"], "name": v["name"],
                     "action": "rename" if v["action"]["type"] == "rename" else "retire",
                     "why": v["why"],
                     "term": v["action"].get("body", {}).get("term"),
                     "definition": v["action"].get("body", {}).get("definition"),
                     "new_name": v["action"].get("body", {}).get("new_name"),
                     "dashboards": [d.name for d in s.consumers(v["metric_id"])]}
                    for v in plan["variants"]]
        out["fix"] = {"kind": "choose_definition", "recommended_id": canon_id,
                      "recommended_reason": _canon_reason(engine, canon_id),
                      "candidates": [{"metric_id": r["metric_id"], "name": r["name"], "trust_score": r["trust_score"],
                                      "approved": r["approved"]} for r in out["sources"]],
                      "variants": variants}
        preview = engine.preview_fix(c.id, canon_id, [{"metric_id": v["metric_id"], "action": v["action"],
                                                       "term": v["term"], "definition": v["definition"],
                                                       "new_name": v["new_name"]} for v in variants])
        out["effect"] = preview

    elif c.code == "C2":
        m = s.metrics[c.entity_ids[0]]
        rows = c.detail.get("overrides", [])
        out["what"] = (f"{m.name} has one official formula, but {len(rows)} dashboard(s) quietly change it. "
                       "The tile label stays the same, so nobody can tell.")
        out["sources"] = [_metric_row(engine, m.id, True)]
        out["visual"] = {"kind": "overrides", "metric": m.name,
                         "rows": [{"dashboard": r["dashboard"], "change": plain_filter(r["expression"]).capitalize()}
                                  for r in rows]}
        out["fix"] = {"kind": "confirm", "label": "I've removed the filter or published it as its own metric"}

    elif c.code == "C3":
        m = s.metrics[c.entity_ids[0]]
        steward = s.glossary[m.glossary_term_id].steward_email if m.glossary_term_id and m.glossary_term_id in s.glossary else None
        dash_owners = [d.owner_email for d in s.consumers(m.id) if d.owner_email]
        suggested = steward or (max(set(dash_owners), key=dash_owners.count) if dash_owners else None)
        out["what"] = (f"{m.name} has no named owner. If it's wrong, nobody is responsible for fixing it, "
                       "and nobody can approve changes to it.")
        out["sources"] = [_metric_row(engine, m.id)]
        out["visual"] = {"kind": "orphan", "metric": m.name, "team": m.team,
                         "dashboards": [d.name for d in s.consumers(m.id)], "suggested_owner": suggested}
        out["fix"] = {"kind": "assign_owner", "suggested_owner": suggested}
        if suggested:
            out["effect"] = engine.preview_fix(c.id, owner_email=suggested)

    elif c.code == "C4":
        cyc = c.detail.get("cycle", [])
        edges = []
        for i, node in enumerate(cyc):
            nxt = cyc[(i + 1) % len(cyc)]
            e = next((e for e in s.lineage if e.from_id == node and e.to_id == nxt), None)
            edges.append({"from": s.name_of(node), "to": s.name_of(nxt), "documented": bool(e and e.documented)})
        affected = [s.name_of(m) for m in c.detail.get("affected_metrics", [])]
        out["what"] = ("These data products feed each other in a circle, so a change anywhere in the loop can ripple "
                       "back and change numbers unpredictably.")
        out["sources"] = [_metric_row(engine, m) for m in c.detail.get("affected_metrics", []) if m in s.metrics]
        out["visual"] = {"kind": "loop", "nodes": [s.name_of(n) for n in cyc], "edges": edges, "affected": affected}
        out["fix"] = {"kind": "confirm", "label": "Our data team has removed the link that closes the loop"}

    elif c.code == "C5":
        m = s.metrics[c.entity_ids[0]]
        g = s.glossary.get(m.glossary_term_id) if m.glossary_term_id else None
        missing = [_words(x) for x in c.detail.get("missing_components", [])]
        out["what"] = (f"{m.name} is labelled '{g.term if g else 'this term'}' but leaves out part of the official "
                       f"definition: {', '.join(missing) or 'some components'}.")
        out["sources"] = [_metric_row(engine, m.id)]
        out["visual"] = {"kind": "drift", "metric": m.name, "official": g.definition if g else None,
                         "term": g.term if g else None, "formula_plain": plain_formula(m.formula), "missing": missing}
        out["fix"] = {"kind": "confirm", "label": "The formula now matches the official definition, or the metric has been renamed"}

    out["why"] = _why_sentence(out)
    return out


def _canon_reason(engine, metric_id: str) -> str:
    m = engine.store.metrics[metric_id]
    parts = []
    if m.certification == "certified":
        parts.append(f"approved by {m.team or 'its owner'}")
    src = _sources(engine, metric_id)
    if src:
        parts.append(f"traced to {', '.join(src)}")
    parts.append(f"trust score {engine.metric_scores[metric_id].score:.0f}")
    return "It's " + ", ".join(parts) + "."


def _why_sentence(e: dict) -> str:
    imp = e["impact"]
    bits = [f"Shown on {imp['dashboards']} dashboard{'s' if imp['dashboards'] != 1 else ''}"]
    if imp["exec_dashboards"]:
        bits.append(f"{imp['exec_dashboards']} of them executive ({', '.join(imp['exec_dashboard_names'])})")
    bits.append(f"seen by about {imp['viewers']:,} people a month")
    text = ", ".join(bits) + "."
    g = e.get("gap")
    if g:
        text += (f" Right now {g['a_label']} shows {_fmt(g['a_value'])} while {g['b_label']} shows "
                 f"{_fmt(g['b_value'])} {g['unit']}, a gap of {_fmt(abs(g['gap']))}.")
    return text
