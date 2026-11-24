"""Graph algorithms over the in-memory store.

These mirror the Cypher queries in infra/neo4j/queries.cypher, so the product works
without Neo4j (demo, tests) and gives identical answers when Neo4j is attached.
"""

from __future__ import annotations

from collections import deque

from .models import LineageEdge
from .store import Store, model_node_id, team_id


def find_cycles(store: Store) -> list[list[str]]:
    """Distinct DEPENDS_ON cycles among data products, each as an ordered list of node ids."""
    adj = store.upstream_edges()
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()

    def dfs(start: str, node: str, path: list[str]) -> None:
        for e in adj.get(node, []):
            nxt = e.to_id
            if nxt == start and len(path) > 1:
                key = frozenset(path)
                if key not in seen:
                    seen.add(key)
                    cycles.append(path.copy())
            elif nxt not in path and len(path) < 8:
                path.append(nxt)
                dfs(start, nxt, path)
                path.pop()

    for start in sorted(adj):
        dfs(start, start, [start])
    return cycles


def upstream_closure(store: Store, data_product_id: str) -> tuple[list[LineageEdge], set[str]]:
    """All DEPENDS_ON edges reachable upstream of a data product, and the nodes visited."""
    adj = store.upstream_edges()
    edges: list[LineageEdge] = []
    visited = {data_product_id}
    q = deque([data_product_id])
    while q:
        n = q.popleft()
        for e in adj.get(n, []):
            edges.append(e)
            if e.to_id not in visited:
                visited.add(e.to_id)
                q.append(e.to_id)
    return edges, visited


def lineage_paths(store: Store, metric_id: str, limit: int = 5) -> list[dict]:
    """Paths from a metric down to source systems, with documentation coverage per path."""
    m = store.metrics[metric_id]
    if not m.data_product_id:
        return []
    adj = store.upstream_edges()
    results: list[dict] = []

    def walk(node: str, names: list[str], docs: list[bool], seen: set[str]) -> None:
        outs = adj.get(node, [])
        if not outs or store.label_of(node) == "SourceSystem":
            if store.label_of(node) == "SourceSystem":
                results.append({
                    "path": list(reversed(names)),
                    "coverage": round(sum(docs) / len(docs), 2) if docs else 1.0,
                    "documented": list(reversed(docs)),
                })
            return
        for e in outs:
            if e.to_id in seen:
                continue
            walk(e.to_id, names + [e.to_name], docs + [e.documented], seen | {e.to_id})

    walk(m.data_product_id, [m.name, store.name_of(m.data_product_id)], [True], {m.data_product_id})
    results.sort(key=lambda r: (-r["coverage"], len(r["path"])))
    return results[:limit]


def metrics_on_cycles(store: Store, cycles: list[list[str]]) -> dict[str, list[str]]:
    """metric_id -> the cycle it sits downstream of (via its data product)."""
    out: dict[str, list[str]] = {}
    cyc_nodes = [set(c) for c in cycles]
    for m in store.metrics.values():
        if not m.data_product_id:
            continue
        _, visited = upstream_closure(store, m.data_product_id)
        for c, nodes in zip(cycles, cyc_nodes):
            if nodes & visited:
                out[m.id] = c
                break
    return out


def blast_radius(store: Store, metric_ids: list[str]) -> dict:
    dashes = {d.id: d for mid in metric_ids for d in store.consumers(mid)}
    return {
        "dashboards": len(dashes),
        "viewers": sum(d.monthly_viewers for d in dashes.values()),
        "exec_dashboards": sum(1 for d in dashes.values() if d.audience == "exec"),
    }


def build_graph(store: Store, scores: dict[str, dict]) -> dict:
    """Whole trust graph as nodes + edges. `scores` maps entity id -> {score, zone}."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid: str, label: str, name: str, **extra) -> None:
        if nid not in nodes:
            s = scores.get(nid, {})
            nodes[nid] = {"id": nid, "label": label, "name": name,
                          "trust_score": s.get("score"), "zone": s.get("zone"), **extra}

    for g in store.glossary.values():
        node(g.id, "GlossaryTerm", g.term)
    for m in store.metrics.values():
        node(m.id, "Metric", m.name, certified=m.certification == "certified", certification=m.certification)
        if m.glossary_term_id:
            edges.append({"source": m.glossary_term_id, "target": m.id, "type": "DEFINES"})
        if m.team:
            tid = team_id(m.team)
            node(tid, "Team", m.team)
            edges.append({"source": tid, "target": m.id, "type": "DEFINES", "owner_email": m.owner_email})
        if m.data_product_id:
            node(m.data_product_id, "DataProduct", store.name_of(m.data_product_id))
            edges.append({"source": m.data_product_id, "target": m.id, "type": "CALCULATES", "documented": True})
    for d in store.dashboards.values():
        node(d.id, "Report" if d.tool.lower() == "report" else "Dashboard", d.name,
             audience=d.audience, monthly_viewers=d.monthly_viewers)
        for mid in d.metric_ids:
            edges.append({"source": d.id, "target": mid, "type": "CONSUMES",
                          "local_override": d.local_overrides.get(mid)})
    for e in store.lineage:
        node(e.from_id, e.from_type, e.from_name)
        node(e.to_id, e.to_type, e.to_name)
        edges.append({"source": e.from_id, "target": e.to_id, "type": e.relation, "documented": e.documented})
    for r in store.recommendations.values():
        mid = model_node_id(r.model, r.version)
        node(mid, "Model", f"{r.model} {r.version}".strip())
        node(r.id, "Recommendation", r.title, confidence=r.raw_confidence)
        edges.append({"source": mid, "target": r.id, "type": "PRODUCES"})
        for f in r.input_features:
            if f in store.metrics:
                edges.append({"source": mid, "target": f, "type": "CONSUMES"})
        for ev in r.evidence:
            if store.exists(ev):
                edges.append({"source": r.id, "target": ev, "type": "USES_EVIDENCE"})
    return {"nodes": list(nodes.values()), "edges": edges}


def neighbourhood(graph: dict, center: str, depth: int = 2, limit: int = 500) -> dict:
    adj: dict[str, set[str]] = {}
    for e in graph["edges"]:
        adj.setdefault(e["source"], set()).add(e["target"])
        adj.setdefault(e["target"], set()).add(e["source"])
    keep = {center}
    frontier = {center}
    for _ in range(depth):
        nxt = set()
        for n in frontier:
            nxt |= adj.get(n, set())
        nxt -= keep
        keep |= nxt
        frontier = nxt
    truncated = len(keep) > limit
    if truncated:
        keep = set(list(keep)[:limit]) | {center}
    nodes = [n for n in graph["nodes"] if n["id"] in keep]
    edges = [e for e in graph["edges"] if e["source"] in keep and e["target"] in keep]
    return {"center": center, "nodes": nodes, "edges": edges, "truncated": truncated}
