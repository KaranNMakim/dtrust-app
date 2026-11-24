"""Conflict detection rules C1-C5 (see PRD section 1.6)."""

from __future__ import annotations

from collections import defaultdict

from . import formula as fx
from .graph import blast_radius, find_cycles, metrics_on_cycles
from .models import Conflict
from .store import Store

GLOSSARY_ALIGNMENT_THRESHOLD = 0.85
ORPHAN_CRITICAL_DASHBOARDS = 5


def _active(store: Store):
    return [m for m in store.metrics.values() if m.certification != "deprecated"]


def detect(store: Store, semantic_matcher=None) -> list[Conflict]:
    """Run all rules. `semantic_matcher(a, b) -> bool` optionally groups unlinked metrics (Claude-backed)."""
    out: list[Conflict] = []
    out += _c1_multiple_definitions(store, semantic_matcher)
    out += _c2_same_kpi_different_calc(store)
    out += _c3_orphans(store)
    out += _c4_cycles(store)
    out += _c5_glossary_drift(store)
    sev_rank = {"critical": 0, "warning": 1, "info": 2}
    out.sort(key=lambda c: (sev_rank.get(c.severity, 3), -c.blast_radius, c.id))
    return out


def _c1_multiple_definitions(store: Store, semantic_matcher) -> list[Conflict]:
    groups: dict[str, list] = defaultdict(list)
    for m in _active(store):
        if m.glossary_term_id:
            groups[m.glossary_term_id].append(m)
    # Metrics with no glossary link: optionally grouped by the semantic matcher.
    if semantic_matcher:
        loose = [m for m in _active(store) if not m.glossary_term_id]
        for m in loose:
            for term_id, members in groups.items():
                if any(semantic_matcher(m, other) for other in members):
                    members.append(m)
                    break

    out = []
    for term_id, members in groups.items():
        hashes = {m.formula_hash for m in members}
        if len(hashes) < 2:
            continue
        ids = [m.id for m in members]
        br = blast_radius(store, ids)
        exec_members = [m.id for m in members if any(d.audience == "exec" for d in store.consumers(m.id))]
        certified = [m.id for m in members if m.certification == "certified"]
        out.append(Conflict(
            id=f"C1-{term_id}",
            code="C1",
            severity="critical" if exec_members else "warning",
            title=f"{len(hashes)} definitions of {store.glossary[term_id].term}",
            entity_ids=ids,
            blast_radius=br["dashboards"],
            detail={
                "term_id": term_id,
                "variants": [{"metric_id": m.id, "name": m.name, "formula": m.formula,
                              "certification": m.certification} for m in members],
                "certified": certified,
                "on_exec_dashboards": exec_members,
                **br,
            },
        ))
    return out


def _c2_same_kpi_different_calc(store: Store) -> list[Conflict]:
    out = []
    for m in _active(store):
        overrides = [(d, d.local_overrides[m.id]) for d in store.consumers(m.id) if m.id in d.local_overrides]
        if not overrides:
            continue
        out.append(Conflict(
            id=f"C2-{m.id}",
            code="C2",
            severity="warning",
            title=f"{m.name} is calculated differently on {len(overrides)} dashboard(s)",
            entity_ids=[m.id] + [d.id for d, _ in overrides],
            blast_radius=len(overrides),
            detail={"overrides": [{"dashboard_id": d.id, "dashboard": d.name, "expression": e} for d, e in overrides]},
        ))
    return out


def _c3_orphans(store: Store) -> list[Conflict]:
    out = []
    for m in _active(store):
        if m.owner_email:
            continue
        used = store.consumers(m.id)
        out.append(Conflict(
            id=f"C3-{m.id}",
            code="C3",
            severity="critical" if len(used) > ORPHAN_CRITICAL_DASHBOARDS else "warning",
            title=f"{m.name} has no owner",
            entity_ids=[m.id],
            blast_radius=len(used),
            detail={"used_in": [d.name for d in used], "team": m.team},
        ))
    return out


def _c4_cycles(store: Store) -> list[Conflict]:
    cycles = find_cycles(store)
    on_cycle = metrics_on_cycles(store, cycles)
    out = []
    for i, cyc in enumerate(cycles, start=1):
        affected = [mid for mid, c in on_cycle.items() if c == cyc]
        br = blast_radius(store, affected)
        names = [store.name_of(n) for n in cyc] + [store.name_of(cyc[0])]
        out.append(Conflict(
            id=f"C4-cycle{i}",
            code="C4",
            severity="critical",
            title="Circular lineage: " + " → ".join(names),
            entity_ids=list(cyc) + affected,
            blast_radius=br["dashboards"],
            detail={"cycle": cyc, "cycle_names": names, "affected_metrics": affected, **br},
        ))
    return out


def _c5_glossary_drift(store: Store) -> list[Conflict]:
    out = []
    for m in _active(store):
        if not m.glossary_term_id:
            continue
        g = store.glossary[m.glossary_term_id]
        align = fx.glossary_alignment(m.formula, g.required_components)
        if align >= GLOSSARY_ALIGNMENT_THRESHOLD:
            continue
        missing = [c for c in g.required_components if c not in m.formula_tokens]
        out.append(Conflict(
            id=f"C5-{m.id}",
            code="C5",
            severity="warning",
            title=f"{m.name} drifts from the glossary definition of {g.term}",
            entity_ids=[m.id],
            blast_radius=len(store.consumers(m.id)),
            detail={"alignment": round(align, 2), "missing_components": missing,
                    "glossary_definition": g.definition},
        ))
    return out
