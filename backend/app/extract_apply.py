"""Apply extracted BI metadata (metrics, dashboards, dbt lineage) to an engine. Pure: no I/O."""

from __future__ import annotations

from .engine import TrustEngine


def apply_extract(eng: TrustEngine, metrics: list[dict], dashboards: list[dict],
                  lineage: list[dict] | None = None, nodes: list[dict] | None = None) -> None:
    store = eng.store
    for n in nodes or []:
        store.node_names.setdefault(n["id"], (n["label"], n["name"]))
    existing = {(e.from_id, e.to_id, e.relation) for e in store.lineage}
    for row in lineage or []:
        key = (row["from_id"], row["to_id"], row["relation"])
        if key not in existing:  # re-uploading the same dbt project must not duplicate edges
            store.add_lineage(row)
            existing.add(key)
    for row in metrics:
        eng.store.add_metric(row)
    for row in dashboards:
        eng.store.add_dashboard(row)
