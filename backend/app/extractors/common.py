"""Shared helpers for BI extractors: call parsing, naming, glossary suggestions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ExtractResult:
    tool: str
    source_name: str
    metrics: list[dict] = field(default_factory=list)      # rows for Store.add_metric
    dashboards: list[dict] = field(default_factory=list)   # rows for Store.add_dashboard
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"tool": self.tool, "source_name": self.source_name, "metrics": self.metrics,
                "dashboards": self.dashboards, "warnings": self.warnings}


def snake(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "_", name.strip())
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.strip("_").lower()


def find_call(expr: str, name: str, start: int = 0) -> tuple[int, int, list[str]] | None:
    """Locate NAME( ... ) (case-insensitive). Returns (start, end_exclusive, top-level args)."""
    m = re.compile(rf"\b{name}\s*\(", re.IGNORECASE).search(expr, start)
    if not m:
        return None
    depth, i, quote = 0, m.end() - 1, None
    args, buf = [], []
    for i in range(m.end() - 1, len(expr)):
        ch = expr[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'" and depth >= 1:
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(buf).strip())
                return m.start(), i + 1, [a for a in args if a != ""] if args != [""] else []
        elif ch == "," and depth == 1:
            args.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    return None


def suggest_term(name: str, glossary: dict) -> str | None:
    """Best glossary term whose term or synonym appears in the metric name."""
    low = name.lower()
    best, best_len = None, 0
    for g in glossary.values():
        for cand in [g.term.lower(), *g.synonyms]:
            if cand and re.search(rf"\b{re.escape(cand)}\b", low) and len(cand) > best_len:
                best, best_len = g.id, len(cand)
    return best


def metric_row(metric_id: str, name: str, formula: str, glossary: dict, **extra) -> dict:
    return {
        "metric_id": metric_id,
        "name": name,
        "formula": formula,
        "grain": extra.get("grain", "daily"),
        "owner_email": extra.get("owner_email", ""),
        "team": extra.get("team", ""),
        "glossary_term": suggest_term(name, glossary) or "",
        "data_product": extra.get("data_product", ""),
        "certification": "none",
        "refresh_sla_h": "24",
        "last_refreshed": extra.get("last_refreshed", ""),
        "time_basis": extra.get("time_basis", ""),
        "calendar": extra.get("calendar", ""),
        "currency": extra.get("currency", ""),
        "hierarchy_version": "",
        "description": extra.get("description", ""),
        "source_expression": extra.get("source_expression", ""),
    }
