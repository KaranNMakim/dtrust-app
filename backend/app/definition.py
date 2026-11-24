"""Structured metric definitions.

Turns a formula string into a comparable structure: additive terms with signs and
aggregations, or a ratio of two term lists, plus filters. Both the CSV formula
syntax and the output of the Power BI / Tableau extractors land here, so every
metric can be diffed term by term regardless of the tool it came from.

    SUM(invoice_amount)-SUM(returns) WHERE region<>'Exports'
    -> kind=additive, terms=[+SUM(invoice_amount), -SUM(returns)], filters=["region<>'Exports'"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_AGG = re.compile(r"^(SUM|COUNT|AVG|MIN|MAX|MAPE|DISTINCTCOUNT|COUNTD)\s*\((.*)\)$", re.IGNORECASE | re.DOTALL)
_SQL_WORDS = {"and", "or", "not", "in", "is", "null", "like", "between", "true", "false", "where"}

# Deductions that usually land weeks after the sale: treated as "late adjustments" when they differ.
LATE_ADJUSTMENT_COLUMNS = {"returns", "rebates", "refunds", "credit_notes", "chargebacks", "accruals"}


@dataclass
class Term:
    sign: int
    agg: str | None
    column: str  # the aggregated expression, normalised (identifier for simple measures)
    raw: str

    @property
    def is_simple(self) -> bool:
        return bool(re.fullmatch(r"[a-z_][a-z0-9_]*", self.column))

    @property
    def is_constant(self) -> bool:
        return bool(re.fullmatch(r"\d+(\.\d+)?", self.column)) and self.agg is None

    def key(self) -> str:
        return f"{(self.agg or '').upper()}({self.column})"


@dataclass
class Definition:
    raw: str
    kind: str  # additive | ratio
    terms: list[Term] = field(default_factory=list)  # additive, or numerator when ratio
    denominator: list[Term] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)

    @property
    def base_terms(self) -> list[Term]:
        return [t for t in self.terms if t.sign > 0 and not t.is_constant]

    @property
    def deduction_terms(self) -> list[Term]:
        return [t for t in self.terms if t.sign < 0 and not t.is_constant]

    def columns(self) -> set[str]:
        cols: set[str] = set()
        for t in self.terms + self.denominator:
            cols |= {c.lower() for c in _IDENT.findall(t.column) if c.lower() not in _SQL_WORDS}
        for f in self.filters:
            m = _IDENT.match(f.strip())
            if m:
                cols.add(m.group(0).lower())
        return cols

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "terms": [{"sign": t.sign, "agg": t.agg, "column": t.column} for t in self.terms],
            "denominator": [{"sign": t.sign, "agg": t.agg, "column": t.column} for t in self.denominator],
            "filters": self.filters,
        }


def _split_top(expr: str, seps: str) -> list[tuple[str, str]]:
    """Split on single-char separators at paren depth 0, outside quotes. Returns (sep_before, part)."""
    out, depth, buf, sep, quote = [], 0, [], "+", None
    for i, ch in enumerate(expr):
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif depth == 0 and ch in seps and (buf and "".join(buf).strip() or ch not in "+-"):
            # a leading sign (unary) stays with its term
            prev = "".join(buf).rstrip()
            if ch in "+-" and prev and prev[-1] in "*/(<>=,":
                buf.append(ch)
                continue
            out.append((sep, "".join(buf)))
            buf, sep = [], ch
        else:
            buf.append(ch)
    out.append((sep, "".join(buf)))
    return [(s, p.strip()) for s, p in out if p.strip()]


def _strip_parens(e: str) -> str:
    e = e.strip()
    while e.startswith("(") and e.endswith(")"):
        depth = 0
        for i, ch in enumerate(e):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(e) - 1:
                return e
        e = e[1:-1].strip()
    return e


def _top_where(formula: str) -> re.Match | None:
    for m in re.finditer(r"\s+WHERE\s+", formula, flags=re.IGNORECASE):
        head = formula[: m.start()]
        if head.count("(") == head.count(")"):
            return m
    return None


def _split_where(formula: str) -> tuple[str, list[str]]:
    m = _top_where(formula)
    if not m:
        return formula, []
    expr, cond = formula[: m.start()], formula[m.end():]
    parts = re.split(r"\s+AND\s+", cond, flags=re.IGNORECASE)
    return expr, [_norm_filter(p) for p in parts if p.strip()]


def _norm_filter(f: str) -> str:
    f = f.strip()
    f = re.sub(r"\s*(<>|!=|>=|<=|=|<|>)\s*", lambda m: "<>" if m.group(1) == "!=" else m.group(1), f)
    f = f.replace('"', "'")
    m = _IDENT.match(f)
    return (m.group(0).lower() + f[m.end():]) if m else f


def _norm_col(e: str) -> str:
    e = re.sub(r"\s+", " ", e.strip())
    return _IDENT.sub(lambda m: m.group(0) if m.group(0).lower() in _SQL_WORDS else m.group(0).lower(), e)


def _term(sign: str, part: str) -> Term:
    part = _strip_parens(part)
    s = -1 if sign == "-" else 1
    if part.startswith("-"):
        s, part = -s, part[1:].strip()
    m = _AGG.match(part)
    if m:
        agg = m.group(1).upper()
        agg = "COUNT_DISTINCT" if agg in ("DISTINCTCOUNT", "COUNTD") else agg
        return Term(s, agg, _norm_col(m.group(2).replace(";", ",")), part)
    return Term(s, None, _norm_col(part), part)


def _terms(expr: str, sign: int = 1) -> list[Term]:
    out: list[Term] = []
    for sep, part in _split_top(_strip_parens(expr), "+-"):
        s = sign * (-1 if sep == "-" else 1)
        inner = _strip_parens(part)
        if inner != part.strip() and len(_split_top(inner, "+-")) > 1 and len(_split_top(inner, "/")) == 1:
            out.extend(_terms(inner, s))  # flatten (a - b) groups
        else:
            t = _term("+", part)
            t.sign *= s
            out.append(t)
    return out


def canonical(formula: str) -> str:
    """Order-insensitive canonical form used for formula fingerprints."""
    d = parse(formula)

    def side(terms: list[Term]) -> str:
        return " ".join(sorted(f"{'+' if t.sign > 0 else '-'}{t.key()}" for t in terms))

    out = side(d.terms)
    if d.kind == "ratio":
        out = f"({out})/({side(d.denominator)})"
    if d.filters:
        out += " | " + " & ".join(sorted(d.filters))
    return out


def parse(formula: str) -> Definition:
    expr, filters = _split_where(formula.strip())
    expr = _strip_parens(expr)
    parts = _split_top(expr, "/")
    if len(parts) == 2:
        return Definition(formula, "ratio", _terms(parts[0][1]), _terms(parts[1][1]), filters)
    return Definition(formula, "additive", _terms(expr), [], filters)


def humanize(column: str) -> str:
    return column.replace("_", " ")
