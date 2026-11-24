# Decision Trust

**Why don't these two numbers agree, and which one should I trust?** Decision Trust reads metric definitions straight from Power BI and Tableau, explains every difference between two dashboard numbers with a numeric bridge, scores each metric and AI recommendation 0–100 with evidence, and turns conflicts into migration plans that publish the winning definition to your semantic layer.

> Spec (PRD, user stories, schemas, API, architecture, 4-week plan, monetization): [Decision Trust — MVP v1 Spec](https://claude.ai/artifact/AkUngCL9t73e5HqNqYwfU1)

## What it does

### The core loop: discover → reconcile → decide → publish

| Step | Capability | How |
| --- | --- | --- |
| **Discover** | **BI extractors** | Power BI TMDL / `model.bim` (DAX measures, `CALCULATE` filters, `DIVIDE`, measure references) and Tableau `.twb` / `.twbx` (calculated fields, worksheet filters, dashboards) become governed metrics. Duplicates are detected by structure, not text. |
| **Reconcile** | **Reconciliation engine** | Pick two tiles. Every difference is classified into seven causes: definition, hidden filters, time logic, source, refresh, mappings and units, late adjustments. With component values loaded, a numeric bridge walks from number A to number B and shows the unexplained remainder. |
| **Decide** | **Migration plans** | Each conflict becomes a plan: the canonical metric, which variants to *rename* (e.g. Sales "revenue" → Bookings) and which to deprecate, affected executive dashboards, and the sequence: restate, run side by side, re-baseline targets, retire. One click executes the action. |
| **Publish** | **Semantic-layer export** | The certified definition exports as dbt MetricFlow YAML or a Databricks metric view, so the fix lands where every tool and AI agent reads it. |

### Trust scoring

| Capability | How |
| --- | --- |
| **Metric Trust Score** | Definition consistency 30%, ownership 20%, lineage 20%, usage consistency 15%, freshness 15%, minus conflict penalties |
| **Recommendation Trust Score** | Explainability 25%, calibrated confidence 15%, input data quality 25%, historical accuracy 20%, business-rule compliance 15%. Capped at weakest input metric + 20 |
| **Conflict detection** | C1 multiple definitions · C2 same KPI, different calculation · C3 orphan metric · C4 circular lineage · C5 glossary drift |
| **Trust Graph** | Sources → data products → metrics → dashboards → models → recommendations, coloured green / yellow / red |
| **Ask** | "Which revenue should I trust?" and "Why does Sales QBR revenue differ from the Board Pack?", answered from graph facts only, with citations |
| **Calibration** | Backtests the score against an incident log (restatements, executive disputes, wrong decisions): AUC per component and evidence-based weight suggestions, shrunk towards current weights |

**Design rule: Claude never sets a score.** Scores are pure, deterministic Python with evidence per component. Claude (optional) classifies questions, writes explanations, and phrases answers from the retrieved subgraph.

## Quick start

### Backend only (no Docker, no API keys)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                       # 67 tests
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

```bash
curl -s -X POST localhost:8000/api/v1/ask \
  -H 'content-type: application/json' \
  -d '{"question":"Which revenue metric should I trust?"}' | jq
```

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev   # http://localhost:3000
```

### Full stack (Neo4j + Postgres + API + web)

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY to turn on Claude
docker compose up --build
```

Neo4j Browser: http://localhost:7474 (neo4j / decisiontrust). The API projects the graph into Neo4j on start and after every change; `python -m app.neo4j_sync` re-syncs manually.

## The demo in four questions

1. **"Why does Sales QBR revenue differ from the Board Pack?"** (Ask or `/reconcile`) → 1,258.3 vs 1,128.0 INR crore. Bookings vs invoices −76.0, Exports filter hidden on the QBR +64.0, discounts −52.0, returns −38.5, rebates −21.5. **95% explained**; the last 6.3 traces to a stale hierarchy mapping (h2026.1 vs h2026.2).
2. **"Which revenue metric should I trust?"** → Net Revenue (Finance), certified, owned by Group Finance BI, traced to SAP, score 93, with the four rival definitions and what's wrong with each.
3. **Conflict queue → Migration plan for "5 definitions of Revenue"** → rename Revenue (Sales) to **Bookings** (it measures a different event), deprecate Revenue APAC (same concept, missing deductions), and touch 10 dashboards, 4 of them executive. Executing all four actions closes the revenue conflict and lifts the Enterprise Trust Index from 56 to 67.
4. **Metric page → Publish to dbt MetricFlow** → a ready-to-review YAML with the derived metric, measures, time dimension and owner metadata.

Upload `backend/data/samples/acme_finance.tmdl` (Power BI) or `acme_sales.twb` (Tableau) on the Ingest page to watch new metrics flow straight into the conflict queue.

## Demo data: Acme Consumer Goods

`backend/data/acme/` holds a fictional CPG company with 14 metrics, 12 dashboards, 7 data products, 5 source systems, 3 models and 6 recommendations. Every conflict type is seeded deliberately.

| Metric | Score | Zone | Why |
| --- | --- | --- | --- |
| Gross Margin % (Finance) | 94 | green | Certified, full lineage |
| Net Revenue (Finance) | 93 | green | Certified, documented to SAP, fresh |
| OTIF | 77 | yellow | Certified, but its data product sits on a lineage cycle |
| Forecast Accuracy | 73 | yellow | Downstream of the Supply → RGM → Demand cycle |
| Distributor Churn | 70 | yellow | Rival churn definition, undocumented Salesforce hop |
| Revenue APAC | 67 | yellow | Omits discounts and rebates |
| Net Sales (eCom) | 67 | yellow | Different source and formula |
| Trade Spend %, Promo ROI | 57 | yellow | On the lineage cycle, no glossary term |
| Revenue (Sales) | 47 | red | Bookings shown as revenue, override in Sales QBR |
| OTIF (Customer Service) | 44 | red | Ignores "in full", shown to execs |
| Churn Rate (Marketing) | 36 | red | No owner, 60 vs 90 days, stale |
| Gross Revenue (Marketing) | 33 | red | No owner, gross of returns, stale, on Ops Exec Review |
| Gross Margin % (Supply) | 13 | red | No owner, wrong denominator, on the cycle |

Recommendation r2 has **0.91 model confidence but a trust score of 40**: it breaks the 20% discount rule and leans on an ownerless metric. r6 is capped at 45 because it cites no evidence. Confidence is not trust.

Enterprise Trust Index: **56** at start. Deprecating the four rival revenue metrics and assigning two owners lifts it to **66**.

## Repo layout

```
backend/
  app/
    scoring.py      MTS + RTS, deterministic, evidence per point
    definition.py   formula -> structured definition (terms, ratio, scoped filters)
    reconcile.py    seven-cause diff + numeric bridge with unexplained residual
    extractors/     powerbi.py (TMDL, model.bim, DAX) · tableau.py (.twb/.twbx)
    exports.py      dbt MetricFlow and Databricks metric view YAML
    migration.py    conflict -> migration plan (rename vs deprecate, restate, re-baseline)
    calibration.py  incident backtest, AUC, weight suggestions
    conflicts.py    rules C1–C5
    graph.py        lineage paths, cycles, blast radius, neighbourhood (in-memory twin of the Cypher)
    engine.py       recompute pipeline, index, steward actions, audit
    ask.py          classify → retrieve → rank → generate
    llm.py          single Claude gateway with cache; offline fallback
    neo4j_sync.py   idempotent projection into Neo4j
    main.py         FastAPI routes under /api/v1
  data/acme/        seed dataset (CSV): metrics, dashboards, lineage, component values, reported values, incidents
  data/samples/     a Power BI TMDL model and a Tableau workbook for the extractors
  tests/
frontend/           Next.js 15, Tailwind, shadcn-style UI, Cytoscape.js
infra/
  postgres/schema.sql
  neo4j/constraints.cypher, queries.cypher
docker-compose.yml
```

## API (selected)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/ask` | Trust question → certified metric, owner, lineage, explanation, confidence, conflicts |
| GET | `/api/v1/index` | Enterprise Trust Index, zones, top conflicts |
| GET | `/api/v1/metrics/{id}/score` | Component breakdown with evidence and fix hints |
| POST | `/api/v1/metrics/{id}/certify` | Certify (blocked under 80) |
| POST | `/api/v1/metrics/{id}/deprecate` | Deprecate a variant |
| GET | `/api/v1/conflicts` | Conflict queue, severity then blast radius |
| GET | `/api/v1/graph/neighbourhood/{id}` | Subgraph for the Trust Graph |
| GET | `/api/v1/reconcile?a=&b=&dashboard_a=&dashboard_b=` | Why two numbers differ: causes + bridge |
| POST | `/api/v1/extract/{powerbi\|tableau}?commit=` | Read metrics from a BI file (preview or commit) |
| GET | `/api/v1/conflicts/{id}/plan` | Migration plan for a conflict |
| POST | `/api/v1/metrics/{id}/rename-term` | Give a variant its own business term |
| GET | `/api/v1/metrics/{id}/export?format=dbt\|databricks` | Semantic-layer YAML |
| GET | `/api/v1/calibration` · POST `/calibration/apply` | Incident backtest and weights |
| POST | `/api/v1/ingest/{type}` | Upload CSV metadata (glossary, metric, dashboard, lineage, recommendation) |

Full OpenAPI at `/docs` when the API is running.

## Status and next steps

v0.1 runs on an in-memory store loaded from CSV, with Neo4j as an optional projection. The Postgres schema is ready; next steps:

- [ ] SQL-backed store behind the same interface (`app/store.py`), persisting `trust_score` history and `audit_event`
- [ ] DAX iterators (`SUMX`), `VAR/RETURN` and Tableau `IF`/LOD expressions in the extractors (kept verbatim with a warning today)
- [ ] Live connectors: Power BI REST / XMLA, Tableau Metadata API, dbt manifest
- [ ] Component values pulled from the warehouse so every additive pair gets a numeric bridge
- [ ] pgvector duplicate detection for metrics with no glossary link (the `semantic_matcher` hook in `conflicts.detect`)
- [ ] OSI export once the spec's metric schema settles
- [ ] JWT auth (replace the demo `X-User` header)
