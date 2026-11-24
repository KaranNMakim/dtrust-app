import pytest
import yaml

from app.ask import ask
from app.calibration import auc, calibrate
from app.engine import ActionError
from app.exports import export
from app.migration import plan


def test_dbt_export_is_valid_yaml_with_derived_metric(store):
    out = export(store, "m_net_rev_fin", "dbt")
    doc = yaml.safe_load(out["content"])
    main = doc["metrics"][-1]
    assert main["type"] == "derived"
    assert main["type_params"]["expr"] == "invoice_amount_total - returns_total - discounts_total - rebates_total"
    assert doc["semantic_models"][0]["defaults"]["agg_time_dimension"] == "invoice_date"


def test_dbt_ratio_and_filter(store):
    otif = yaml.safe_load(export(store, "m_otif_sc", "dbt")["content"])["metrics"][-1]
    assert otif["type"] == "ratio"
    sales = yaml.safe_load(export(store, "m_rev_sales", "dbt")["content"])["metrics"][-1]
    assert "Dimension(" in sales["filter"]
    assert "not the certified definition" in sales["description"]


def test_databricks_export(store):
    out = export(store, "m_otif_sc", "databricks")["content"]
    assert "WITH METRICS" in out and "COUNT_IF(on_time AND in_full)" in out
    body = yaml.safe_load(out.split("AS $$\n", 1)[1].rsplit("$$", 1)[0])
    assert body["measures"][0]["name"] == "OTIF"


def test_auc():
    assert auc([1, 2], [3, 4]) == 1.0
    assert auc([3], [3]) == 0.5
    assert auc([], [1]) is None


def test_calibration_report(engine):
    c = calibrate(engine)
    assert c["metrics_with_incidents"] == 7
    assert 0.5 < c["current_auc"] <= 1
    assert abs(sum(c["suggested_weights"].values()) - 1) < 0.01
    assert "Directional" in c["caveat"]


def test_apply_and_reset_weights(engine):
    w = {"definition": 0.25, "ownership": 0.25, "lineage": 0.1, "usage": 0.2, "freshness": 0.2}
    engine.set_weights(w, "steward@acme.com")
    assert engine.metric_scores["m_net_rev_fin"].scoring_version.endswith("calibrated")
    with pytest.raises(ActionError):
        engine.set_weights({"definition": 1.0}, "steward@acme.com")
    engine.set_weights(None, "steward@acme.com")
    assert engine.weights["definition"] == 0.30


def test_revenue_migration_plan(engine):
    p = plan(engine, "C1-g_revenue")
    assert p["canonical"]["metric_id"] == "m_net_rev_fin"
    actions = {v["metric_id"]: v["action"]["type"] for v in p["variants"]}
    assert actions["m_rev_sales"] == "rename"      # bookings are a different concept
    assert actions["m_rev_apac"] == "deprecate"    # same concept, missing deductions
    assert len(p["steps"]) == 6 and p["impact"]["exec_dashboards"] >= 3


def test_other_conflict_plans(engine):
    assert "Supply Mart → RGM Mart" in plan(engine, "C4-cycle1")["steps"][0]["detail"]
    assert plan(engine, "C3-m_gross_rev_mkt")["steps"][0]["action"]["type"] == "assign_owner"


def test_rename_variant_resolves_definition_conflict(engine):
    before = engine.metric_scores["m_rev_sales"].score
    engine.rename_variant("m_rev_sales", "Bookings", "Closed-won opportunity value", "steward@acme.com", "Bookings")
    assert engine.store.metrics["m_rev_sales"].glossary_term_id == "g_bookings"
    c1 = next(c for c in engine.conflicts if c.id == "C1-g_revenue")
    assert "m_rev_sales" not in c1.entity_ids
    assert engine.metric_scores["m_rev_sales"].score > before


def test_ask_reconcile_intent(engine):
    out = ask(engine, "Why does Sales QBR revenue differ from the Board Pack?")
    assert out["intent"] == "reconcile"
    assert out["reconciliation"]["bridge"]["start"] == 1258.3
    out2 = ask(engine, "Why is Revenue APAC lower than group revenue?")
    assert out2["reconciliation"]["b"]["metric_id"] == "m_net_rev_fin"
