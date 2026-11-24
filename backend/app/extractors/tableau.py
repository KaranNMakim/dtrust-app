"""Tableau extractor: .twb (XML) or .twbx (zip) -> metric and dashboard rows.

Reads calculated fields from every datasource, resolves references between
calculations, translates the common aggregate syntax, and reads categorical
filters on each worksheet so that dashboard-level overrides become visible
(the "hidden filter" cause of disagreement).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

from .common import ExtractResult, metric_row, snake

_FIELD = re.compile(r"\[([^\]]+)\]")
_UNSUPPORTED = re.compile(r"\b(IF|CASE|FIXED|INCLUDE|EXCLUDE|WINDOW_\w+|RUNNING_\w+|LOOKUP)\b", re.I)


def _load(data: bytes, filename: str) -> ET.Element:
    if filename.lower().endswith(".twbx") or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            twb = next(n for n in z.namelist() if n.lower().endswith(".twb"))
            data = z.read(twb)
    return ET.fromstring(data)


def _field_name(col_ref: str) -> str:
    """'[ds].[none:Region:nk]' -> 'region'; '[Region]' -> 'region'."""
    last = col_ref.split("].[")[-1].strip("[]")
    parts = last.split(":")
    return snake(parts[1] if len(parts) >= 3 else parts[0])


def extract_tableau(data: bytes, filename: str, glossary: dict) -> ExtractResult:
    root = _load(data, filename)
    res = ExtractResult("tableau", filename)

    # 1. Calculated fields (internal name -> caption, formula)
    calcs: dict[str, tuple[str, str]] = {}
    for col in root.iter("column"):
        calc = col.find("calculation")
        if calc is None or not calc.get("formula"):
            continue
        internal = (col.get("name") or "").strip("[]")
        caption = col.get("caption") or internal
        calcs[internal] = (caption, calc.get("formula"))
    by_caption = {cap: f for cap, f in calcs.values()}

    def translate(formula: str, stack: list[str]) -> str:
        if _UNSUPPORTED.search(formula):
            res.warnings.append(f"[{stack[0]}] uses Tableau logic not yet normalised "
                                f"({_UNSUPPORTED.search(formula).group(0).upper()}); kept verbatim")

        def ref(m: re.Match) -> str:
            n = m.group(1)
            target = calcs.get(n, (None, None))[1] or by_caption.get(n)
            label = calcs.get(n, (n, None))[0]
            if target and label not in stack:
                return "(" + translate(target, stack + [label]) + ")"
            return snake(label)

        f = _FIELD.sub(ref, formula)
        f = re.sub(r"\bZN\s*\(([^()]*)\)", r"\1", f, flags=re.I)
        f = re.sub(r"\bCOUNTD\s*\(", "COUNT_DISTINCT(", f, flags=re.I)
        f = f.replace("==", "=").replace("!=", "<>")
        return re.sub(r"\s+", " ", f).strip()

    id_by_internal: dict[str, str] = {}
    for internal, (caption, formula) in calcs.items():
        # Only aggregate calculations are business metrics; row-level calcs are helpers.
        if not re.search(r"\b(SUM|AVG|COUNT|COUNTD|MIN|MAX|MEDIAN)\s*\(", formula, re.I):
            continue
        mid = "tab_" + snake(caption)
        id_by_internal[internal] = mid
        res.metrics.append(metric_row(mid, caption, translate(formula, [caption]), glossary,
                                      source_expression=re.sub(r"\s+", " ", formula).strip()))

    # 2. Worksheets: which metrics they show and which categorical filters they apply
    sheets: dict[str, dict] = {}
    for ws in root.iter("worksheet"):
        used = set()
        for dep in ws.iter("column"):
            n = (dep.get("name") or "").strip("[]")
            if n in id_by_internal:
                used.add(id_by_internal[n])
        for ci in ws.iter("column-instance"):
            n = (ci.get("column") or "").strip("[]")
            if n in id_by_internal:
                used.add(id_by_internal[n])
        filters = []
        for flt in ws.iter("filter"):
            if flt.get("class") != "categorical":
                continue
            field = _field_name(flt.get("column", ""))
            members, excluded = [], False
            for gf in flt.iter("groupfilter"):
                fn = gf.get("function")
                if fn == "except":
                    excluded = True
                if fn == "member" and gf.get("member"):
                    members.append(gf.get("member").strip('"'))
            if not members:
                continue
            if excluded and len(members) == 1:
                filters.append(f"{field}<>'{members[0]}'")
            elif excluded:
                filters.append(f"{field} NOT IN ({', '.join(repr(m) for m in members)})")
            elif len(members) == 1:
                filters.append(f"{field}='{members[0]}'")
            else:
                filters.append(f"{field} IN ({', '.join(repr(m) for m in members)})")
        sheets[ws.get("name", "")] = {"metrics": used, "filters": filters}

    # 3. Dashboards: union of their worksheets
    for db in root.iter("dashboard"):
        name = db.get("name", "Dashboard")
        zones = {z.get("name") for z in db.iter("zone") if z.get("name") in sheets}
        metrics: set[str] = set()
        per_metric: dict[str, list[str]] = {}
        for z in zones:
            metrics |= sheets[z]["metrics"]
            for mid in sheets[z]["metrics"]:
                per_metric.setdefault(mid, []).extend(sheets[z]["filters"])
        overrides = [f"{mid}:{' AND '.join(dict.fromkeys(fs))}" for mid, fs in per_metric.items() if fs]
        if metrics:
            res.dashboards.append({"dashboard_id": "tab_" + snake(name), "name": name, "tool": "Tableau",
                                   "audience": "department", "owner_email": "", "monthly_viewers": "0",
                                   "metrics": "|".join(sorted(metrics)),
                                   "local_overrides": "|".join(overrides)})
    if not calcs:
        res.warnings.append("No calculated fields found in this workbook.")
    return res
