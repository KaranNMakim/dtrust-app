-- Decision Trust v1 schema (Postgres 16 + pgvector). Mirrors backend/app/models.py.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE workspace (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE team (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), name TEXT NOT NULL, domain TEXT);
CREATE TABLE person (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id),
  email TEXT UNIQUE NOT NULL, display_name TEXT, team_id UUID REFERENCES team(id), is_active BOOLEAN DEFAULT true,
  role TEXT CHECK (role IN ('viewer','owner','steward','admin'))
);
CREATE TABLE ingestion_batch (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id),
  source_type TEXT CHECK (source_type IN ('dashboard','metric','data_product','lineage','recommendation','glossary')),
  connector TEXT, status TEXT DEFAULT 'pending', row_count INT, error_report JSONB, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE source_system (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), external_id TEXT, name TEXT NOT NULL, system_type TEXT);
CREATE TABLE data_product (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), external_id TEXT,
  name TEXT NOT NULL, owner_id UUID REFERENCES person(id), team_id UUID REFERENCES team(id), description TEXT,
  refresh_sla_hours INT DEFAULT 24, last_refreshed_at TIMESTAMPTZ
);
CREATE TABLE glossary_term (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), external_id TEXT,
  term TEXT NOT NULL, definition TEXT NOT NULL, steward_id UUID REFERENCES person(id),
  required_components TEXT[], synonyms TEXT[], embedding VECTOR(1024)
);
CREATE TABLE metric (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), external_id TEXT,
  name TEXT NOT NULL, canonical_name TEXT, formula TEXT NOT NULL, formula_ast JSONB, formula_hash TEXT, grain TEXT,
  owner_id UUID REFERENCES person(id), steward_id UUID REFERENCES person(id), team_id UUID REFERENCES team(id),
  glossary_term_id UUID REFERENCES glossary_term(id), data_product_id UUID REFERENCES data_product(id),
  certification TEXT DEFAULT 'none' CHECK (certification IN ('none','pending','certified','deprecated')),
  certified_by UUID REFERENCES person(id), certified_at TIMESTAMPTZ,
  refresh_sla_hours INT DEFAULT 24, last_refreshed_at TIMESTAMPTZ, embedding VECTOR(1024),
  batch_id UUID REFERENCES ingestion_batch(id)
);
CREATE INDEX ON metric (workspace_id, canonical_name);
CREATE INDEX ON metric USING hnsw (embedding vector_cosine_ops);
CREATE TABLE dashboard (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), external_id TEXT,
  name TEXT NOT NULL, tool TEXT, external_url TEXT, owner_id UUID REFERENCES person(id),
  audience TEXT CHECK (audience IN ('exec','department','team','personal')), monthly_viewers INT DEFAULT 0, last_refreshed_at TIMESTAMPTZ
);
CREATE TABLE dashboard_metric (
  dashboard_id UUID REFERENCES dashboard(id), metric_id UUID REFERENCES metric(id),
  local_formula TEXT, filters JSONB, PRIMARY KEY (dashboard_id, metric_id)
);
CREATE TABLE lineage_edge (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id),
  from_type TEXT, from_id UUID, to_type TEXT, to_id UUID,
  relation TEXT CHECK (relation IN ('DEPENDS_ON','CALCULATES','CONSUMES','VALIDATES','DEFINES')),
  documented BOOLEAN DEFAULT true, source TEXT
);
CREATE TABLE model (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), name TEXT NOT NULL, version TEXT, owner_id UUID REFERENCES person(id), model_type TEXT);
CREATE TABLE recommendation (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), external_id TEXT,
  model_id UUID REFERENCES model(id), title TEXT NOT NULL, rationale TEXT, raw_confidence NUMERIC(4,3),
  input_features JSONB, evidence JSONB, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE recommendation_outcome (recommendation_id UUID REFERENCES recommendation(id), accepted BOOLEAN, outcome_success BOOLEAN, recorded_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE business_rule (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), name TEXT, expression TEXT, severity TEXT);
CREATE TABLE trust_score (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id),
  entity_type TEXT CHECK (entity_type IN ('metric','recommendation','dashboard')), entity_id UUID NOT NULL,
  score NUMERIC(5,2) NOT NULL, zone TEXT CHECK (zone IN ('green','yellow','red')),
  components JSONB NOT NULL, penalties JSONB, cap JSONB, scoring_version TEXT NOT NULL, explanation TEXT,
  computed_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON trust_score (entity_type, entity_id, computed_at DESC);
CREATE TABLE conflict (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), rule_key TEXT,
  code TEXT CHECK (code IN ('C1','C2','C3','C4','C5')), severity TEXT CHECK (severity IN ('critical','warning','info')),
  title TEXT, entity_ids TEXT[], blast_radius INT,
  status TEXT DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')), detail JSONB,
  detected_at TIMESTAMPTZ DEFAULT now(), resolved_by UUID REFERENCES person(id), resolved_at TIMESTAMPTZ
);
CREATE TABLE audit_event (
  id BIGSERIAL PRIMARY KEY, workspace_id UUID REFERENCES workspace(id), actor_id UUID REFERENCES person(id),
  action TEXT, entity_type TEXT, entity_id TEXT, reason TEXT, payload JSONB, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE ask_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id UUID REFERENCES workspace(id), user_id UUID REFERENCES person(id),
  question TEXT, answer JSONB, cited_node_ids TEXT[], feedback SMALLINT, latency_ms INT, created_at TIMESTAMPTZ DEFAULT now()
);
