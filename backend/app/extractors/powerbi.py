"""Power BI extractor: TMDL (.tmdl) or Tabular model JSON (model.bim) -> metric rows.

Supports the DAX patterns that carry most business definitions:
SUM / AVERAGE / COUNT / COUNTROWS / DISTINCTCOUNT, CALCULATE with filter arguments,
FILTER / KEEPFILTERS inside CALCULATE, DIVIDE, measure references ([Other Measure]),
Table[Column] references, && / || operators and comments. Anything else (VAR/RETURN,
iterators such as SUMX) is kept verbatim with a warning so nothing is silently lost.
"""

from __future__ import annotations

import json
import re

from .common import ExtractResult, find_call, metric_row, snake

_TABLE_COL = re.compile(r"'([^']+)'\[([^\]]+)\]|\b([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]")
_BARE_REF = re.compile(r"(?<![\w\]'])\[([^\]]+)\]")
_UNSUPPORTED = re.compile(r"\b(VAR|RETURN|SUMX|AVERAGEX|COUNTX|ALL|ALLEXCEPT|SAMEPERIODLASTYEAR|DATEADD|SWITCH|IF)\b", re.I)


def _strip_comments(expr: str) -> str:
    expr = re.sub(r"/\*.*?\*/", " ", expr, flags=re.S)
    return re.sub(r"//[^\n]*", " ", expr)


class _Dax:
    def __init__(self, measures: dict[str, str]):
        self.measures = measures  # name -> raw DAX
        self.warnings: list[str] = []

    def translate(self, name: str) -> tuple[str, list[str]]:
        filters: list[str] = []
        expr = self._expr(self.measures[name], filters, [name], top=True)
        filters = list(dict.fromkeys(filters))
        formula = expr + (" WHERE " + " AND ".join(filters) if filters else "")
        return formula, filters

    def _expr(self, raw: str, filters: list[str], stack: list[str], top: bool = False) -> str:
        e = _strip_comments(raw).strip()
        if _UNSUPPORTED.search(e):
            self.warnings.append(f"[{stack[0]}] uses DAX not yet normalised ({_UNSUPPORTED.search(e).group(0).upper()}); kept verbatim")
        e = _TABLE_COL.sub(lambda m: snake(m.group(2) or m.group(4)), e)

        def ref(m: re.Match) -> str:
            n = m.group(1)
            if n in self.measures:
                if n in stack:
                    self.warnings.append(f"Circular measure reference: {' -> '.join(stack + [n])}")
                    return snake(n)
                return "(" + self._expr(self.measures[n], filters, stack + [n]) + ")"
            return snake(n)

        e = _BARE_REF.sub(ref, e)
        e = e.replace("&&", " AND ").replace("||", " OR ").replace("==", "=")
        e = re.sub(r"\b(TRUE|FALSE)\s*\(\s*\)", r"\1", e, flags=re.I)
        e = re.sub(r"\bAVERAGE\s*\(", "AVG(", e, flags=re.I)
        e = re.sub(r"\bCOUNTROWS\s*\(\s*([A-Za-z_][\w ]*)\s*\)", lambda m: f"COUNT({snake(m.group(1))}_rows)", e, flags=re.I)
        e = re.sub(r"\bDISTINCTCOUNT\s*\(", "COUNT_DISTINCT(", e, flags=re.I)
        e = self._calls(e, filters, stack, top)
        e = re.sub(r"\s+", " ", e).strip()
        e = re.sub(r"\(\s*\(([^()]*)\)\s*\)", r"(\1)", e)
        return e

    def _calls(self, e: str, filters: list[str], stack: list[str], top: bool = False) -> str:
        while (c := find_call(e, "CALCULATE")):
            s, end, args = c
            inner = self._calls(args[0], filters, stack) if args else ""
            local = [x for f in args[1:] for x in self._filter(f, filters, stack)]
            outermost = top and e[:s].strip() == "" and e[end:].strip() == ""
            agg = re.fullmatch(r"\(*\s*([A-Z_]+)\s*\((.*)\)\s*\)*", inner.strip(), flags=re.S)
            if outermost or not local:
                filters.extend(local)
            elif agg and "(" not in agg.group(2):
                # Filter applies to this aggregate only: keep it local, e.g. COUNT(orders_rows WHERE on_time=TRUE)
                inner = f"{agg.group(1)}({agg.group(2).strip()} WHERE {' AND '.join(local)})"
            else:
                filters.extend(local)
                self.warnings.append(f"[{stack[0]}] CALCULATE filter on part of the expression was applied to the whole measure")
            e = e[:s] + inner + e[end:]
        while (c := find_call(e, "DIVIDE")):
            s, end, args = c
            num, den = (self._calls(a, filters, stack) for a in args[:2])
            e = e[:s] + f"({num})/({den})" + e[end:]
        return e

    def _filter(self, f: str, filters: list[str], stack: list[str]) -> list[str]:
        f = f.strip()
        if (c := find_call(f, "KEEPFILTERS")) and c[0] == 0:
            return self._filter(c[2][0], filters, stack)
        if (c := find_call(f, "FILTER")) and c[0] == 0:
            return self._filter(c[2][1], filters, stack) if len(c[2]) > 1 else []
        parts = re.split(r"\s+AND\s+", f, flags=re.I)
        out = []
        for p in parts:
            p = re.sub(r"\s*(<>|>=|<=|=|<|>)\s*", r"\1", p.strip()).replace('"', "'")
            m = re.match(r"(\w+)\s+IN\s*\{(.+)\}", p, flags=re.I)
            if m:
                p = f"{m.group(1)} IN ({m.group(2)})"
            out.append(p)
        return out


def _parse_tmdl(text: str) -> tuple[dict[str, str], dict[str, dict]]:
    measures: dict[str, str] = {}
    meta: dict[str, dict] = {}
    lines = text.splitlines()
    table, desc_buf, i = None, [], 0
    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if st.startswith("///"):
            desc_buf.append(st[3:].strip())
            i += 1
            continue
        m_tab = re.match(r"\s*table\s+'?([^'=]+?)'?\s*$", line)
        if m_tab:
            table = m_tab.group(1).strip()
            desc_buf = []
            i += 1
            continue
        m = re.match(r"(\s*)measure\s+('([^']+)'|([^\s=]+))\s*=\s*(.*)$", line)
        if not m:
            if st:
                desc_buf = []
            i += 1
            continue
        indent = len(m.group(1).replace("\t", "    "))
        name = m.group(3) or m.group(4)
        expr = m.group(5).strip()
        body: list[str] = [expr] if expr and expr != "```" else []
        fenced = expr == "```"
        props: dict[str, str] = {}
        i += 1
        while i < len(lines):
            nxt = lines[i]
            nst = nxt.strip()
            n_indent = len(nxt[: len(nxt) - len(nxt.lstrip())].replace("\t", "    "))
            if fenced:
                i += 1
                if nst == "```":
                    fenced = False
                    continue
                body.append(nst)
                continue
            if nst and n_indent <= indent:
                break
            pm = re.match(r"(formatString|displayFolder|lineageTag|description|dataCategory|isHidden)\s*[:=]\s*(.*)", nst)
            if pm:
                props[pm.group(1)] = pm.group(2).strip()
            elif nst.startswith(("annotation ", "changedProperty", "extendedProperty")):
                pass
            elif nst and not props:
                body.append(nst)
            i += 1
        measures[name] = "\n".join(body)
        meta[name] = {"table": table, "description": " ".join(desc_buf) or props.get("description", ""),
                      "folder": props.get("displayFolder", "")}
        desc_buf = []
    return measures, meta


def _parse_bim(text: str) -> tuple[dict[str, str], dict[str, dict]]:
    model = json.loads(text)
    model = model.get("model", model)
    measures, meta = {}, {}
    for t in model.get("tables", []):
        for ms in t.get("measures", []):
            expr = ms.get("expression", "")
            if isinstance(expr, list):
                expr = " ".join(expr)
            measures[ms["name"]] = expr
            meta[ms["name"]] = {"table": t.get("name"), "description": ms.get("description", ""),
                                "folder": ms.get("displayFolder", "")}
    return measures, meta


def extract_powerbi(text: str, filename: str, glossary: dict, dashboard_name: str | None = None,
                    hidden_prefixes: tuple[str, ...] = ("_",)) -> ExtractResult:
    if filename.lower().endswith((".bim", ".json")) or text.lstrip().startswith("{"):
        measures, meta = _parse_bim(text)
    else:
        measures, meta = _parse_tmdl(text)
    res = ExtractResult("powerbi", filename)
    dax = _Dax(measures)
    ids = []
    for name in measures:
        if name.startswith(hidden_prefixes):
            continue
        formula, _ = dax.translate(name)
        mid = "pbi_" + snake(name)
        ids.append(mid)
        res.metrics.append(metric_row(mid, name, formula, glossary,
                                      description=meta[name]["description"],
                                      source_expression=re.sub(r"\s+", " ", measures[name]).strip()))
    res.warnings.extend(dict.fromkeys(dax.warnings))
    if not measures:
        res.warnings.append("No measures found. Expecting a .tmdl file or model.bim JSON.")
    if dashboard_name and ids:
        res.dashboards.append({"dashboard_id": "pbi_" + snake(dashboard_name), "name": dashboard_name,
                               "tool": "Power BI", "audience": "department", "owner_email": "",
                               "monthly_viewers": "0", "metrics": "|".join(ids), "local_overrides": ""})
    return res
