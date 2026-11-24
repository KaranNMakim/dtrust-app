"""Project the trust graph into Neo4j and read neighbourhoods back.

Postgres (or the in-memory store) is the system of record; Neo4j is a rebuildable
projection. `sync()` is idempotent: MERGE on id, then overwrite properties.

Run:  python -m app.neo4j_sync      (uses NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings, settings

log = logging.getLogger("decision_trust.neo4j")
CONSTRAINTS = Path(__file__).resolve().parents[2] / "infra" / "neo4j" / "constraints.cypher"
LABELS = {"Metric", "Dashboard", "Report", "DataProduct", "SourceSystem", "Model",
          "Recommendation", "Team", "GlossaryTerm"}
REL_TYPES = {"DEFINES", "CONSUMES", "CALCULATES", "DEPENDS_ON", "VALIDATES", "PRODUCES",
             "USES_EVIDENCE", "VARIANT_OF", "CERTIFIED_AS"}


class Neo4jGraph:
    def __init__(self, cfg: Settings = settings):
        from neo4j import GraphDatabase  # type: ignore

        self.cfg = cfg
        self.driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))

    def close(self) -> None:
        self.driver.close()

    def apply_constraints(self) -> None:
        if not CONSTRAINTS.exists():
            return
        stmts = [s.strip() for s in CONSTRAINTS.read_text().split(";") if s.strip() and not s.strip().startswith("//")]
        with self.driver.session() as s:
            for stmt in stmts:
                s.run(stmt)

    def sync(self, graph: dict) -> dict:
        ws = self.cfg.workspace_id
        by_label: dict[str, list[dict]] = {}
        for n in graph["nodes"]:
            if n["label"] in LABELS:
                props = {k: v for k, v in n.items() if v is not None and k not in ("label",)}
                props["workspace_id"] = ws
                by_label.setdefault(n["label"], []).append(props)
        by_type: dict[str, list[dict]] = {}
        for e in graph["edges"]:
            if e["type"] in REL_TYPES:
                props = {k: v for k, v in e.items() if k not in ("source", "target", "type") and v is not None}
                by_type.setdefault(e["type"], []).append({"s": e["source"], "t": e["target"], "props": props})
        with self.driver.session() as s:
            s.run("MATCH (n {workspace_id: $ws}) DETACH DELETE n", ws=ws)
            for label, rows in by_label.items():
                s.run(f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row", rows=rows)
            for rtype, rows in by_type.items():
                s.run(
                    f"UNWIND $rows AS row MATCH (a {{id: row.s, workspace_id: $ws}}) "
                    f"MATCH (b {{id: row.t, workspace_id: $ws}}) MERGE (a)-[r:{rtype}]->(b) SET r += row.props",
                    rows=rows, ws=ws,
                )
        counts = {"nodes": sum(len(v) for v in by_label.values()), "edges": sum(len(v) for v in by_type.values())}
        log.info("synced %s", counts)
        return counts

    def neighbourhood(self, node_id: str, depth: int = 2, limit: int = 500) -> dict:
        q = (
            "MATCH (c {id: $id, workspace_id: $ws}) "
            f"OPTIONAL MATCH p = (c)-[*1..{int(depth)}]-(n) "
            "WITH c, collect(DISTINCT n)[..$limit] AS ns, collect(p) AS ps "
            "UNWIND ps AS p UNWIND relationships(p) AS r "
            "WITH c, ns, collect(DISTINCT r) AS rs "
            "RETURN [c] + ns AS nodes, rs AS rels"
        )
        with self.driver.session() as s:
            rec = s.run(q, id=node_id, ws=self.cfg.workspace_id, limit=limit).single()
        if not rec:
            raise KeyError(node_id)
        nodes = [{**dict(n), "label": next(iter(n.labels))} for n in rec["nodes"]]
        edges = [{"source": r.start_node["id"], "target": r.end_node["id"], "type": r.type, **dict(r)}
                 for r in rec["rels"]]
        return {"center": node_id, "nodes": nodes, "edges": edges, "truncated": len(nodes) > limit}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from .engine import TrustEngine
    from .store import Store

    if not settings.neo4j_uri:
        raise SystemExit("Set NEO4J_URI (e.g. bolt://localhost:7687)")
    engine = TrustEngine(Store.from_dir(settings.data_dir), settings.now)
    g = Neo4jGraph()
    try:
        g.apply_constraints()
        print(g.sync(engine.graph))
    finally:
        g.close()


if __name__ == "__main__":
    main()
