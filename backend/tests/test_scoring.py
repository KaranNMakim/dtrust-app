from datetime import datetime, timedelta, timezone

from app import formula as fx
from app.models import Metric
from app.scoring import MTS_WEIGHTS, RTS_WEIGHTS, freshness


def test_weights_sum_to_one():
    assert abs(sum(MTS_WEIGHTS.values()) - 1) < 1e-9
    assert abs(sum(RTS_WEIGHTS.values()) - 1) < 1e-9


def test_formula_hash_ignores_whitespace_case_and_term_order():
    a = "SUM(invoice_amount)-SUM(returns)-SUM(discounts)"
    b = "sum(invoice_amount) - sum(discounts) - sum(returns)"
    assert fx.formula_hash(a) == fx.formula_hash(b)
    assert fx.formula_hash(a) != fx.formula_hash("SUM(order_value)")


def test_glossary_alignment():
    req = ["invoice_amount", "returns", "discounts", "rebates"]
    assert fx.glossary_alignment("SUM(invoice_amount)-SUM(returns)-SUM(discounts)-SUM(rebates)", req) == 1
    assert fx.glossary_alignment("SUM(invoice_amount)-SUM(returns)", req) == 0.5
    assert fx.glossary_alignment("SUM(order_value)", req) == 0


def _metric(last, sla=24):
    return Metric("m", "M", "x", "daily", "a@b.c", "T", None, None, "none", sla, last)


def test_freshness_decays_linearly_to_zero_at_three_sla():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    assert freshness(_metric(now - timedelta(hours=10)), now).raw == 100
    assert freshness(_metric(now - timedelta(hours=48)), now).raw == 50
    assert freshness(_metric(now - timedelta(hours=72)), now).raw == 0
    assert freshness(_metric(None), now).raw == 0


def test_certified_metrics_are_green(engine):
    for mid in ("m_net_rev_fin", "m_gm_fin"):
        assert engine.metric_scores[mid].zone == "green", mid


def test_orphans_and_stale_metrics_are_red(engine):
    for mid in ("m_gross_rev_mkt", "m_gm_supply", "m_churn_mkt"):
        ts = engine.metric_scores[mid]
        assert ts.zone == "red", mid
        assert next(c for c in ts.components if c.key == "ownership").raw == 0


def test_certified_revenue_beats_every_rival(engine):
    top = engine.metric_scores["m_net_rev_fin"].score
    for m in engine.store.metrics_for_term("g_revenue"):
        if m.id != "m_net_rev_fin":
            assert engine.metric_scores[m.id].score < top


def test_definition_conflicts_are_charged_once(engine):
    ts = engine.metric_scores["m_rev_apac"]
    charged = [p for p in ts.penalties if p["code"] in ("C1", "C5") and p["points"] < 0]
    assert len(charged) == 1


def test_cycle_halves_lineage(engine):
    lin = next(c for c in engine.metric_scores["m_fcst_acc"].components if c.key == "lineage")
    assert lin.raw <= 50
    assert any("circular" in e.lower() for e in lin.evidence)


def test_every_component_has_evidence(engine):
    for ts in list(engine.metric_scores.values()) + list(engine.rec_scores.values()):
        assert 0 <= ts.score <= 100
        for c in ts.components:
            assert c.evidence, (ts.entity_id, c.key)


def test_rts_capped_by_weakest_input(engine):
    ts = engine.rec_scores["r3"]
    weakest = engine.metric_scores["m_churn_mkt"].score
    assert ts.score <= weakest + 20


def test_high_confidence_with_rule_violation_is_red(engine):
    r2 = engine.store.recommendations["r2"]
    assert r2.raw_confidence > 0.9
    assert engine.rec_scores["r2"].zone == "red"


def test_no_evidence_means_untrusted(engine):
    assert engine.rec_scores["r6"].zone == "red"
    assert engine.rec_scores["r6"].cap["reason"] == "no_evidence"
