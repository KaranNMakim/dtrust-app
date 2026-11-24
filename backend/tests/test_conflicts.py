from app import conflicts
from app.graph import find_cycles, lineage_paths


def _codes(found):
    return {c.code for c in found}


def test_all_five_conflict_types_detected(store):
    assert _codes(conflicts.detect(store)) == {"C1", "C2", "C3", "C4", "C5"}


def test_revenue_has_five_definitions_and_is_critical(store):
    c = next(c for c in conflicts.detect(store) if c.id == "C1-g_revenue")
    assert c.severity == "critical"
    assert len(c.detail["variants"]) == 5
    assert c.detail["certified"] == ["m_net_rev_fin"]


def test_orphans(store):
    orphans = {c.entity_ids[0] for c in conflicts.detect(store) if c.code == "C3"}
    assert orphans == {"m_gross_rev_mkt", "m_gm_supply", "m_churn_mkt"}


def test_cycle_found(store):
    cycles = find_cycles(store)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"dp_supply", "dp_rgm", "dp_demand"}


def test_override_detected(store):
    c2 = [c for c in conflicts.detect(store) if c.code == "C2"]
    assert [c.entity_ids[0] for c in c2] == ["m_rev_sales"]


def test_critical_conflicts_sorted_first(store):
    found = conflicts.detect(store)
    sev = [c.severity for c in found]
    assert sev == sorted(sev, key=lambda s: 0 if s == "critical" else 1)


def test_net_revenue_lineage_reaches_sap_fully_documented(store):
    paths = lineage_paths(store, "m_net_rev_fin")
    assert paths[0]["path"][0] == "SAP S/4HANA"
    assert paths[0]["coverage"] == 1.0


def test_deprecating_rivals_removes_them_from_conflicts(engine):
    for mid in ("m_rev_sales", "m_gross_rev_mkt", "m_rev_apac", "m_net_sales_ecom"):
        engine.deprecate(mid, "steward@acme.com", "merge into Net Revenue (Finance)")
    assert not any(c.id == "C1-g_revenue" for c in engine.conflicts)
