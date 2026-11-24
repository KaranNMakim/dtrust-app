"""Export a governed metric to semantic-layer formats, so the fix lands where the metric is consumed.

- dbt MetricFlow: a semantic model plus simple, derived or ratio metrics
- Databricks Unity Catalog metric view YAML

The output is a starting point for an analytics engineer: entity keys, the physical
table name and the dimension list need review before merging. Header comments say so.
"""

from __future__ import annotations

import re

import yaml

from .definition import Definition, Term, parse
from .extractors.common import snake
from .store import Store


def _sql_agg(t: Term) -> str:
    """Our term syntax -> SQL. AGG(col WHERE cond) becomes AGG(col) FILTER (WHERE cond)."""
    col, cond = t.column, None
    m = re.match(r"(.+?)\s+WHERE\s+(.+)", col, flags=re.I)
    if m:
        col, cond = m.group(1).strip(), m.group(2).strip()
    if t.agg is None:
        expr = col
    elif t.agg == "COUNT_DISTINCT":
        expr = f"COUNT(DISTINCT {col})"
    elif col.endswith("_rows") and t.agg == "COUNT":
        expr = "COUNT(*)"
    elif t.agg == "COUNT" and _is_condition(col):
        expr = f"COUNT_IF({col})"
    else:
        expr = f"{t.agg}({col})"
    if cond:
        expr += f" FILTER (WHERE {cond})"
    return expr


def _is_condition(col: str) -> bool:
    return bool(re.search(r"\s(AND|OR)\s|[=<>]", col, flags=re.I))


def _sql_side(terms: list[Term]) -> str:
    out = ""
    for i, t in enumerate(terms):
        piece = _sql_agg(t)
        if i == 0:
            out = piece if t.sign > 0 else f"-{piece}"
        else:
            out += f" {'+' if t.sign > 0 else '-'} {piece}"
    return out


def sql_expression(d: Definition) -> str:
    if d.kind == "ratio":
        return f"({_sql_side(d.terms)}) / NULLIF({_sql_side(d.denominator)}, 0)"
    return _sql_side(d.terms)


def _filter_sql(filters: list[str]) -> str | None:
    return " AND ".join(filters) if filters else None


def _source_table(store: Store, metric_id: str) -> str:
    m = store.metrics[metric_id]
    return snake(store.name_of(m.data_product_id)) if m.data_product_id else "TODO_source_table"


def _dimensions(store: Store, metric_id: str, d: Definition) -> list[str]:
    m = store.metrics[metric_id]
    dims = []
    for f in d.filters:
        mm = re.match(r"([a-z_][a-z0-9_]*)", f)
        if mm and mm.group(1) not in dims:
            dims.append(mm.group(1))
    return dims


def to_dbt(store: Store, metric_id: str) -> str:
    m = store.metrics[metric_id]
    d = parse(m.formula)
    model = _source_table(store, metric_id)
    time_dim = m.time_basis or "metric_date"
    measures, simple_metrics, seen = [], [], set()

    def measure(t: Term) -> str:
        name = snake(t.column.split(" WHERE ")[0]) if t.agg else snake(t.column)
        if t.agg == "COUNT_DISTINCT":
            agg = "count_distinct"
        elif t.agg in ("SUM", "COUNT", "AVG", "MIN", "MAX"):
            agg = {"AVG": "average"}.get(t.agg, t.agg.lower())
        else:
            agg = "sum"
        cond = re.search(r"\s+WHERE\s+(.+)", t.column, flags=re.I)
        if cond:
            name = f"{name}_{snake(cond.group(1))}"[:60]
        if name not in seen:
            seen.add(name)
            col = t.column.split(" WHERE ")[0]
            expr = "1" if col.endswith("_rows") else col
            if t.agg == "COUNT" and _is_condition(col):
                name_fix = snake(re.sub(r"\s+(AND|OR)\s+", "_and_", col))[:60]
                seen.discard(name)
                name = name_fix
                seen.add(name)
                expr = f"case when {col} then 1 end"
            entry = {"name": name, "agg": agg, "expr": expr}
            if cond:
                entry["expr"] = f"case when {cond.group(1)} then {expr} end"
            measures.append(entry)
            simple_metrics.append({"name": f"{name}_total", "label": name.replace('_', ' ').title(),
                                   "type": "simple", "type_params": {"measure": name}})
        return f"{name}_total"

    metric_name = snake(m.name)
    filt = _filter_sql(d.filters)
    if d.kind == "ratio" and len(d.terms) == 1 and len(d.denominator) == 1:
        num, den = measure(d.terms[0]), measure(d.denominator[0])
        main = {"name": metric_name, "label": m.name, "type": "ratio",
                "type_params": {"numerator": num, "denominator": den}}
    else:
        refs = []
        expr_terms = d.terms + d.denominator
        for t in expr_terms:
            if not t.is_constant:
                refs.append(measure(t))
        expr = _expr_from_refs(d)
        main = {"name": metric_name, "label": m.name, "type": "derived",
                "type_params": {"expr": expr, "metrics": [{"name": r} for r in dict.fromkeys(refs)]}}
    if m.glossary_term_id and m.glossary_term_id in store.glossary:
        g = store.glossary[m.glossary_term_id]
        main["description"] = (g.definition if m.certification == "certified"
                               else f"Variant of '{g.term}'; not the certified definition. Review before publishing.")
    if filt:
        dims = _dimensions(store, metric_id, d)
        jinja = filt
        for dim in dims:
            jinja = re.sub(rf"\b{dim}\b", "{{ Dimension('" + model + "__" + dim + "') }}", jinja, count=1)
        main["filter"] = jinja
    main["meta"] = {"decision_trust": {"metric_id": m.id, "certification": m.certification,
                                       "owner": m.owner_email, "team": m.team}}
    doc = {
        "semantic_models": [{
            "name": model,
            "model": f"ref('{model}')",
            "defaults": {"agg_time_dimension": time_dim},
            "entities": [{"name": f"{model}_id", "type": "primary"}],
            "dimensions": [{"name": time_dim, "type": "time", "type_params": {"time_granularity": "day"}}]
            + [{"name": dim, "type": "categorical"} for dim in _dimensions(store, metric_id, d)],
            "measures": measures,
        }],
        "metrics": simple_metrics + [main],
    }
    header = (f"# Generated by Decision Trust from '{m.name}' ({m.certification}).\n"
              "# Review before merging: set the real primary entity, check the model ref and dimension names.\n")
    return header + yaml.safe_dump(doc, sort_keys=False, width=120)


def _expr_from_refs(d: Definition) -> str:
    def side(terms: list[Term]) -> str:
        out = ""
        for i, t in enumerate(terms):
            if t.is_constant:
                ref = t.column
            else:
                base = snake(t.column.split(" WHERE ")[0]) if t.agg else snake(t.column)
                cond = re.search(r"\s+WHERE\s+(.+)", t.column, flags=re.I)
                ref = (f"{base}_{snake(cond.group(1))}"[:60] if cond else base) + "_total"
            out += (ref if i == 0 and t.sign > 0 else f"{' ' if i else ''}{'+' if t.sign > 0 else '-'} {ref}")
        return out.strip()
    return f"({side(d.terms)}) / ({side(d.denominator)})" if d.kind == "ratio" else side(d.terms)


def to_databricks(store: Store, metric_id: str, catalog: str = "main", schema: str = "gold") -> str:
    m = store.metrics[metric_id]
    d = parse(m.formula)
    table = _source_table(store, metric_id)
    doc: dict = {"version": 0.1, "source": f"{catalog}.{schema}.{table}"}
    filt = _filter_sql(d.filters)
    if filt:
        doc["filter"] = filt
    dims = []
    if m.time_basis:
        dims.append({"name": m.time_basis.replace("_", " ").title(), "expr": m.time_basis})
    for dim in _dimensions(store, metric_id, d):
        dims.append({"name": dim.replace("_", " ").title(), "expr": dim})
    if dims:
        doc["dimensions"] = dims
    doc["measures"] = [{"name": m.name, "expr": sql_expression(d)}]
    header = (f"-- Generated by Decision Trust from '{m.name}' ({m.certification}).\n"
              f"-- Review the source table and the YAML version against your workspace before creating the view.\n"
              f"CREATE OR REPLACE VIEW {catalog}.{schema}.{snake(m.name)}_mv\nWITH METRICS\nLANGUAGE YAML\nAS $$\n")
    return header + yaml.safe_dump(doc, sort_keys=False, width=120) + "$$;\n"


FORMATS = {"dbt": (to_dbt, "yml"), "databricks": (to_databricks, "sql")}


def export(store: Store, metric_id: str, fmt: str) -> dict:
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    fn, ext = FORMATS[fmt]
    content = fn(store, metric_id)
    return {"format": fmt, "filename": f"{snake(store.metrics[metric_id].name)}.{ext}", "content": content}
