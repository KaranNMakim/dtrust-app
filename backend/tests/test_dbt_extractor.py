import json
from pathlib import Path

import pytest

from app.definition import parse
from app.extractors import extract_dbt
from app.formula import formula_hash
from app.extract_apply import apply_extract

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"
MANIFEST = (SAMPLES / "acme_dbt_manifest.json").read_bytes()
SEMANTIC = (SAMPLES / "acme_dbt_semantic_manifest.json").read_bytes()


def _both(store):
    return extract_dbt([("manifest.json", MANIFEST), ("semantic_manifest.json", SEMANTIC)], store.glossary)


def test_metrics_translated(store):
    res = _both(store)
    by = {m["metric_id"]: m for m in res.metrics}
    assert by["dbt_ecom_revenue"]["formula"] == "SUM(order_value)"
    assert parse(by["dbt_refund_rate"]["formula"]).kind == "ratio"
    assert parse(by["dbt_domestic_revenue"]["formula"]).filters == ["region<>'Exports'"]
    assert by["dbt_net_revenue"]["owner_email"] == "meera.iyer@acme.com"
    assert by["dbt_net_revenue"]["time_basis"] == "invoice_date"
    assert by["dbt_net_revenue"]["data_product"] == "dbt_fct_revenue"


def test_dbt_net_revenue_matches_certified_finance_definition(store):
    m = next(m for m in _both(store).metrics if m["metric_id"] == "dbt_net_revenue")
    assert formula_hash(m["formula"]) == store.metrics["m_net_rev_fin"].formula_hash
    assert m["glossary_term"] == "g_revenue"


def test_unsupported_metric_types_warn_and_are_not_grouped(store):
    res = _both(store)
    rolling = next(m for m in res.metrics if m["metric_id"] == "dbt_revenue_7d_rolling")
    assert rolling["glossary_term"] == ""
    assert any("cumulative" in w for w in res.warnings)


def test_lineage_and_sources(store):
    res = _both(store)
    edges = {(e["from_name"], e["to_name"]) for e in res.lineage}
    assert ("fct_revenue", "stg_sap_invoices") in edges and ("stg_sap_invoices", "SAP") in edges
    assert all(e["documented"] == "true" for e in res.lineage)


def test_exposures_become_dashboards(store):
    dashes = {d["name"]: d for d in _both(store).dashboards}
    board = dashes["Finance Board Pack (dbt)"]
    assert board["audience"] == "exec" and board["metrics"] == "dbt_net_revenue|dbt_domestic_revenue"


def test_single_file_modes(store):
    only_sem = extract_dbt([("semantic_manifest.json", SEMANTIC)], store.glossary)
    assert only_sem.metrics and not only_sem.lineage
    assert any("manifest.json" in w for w in only_sem.warnings)
    only_man = extract_dbt([("manifest.json", MANIFEST)], store.glossary)
    assert only_man.lineage and not only_man.metrics


def test_jinja_filters_and_bad_files(store):
    sem = json.loads(SEMANTIC)
    sem["metrics"][6]["filter"] = {"where_filters": [{"where_sql_template": "{{ Dimension('ecom_line__region') }} = 'India'"}]}
    res = extract_dbt([("s.json", json.dumps(sem))], store.glossary)
    eco = next(m for m in res.metrics if m["metric_id"] == "dbt_ecom_revenue")
    assert parse(eco["formula"]).filters == ["region='India'"]
    with pytest.raises(ValueError):
        extract_dbt([("x.json", b"not json")], store.glossary)
    with pytest.raises(ValueError):
        extract_dbt([("x.json", b'{"hello": 1}')], store.glossary)


def test_commit_feeds_scoring_and_lineage(engine):
    res = _both(engine.store)
    apply_extract(engine, res.metrics, res.dashboards, res.lineage, res.nodes)
    apply_extract(engine, res.metrics, res.dashboards, res.lineage, res.nodes)  # re-upload: no duplicate edges
    engine.recompute()
    keys = [(e.from_id, e.to_id) for e in engine.store.lineage]
    assert len(keys) == len(set(keys))
    lin = next(c for c in engine.metric_scores["dbt_net_revenue"].components if c.key == "lineage")
    assert lin.raw == 100  # fully documented back to SAP via dbt
    assert any(c.code == "C3" and "dbt_ecom_revenue" in c.entity_ids for c in engine.conflicts)  # no owner in meta
