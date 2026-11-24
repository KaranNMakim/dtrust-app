// Reference queries. The Python engine (backend/app/graph.py) implements the same logic in memory.

// 1. All variants of a business term with owners and consumers (Ask + C1)
MATCH (g:GlossaryTerm {id: $term_id})-[:DEFINES]->(m:Metric)
OPTIONAL MATCH (d)-[:CONSUMES]->(m)
OPTIONAL MATCH (t:Team)-[:DEFINES]->(m)
RETURN m.id, m.name, m.certification, m.trust_score, m.zone, t.name AS owner_team,
       collect(DISTINCT {dashboard: d.name, audience: d.audience}) AS consumers
ORDER BY m.certification = 'certified' DESC, m.trust_score DESC;

// 2. Lineage from a metric down to source systems, with documentation coverage
MATCH p = (dp:DataProduct)-[:CALCULATES]->(m:Metric {id: $metric_id})
MATCH q = (dp)-[:DEPENDS_ON*0..6]->(s:SourceSystem)
WITH q, relationships(q) AS rels
RETURN [n IN nodes(q) | n.name] AS path,
       CASE size(rels) WHEN 0 THEN 1.0 ELSE toFloat(size([r IN rels WHERE coalesce(r.documented, true)])) / size(rels) END AS coverage
ORDER BY coverage DESC LIMIT 5;

// 3. Circular lineage (C4)
MATCH p = (a:DataProduct)-[:DEPENDS_ON*2..8]->(a)
RETURN [n IN nodes(p) | n.name] AS cycle, length(p) AS hops;

// 4. Orphan metrics in use (C3)
MATCH (m:Metric)
WHERE NOT EXISTS { MATCH (:Team)-[r:DEFINES]->(m) WHERE r.owner_email IS NOT NULL }
OPTIONAL MATCH (d:Dashboard)-[:CONSUMES]->(m)
RETURN m.name, count(d) AS dashboards ORDER BY dashboards DESC;

// 5. Blast radius: dashboards and viewers a metric reaches
MATCH (d:Dashboard)-[:CONSUMES]->(m:Metric {id: $metric_id})
RETURN count(DISTINCT d) AS dashboards, sum(d.monthly_viewers) AS viewers;

// 6. Red zone spreading into executive dashboards
MATCH (m:Metric {zone: 'red'})<-[:CONSUMES]-(d:Dashboard {audience: 'exec'})
RETURN d.name AS exec_dashboard, collect(m.name) AS untrusted_metrics;
