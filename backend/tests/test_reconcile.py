import pytest

from app.definition import canonical, parse
from app.reconcile import reconcile


def test_parse_additive_with_filters():
    d = parse("SUM(amount)-SUM(returns) WHERE region <> 'Exports' AND channel = \"GT\"")
    assert d.kind == "additive"
    assert [(t.sign, t.column) for t in d.terms] == [(1, "amount"), (-1, "returns")]
    assert d.filters == ["region<>'Exports'", "channel='GT'"]


def test_parse_ratio_and_nested_groups_flatten():
    d = parse("((SUM(a) - SUM(b)) - SUM(c)) / SUM(a)")
    assert d.kind == "ratio"
    assert [(t.sign, t.column) for t in d.terms] == [(1, "a"), (-1, "b"), (-1, "c")]
    assert parse("a - (b - c)").terms[2].sign == 1


def test_where_inside_aggregate_stays_local():
    d = parse("COUNT(orders_rows WHERE on_time=TRUE) / COUNT(orders_rows)")
    assert d.filters == []
    assert "WHERE" in d.terms[0].column


def test_canonical_ignores_order_brackets_whitespace():
    assert canonical("SUM(a)-SUM(b)-SUM(c)") == canonical("SUM(a) - (SUM(c)) - SUM(b)")
    assert canonical("SUM(a)") != canonical("SUM(a) WHERE x=1")


def test_sales_qbr_vs_board_bridge_closes(store):
    r = reconcile(store, "m_rev_sales", "m_net_rev_fin", "d_sales_qbr", "d_board")
    br = r["bridge"]
    assert br["start"] == 1258.3 and br["end"] == 1128.0
    assert br["closes"]
    labels = [s["label"] for s in br["steps"]]
    assert "Remove filter region<>'Exports'" in labels
    assert any(s["cause"] == "unexplained" for s in br["steps"])  # 6.3 not explained by structure
    assert 0.9 < br["explained_share"] < 1.0
    causes = {c["cause"] for c in r["causes"]}
    assert {"definition", "filters", "time_logic", "source", "mapping", "late_adjustments"} <= causes


def test_each_finding_has_its_own_impact(store):
    r = reconcile(store, "m_rev_sales", "m_net_rev_fin", "d_sales_qbr", "d_board")
    impacts = {c["finding"]: c["impact"] for c in r["causes"]}
    assert impacts["Revenue (Sales) does not deduct returns; Net Revenue (Finance) does"] == -38.5
    assert impacts["Revenue (Sales) applies stage='Closed Won' in the formula"] is None


def test_ecom_bridge_fully_explained(store):
    r = reconcile(store, "m_net_sales_ecom", "m_net_rev_fin")
    assert r["bridge"]["explained_share"] == 1.0


def test_no_bridge_across_currencies(store):
    r = reconcile(store, "m_rev_apac", "m_net_rev_fin")
    assert r["bridge"] is None
    assert any(c["cause"] == "mapping" and "USD" in c["finding"] for c in r["causes"])


def test_ratio_metrics_get_structural_causes_only(store):
    r = reconcile(store, "m_otif_cs", "m_otif_sc")
    assert r["bridge"] is None
    assert any("numerator" in c["finding"] for c in r["causes"])


def test_dashboard_must_show_metric(store):
    with pytest.raises(ValueError):
        reconcile(store, "m_rev_sales", "m_net_rev_fin", "d_board", None)
