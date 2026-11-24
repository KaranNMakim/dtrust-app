from pathlib import Path

from app.definition import parse
from app.extractors import extract_powerbi, extract_tableau
from app.formula import formula_hash

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def _pbi(store):
    return extract_powerbi((SAMPLES / "acme_finance.tmdl").read_text(), "acme_finance.tmdl", store.glossary, "Finance Model")


def test_powerbi_measures_and_hidden_skipped(store):
    res = _pbi(store)
    ids = [m["metric_id"] for m in res.metrics]
    assert "pbi_net_revenue" in ids and "pbi__helper" not in ids
    assert res.dashboards[0]["name"] == "Finance Model"


def test_powerbi_measure_reference_inlined_and_matches_csv_definition(store):
    m = next(m for m in _pbi(store).metrics if m["metric_id"] == "pbi_net_revenue")
    assert formula_hash(m["formula"]) == store.metrics["m_net_rev_fin"].formula_hash
    assert m["glossary_term"] == "g_revenue"


def test_powerbi_calculate_filters_hoisted_and_comment_stripped(store):
    m = next(m for m in _pbi(store).metrics if m["metric_id"] == "pbi_domestic_revenue")
    d = parse(m["formula"])
    assert d.filters == ["region<>'Exports'", "channel='GT'"]


def test_powerbi_divide_and_local_filter(store):
    otif = next(m for m in _pbi(store).metrics if m["metric_id"] == "pbi_otif")
    d = parse(otif["formula"])
    assert d.kind == "ratio" and d.filters == []
    assert "on_time=TRUE" in d.terms[0].column
    gm = parse(next(m for m in _pbi(store).metrics if m["metric_id"] == "pbi_gross_margin")["formula"])
    assert gm.kind == "ratio" and any(t.column == "cogs" and t.sign < 0 for t in gm.terms)


def test_powerbi_bim_json(store):
    bim = '{"model": {"tables": [{"name": "Sales", "measures": [{"name": "Revenue", "expression": ["SUM(Sales[invoice_amount])"]}]}]}}'
    res = extract_powerbi(bim, "model.bim", store.glossary)
    assert res.metrics[0]["formula"] == "SUM(invoice_amount)"


def test_powerbi_unsupported_dax_warns(store):
    tmdl = "table T\n\tmeasure X = VAR a = SUM(T[x]) RETURN a\n"
    res = extract_powerbi(tmdl, "x.tmdl", store.glossary)
    assert res.warnings and "VAR" in res.warnings[0]


def test_tableau_calcs_filters_and_dashboards(store):
    res = extract_tableau((SAMPLES / "acme_sales.twb").read_bytes(), "acme_sales.twb", store.glossary)
    by_id = {m["metric_id"]: m for m in res.metrics}
    assert by_id["tab_revenue"]["formula"] == "SUM(opportunity_amount)"
    assert by_id["tab_revenue"]["glossary_term"] == "g_revenue"
    assert "tab_is_strategic" not in by_id  # row-level helper, not a metric
    assert "(SUM(opportunity_amount))" in by_id["tab_net_bookings"]["formula"]
    dash = res.dashboards[0]
    assert dash["name"] == "Sales QBR (Tableau)"
    assert "tab_revenue:region<>'Exports'" in dash["local_overrides"]


def test_extracted_metrics_feed_conflict_detection(engine):
    res = extract_tableau((SAMPLES / "acme_sales.twb").read_bytes(), "acme_sales.twb", engine.store.glossary)
    for r in res.metrics:
        engine.store.add_metric(r)
    for r in res.dashboards:
        engine.store.add_dashboard(r)
    engine.recompute()
    c1 = next(c for c in engine.conflicts if c.id == "C1-g_revenue")
    assert "tab_revenue" in c1.entity_ids
    assert any(c.id == "C3-tab_revenue" for c in engine.conflicts)  # extracted with no owner
