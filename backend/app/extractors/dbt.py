"""dbt extractor: manifest.json and/or semantic_manifest.json -> metrics, lineage and dashboards.

- Metrics come from the dbt Semantic Layer (MetricFlow): simple, ratio and derived metrics are
  translated into Decision Trust's formula syntax, with their where-filters. Cumulative and
  conversion metrics are kept verbatim with a warning.
- Lineage comes from manifest.json: every model's dependencies on other models and on sources.
  dbt-declared lineage counts as documented.
- Dashboards come from dbt exposures of type "dashboard" (owner, the metrics or models they use).

Works with either file alone; both together give the full picture.
"""

from __future__ import annotations

import json
import re

from .common import ExtractResult, metric_row, snake

AGG = {"sum": "SUM", "sum_boolean": "SUM", "count": "COUNT", "count_distinct": "COUNT_DISTINCT",
       "average": "AVG", "avg": "AVG", "min": "MIN", "max": "MAX", "median": "MEDIAN"}


def _jinja_to_sql(where: str) -> str:
    """{{ Dimension('order__region') }} != 'Exports'  ->  region<>'Exports'"""
    def ref(m: re.Match) -> str:
        name = m.group(2).split("__")[-1]
        return snake(name)

    s = re.sub(r"\{\{\s*(Dimension|TimeDimension|Entity|Metric)\(\s*'([^']+)'[^)]*\)(?:\.[a-z_]+\([^)]*\))*\s*\}\}", ref, where)
    s = s.replace("!=", "<>").replace('"', "'")
    s = re.sub(r"\s*(<>|>=|<=|=|<|>)\s*", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _filters(obj) -> list[str]:
    """MetricFlow filters appear as {"where_filters": [{"where_sql_template": ...}]}, a list, or a string."""
    if not obj:
        return []
    if isinstance(obj, str):
        return [_jinja_to_sql(obj)]
    if isinstance(obj, list):
        return [f for o in obj for f in _filters(o)]
    if isinstance(obj, dict):
        if "where_filters" in obj:
            return _filters(obj["where_filters"])
        if "where_sql_template" in obj:
            return [_jinja_to_sql(obj["where_sql_template"])]
    return []


def _ref_name(ref) -> tuple[str | None, list[str]]:
    """A measure or metric reference: 'name' or {"name": ..., "filter": ...}."""
    if isinstance(ref, str):
        return ref, []
    if isinstance(ref, dict):
        return ref.get("name"), _filters(ref.get("filter"))
    return None, []


def _model_name(sm: dict) -> str:
    rel = sm.get("node_relation") or {}
    if rel.get("alias"):
        return rel["alias"]
    m = re.search(r"ref\(\s*['\"]([^'\"]+)['\"]", sm.get("model") or "")
    return m.group(1) if m else sm.get("name", "model")


class _Translator:
    def __init__(self, semantic_models: list[dict], metrics: list[dict]):
        self.measures: dict[str, dict] = {}
        for sm in semantic_models:
            model = _model_name(sm)
            time_dim = (sm.get("defaults") or {}).get("agg_time_dimension")
            for ms in sm.get("measures") or []:
                self.measures[ms["name"]] = {**ms, "_model": model, "_time": ms.get("agg_time_dimension") or time_dim}
        self.metrics = {m["name"]: m for m in metrics}
        self.warnings: list[str] = []

    def measure_expr(self, name: str) -> tuple[str, str | None, str | None]:
        ms = self.measures.get(name)
        if not ms:
            self.warnings.append(f"Measure '{name}' isn't defined in the files provided")
            return f"SUM({snake(name)})", None, None
        agg = AGG.get((ms.get("agg") or "sum").lower())
        expr = (ms.get("expr") or ms["name"]).strip()
        col = snake(expr) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr) else re.sub(r"\s+", " ", expr)
        if col == "1" and agg == "SUM":
            agg, col = "COUNT", f"{snake(ms['_model'])}_rows"
        if not agg:
            self.warnings.append(f"Measure '{name}' uses aggregation '{ms.get('agg')}', kept as-is")
            return f"{ms.get('agg', 'agg').upper()}({col})", ms["_model"], ms["_time"]
        return f"{agg}({col})", ms["_model"], ms["_time"]

    def metric(self, name: str, stack: tuple[str, ...] = ()) -> tuple[str, list[str], str | None, str | None]:
        """Returns (expression, filters, model, time dimension)."""
        m = self.metrics.get(name)
        if not m:
            self.warnings.append(f"Metric '{name}' is referenced but not defined")
            return snake(name), [], None, None
        if name in stack:
            self.warnings.append(f"Circular metric reference: {' -> '.join(stack + (name,))}")
            return snake(name), [], None, None
        tp = m.get("type_params") or {}
        mtype = (m.get("type") or "simple").lower()
        filters = _filters(m.get("filter"))
        if mtype == "simple":
            mref, mfilt = _ref_name(tp.get("measure"))
            if mref:
                expr, model, time = self.measure_expr(mref)
            elif tp.get("agg"):  # newer YAML spec: simple metrics carry agg/expr directly
                col = tp.get("expr") or name
                expr, model, time = f"{AGG.get(tp['agg'].lower(), 'SUM')}({snake(col) if ' ' not in col else col})", None, None
            else:
                return snake(name), filters, None, None
            return expr, filters + mfilt, model, time
        if mtype == "ratio":
            num_name, num_f = _ref_name(tp.get("numerator"))
            den_name, den_f = _ref_name(tp.get("denominator"))
            n_expr, n_filt, model, time = self.metric(num_name, stack + (name,))
            d_expr, d_filt, _, _ = self.metric(den_name, stack + (name,))
            n_expr = self._local(n_expr, n_filt + num_f)
            d_expr = self._local(d_expr, d_filt + den_f)
            return f"({n_expr})/({d_expr})", filters, model, time
        if mtype == "derived":
            expr = tp.get("expr") or ""
            model = time = None
            for ref in tp.get("metrics") or []:
                rname, rfilt = _ref_name(ref)
                alias = ref.get("alias") if isinstance(ref, dict) else None
                if isinstance(ref, dict) and (ref.get("offset_window") or ref.get("offset_to_grain")):
                    self.warnings.append(f"[{m.get('label') or name}] uses a time offset; offset kept out of the formula")
                sub, sfilt, smodel, stime = self.metric(rname, stack + (name,))
                model, time = model or smodel, time or stime
                sub = self._local(sub, sfilt + rfilt)
                expr = re.sub(rf"\b{re.escape(alias or rname)}\b", f"({sub})", expr)
            return re.sub(r"\s+", " ", expr).strip(), filters, model, time
        self.warnings.append(f"[{m.get('label') or name}] is a {mtype} metric; kept verbatim")
        return snake(name), filters, None, None

    @staticmethod
    def _local(expr: str, filters: list[str]) -> str:
        """Filters on one part of a ratio/derived metric stay attached to that aggregate."""
        if not filters:
            return expr
        m = re.fullmatch(r"([A-Z_]+)\((.*)\)", expr.strip())
        if m and "(" not in m.group(2):
            return f"{m.group(1)}({m.group(2)} WHERE {' AND '.join(filters)})"
        return expr


def _load(data: bytes | str | dict | None) -> dict | None:
    if data is None or data == b"" or data == "":
        return None
    if isinstance(data, dict):
        return data
    try:
        doc = json.loads(data.decode("utf-8-sig") if isinstance(data, bytes) else data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("That file isn't a dbt artifact. Upload target/manifest.json and/or "
                         "target/semantic_manifest.json from your dbt project.") from exc
    if not isinstance(doc, dict) or not ({"nodes", "semantic_models", "metrics"} & set(doc)):
        raise ValueError("That JSON file doesn't look like a dbt artifact. Upload target/manifest.json and/or "
                         "target/semantic_manifest.json.")
    return doc


def classify(doc: dict) -> str:
    """'manifest' (has nodes) or 'semantic' (semantic_models/metrics only)."""
    return "manifest" if "nodes" in doc else "semantic"


def extract_dbt(files: list[tuple[str, bytes | str | dict]], glossary: dict) -> ExtractResult:
    docs = {}
    names = []
    for fname, data in files:
        doc = _load(data)
        if not doc:
            continue
        docs[classify(doc)] = doc
        names.append(fname)
    res = ExtractResult("dbt", " + ".join(names) or "dbt")
    manifest, semantic = docs.get("manifest"), docs.get("semantic")
    if not manifest and not semantic:
        res.warnings.append("No dbt artifacts found. Upload target/manifest.json and/or target/semantic_manifest.json.")
        return res

    # ---- semantic layer (semantic manifest preferred; manifest.json also carries it since dbt 1.6)
    if semantic:
        sms, mets = semantic.get("semantic_models") or [], semantic.get("metrics") or []
    else:
        sms = list((manifest.get("semantic_models") or {}).values())
        mets = list((manifest.get("metrics") or {}).values())
    tr = _Translator(sms, mets)
    metric_ids: dict[str, str] = {}
    for m in mets:
        expr, filters, model, time = tr.metric(m["name"])
        formula = expr + (" WHERE " + " AND ".join(dict.fromkeys(filters)) if filters else "")
        meta = m.get("meta") or (m.get("config") or {}).get("meta") or {}
        owner = meta.get("owner") or meta.get("owner_email") or ""
        if isinstance(owner, dict):
            owner = owner.get("email", "")
        mid = "dbt_" + snake(m["name"])
        metric_ids[m["name"]] = mid
        translated = formula != snake(m["name"])
        row = metric_row(
            mid, m.get("label") or m["name"], formula, glossary,
            owner_email=owner if "@" in str(owner) else "",
            team=meta.get("team", "") or meta.get("domain", ""),
            data_product=("dbt_" + snake(model)) if model else "",
            time_basis=snake(time) if time else "",
            description=m.get("description") or "",
            source_expression=json.dumps({"type": m.get("type"), "type_params": m.get("type_params")}, default=str)[:400],
        )
        if not translated:
            row["glossary_term"] = ""  # nothing structural to compare, so don't group it with a business definition
        res.metrics.append(row)
    res.warnings.extend(dict.fromkeys(tr.warnings))

    # ---- lineage + exposures from manifest.json
    if manifest:
        nodes = manifest.get("nodes") or {}
        sources = manifest.get("sources") or {}

        def node_ref(uid: str) -> tuple[str, str, str] | None:
            if uid in sources:
                s = sources[uid]
                sys_name = s.get("source_name") or s.get("database") or "source"
                label = sys_name.upper() if len(sys_name) <= 4 else sys_name.replace("_", " ").title()
                return "SourceSystem", "src_dbt_" + snake(sys_name), label
            n = nodes.get(uid)
            if n and n.get("resource_type") in ("model", "seed", "snapshot"):
                nm = n.get("alias") or n.get("name")
                return "DataProduct", "dbt_" + snake(nm), nm
            return None

        seen = set()
        for uid, n in nodes.items():
            if n.get("resource_type") not in ("model", "snapshot"):
                continue
            me = node_ref(uid)
            for dep in (n.get("depends_on") or {}).get("nodes") or []:
                up = node_ref(dep)
                if not up or (me[1], up[1]) in seen:
                    continue
                seen.add((me[1], up[1]))
                res.lineage.append({"from_type": me[0], "from_id": me[1], "from_name": me[2], "relation": "DEPENDS_ON",
                                    "to_type": up[0], "to_id": up[1], "to_name": up[2], "documented": "true"})
            res.nodes.append({"id": me[1], "label": me[0], "name": me[2]})

        for uid, ex in (manifest.get("exposures") or {}).items():
            if (ex.get("type") or "").lower() not in ("dashboard", "analysis", "application"):
                continue
            deps = (ex.get("depends_on") or {})
            used = []
            for dep in deps.get("metrics") or []:
                name = dep.split(".")[-1]
                if name in metric_ids:
                    used.append(metric_ids[name])
            if not used:  # fall back: metrics calculated by the models this exposure reads
                models = {node_ref(d)[1] for d in deps.get("nodes") or [] if node_ref(d)}
                used = [r["metric_id"] for r in res.metrics if r["data_product"] in models]
            if not used:
                continue
            owner = ex.get("owner") or {}
            res.dashboards.append({
                "dashboard_id": "dbt_" + snake(ex.get("name", uid)), "name": ex.get("label") or ex.get("name"),
                "tool": "dbt exposure", "audience": (ex.get("meta") or {}).get("audience", "department"),
                "owner_email": owner.get("email", "") if isinstance(owner, dict) else "",
                "monthly_viewers": str((ex.get("meta") or {}).get("monthly_viewers", 0)),
                "metrics": "|".join(dict.fromkeys(used)), "local_overrides": "",
            })
    else:
        res.warnings.append("Only the semantic manifest was provided, so lineage wasn't imported. "
                            "Add target/manifest.json to see where each metric's data comes from.")
    if not mets:
        res.warnings.append("No dbt Semantic Layer metrics found. Lineage was still imported.")
    return res
