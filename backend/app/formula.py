"""Formula normalisation.

v1 uses a dialect-agnostic tokeniser: lowercase identifiers, strip whitespace, sort
commutative SUM terms. Two formulas that normalise to the same string get the same
hash and count as the same definition. A sqlglot / Claude-backed AST normaliser
plugs in behind `normalise()` for DAX and Tableau calcs (see docs/ROADMAP.md).
"""

from __future__ import annotations

import hashlib
import re

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KEYWORDS = {"sum", "count", "avg", "min", "max", "where", "and", "or", "not", "mape", "case", "when", "then", "else", "end"}


def tokens(formula: str) -> set[str]:
    """Identifiers used in a formula, lowercased. Aggregate keywords are kept apart."""
    found = {t.lower() for t in _IDENT.findall(formula)}
    return found


def data_tokens(formula: str) -> set[str]:
    """Identifiers that refer to data, i.e. without SQL keywords (MAPE is kept: it is a definition choice)."""
    return {t for t in tokens(formula) if t not in _KEYWORDS or t == "mape"}


def normalise(formula: str) -> str:
    f = re.sub(r"\s+", "", formula.lower())
    # Sort the additive terms of a top-level a-b-c chain so ordering does not create false variants.
    if "(" in f and re.fullmatch(r"[a-z0-9_()]+([+-][a-z0-9_()]+)*", f):
        parts = re.split(r"(?=[+-])", f)
        head, rest = parts[0], sorted(parts[1:])
        f = head + "".join(rest)
    return f


def formula_hash(formula: str) -> str:
    """Fingerprint of the parsed structure, so whitespace, brackets and term order don't create false variants."""
    from .definition import canonical

    try:
        key = canonical(formula)
    except Exception:  # noqa: BLE001 - unparseable formulas fall back to text
        key = normalise(formula)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def glossary_alignment(formula: str, required_components: list[str]) -> float:
    """Share of the glossary's required components that the formula uses (0..1)."""
    if not required_components:
        return 1.0
    have = data_tokens(formula)
    hits = sum(1 for c in required_components if c.lower() in have)
    return hits / len(required_components)
