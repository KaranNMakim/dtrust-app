import pytest

from app.engine import ActionError
from app.explain import explain, plain_filter, plain_formula


def _recommended(engine, cid="C1-g_revenue"):
    x = explain(engine, cid)
    return x, [{"metric_id": v["metric_id"], "action": v["action"], "term": v["term"],
                "definition": v["definition"], "new_name": v["new_name"]} for v in x["fix"]["variants"]]


def test_plain_language_helpers():
    assert plain_formula("SUM(invoice_amount)-SUM(returns)") == "invoice amount − returns"
    assert plain_formula("COUNT(on_time AND in_full)/COUNT(orders)") == "(number of on time and in full) ÷ (number of orders)"
    assert plain_filter("region<>'Exports'") == "excludes region Exports"


def test_explain_answers_four_questions(engine):
    x, _ = _recommended(engine)
    assert x["type_label"] == "Same name, different formulas" and x["severity_label"] == "Urgent"
    assert x["what"] and x["why"] and x["sources"] and x["effect"]
    assert x["sources"][0]["recommended"] and x["sources"][0]["source_systems"] == ["SAP S/4HANA"]
    assert x["impact"]["exec_dashboards"] == 4
    assert x["gap"]["b_value"] == 1128.0


def test_preview_changes_nothing(engine):
    _, variants = _recommended(engine)
    before = engine.index()["index"]
    p = engine.preview_fix("C1-g_revenue", "m_net_rev_fin", variants)
    assert p["index_after"] > p["index_before"] == before
    assert engine.index()["index"] == before
    assert engine.store.metrics["m_rev_sales"].name == "Revenue (Sales)"


def test_apply_fix_writes_decision_and_repoints_tiles(engine):
    _, variants = _recommended(engine)
    d = engine.apply_fix("C1-g_revenue", "steward@acme.com", "Finance owns revenue", "m_net_rev_fin", variants,
                         checklist=[{"title": "Restate history", "owner": "Finance"}])
    assert d["kind"] == "fix" and d["trust_index_after"] > d["trust_index_before"]
    assert {c["action"] for c in d["changes"]} >= {"rename", "retire"}
    assert "m_net_rev_fin" in engine.store.dashboards["d_apac"].metric_ids  # retired APAC tile now shows Finance
    assert not any(c.id == "C1-g_revenue" and c.status == "open" for c in engine.conflicts)
    assert engine.decisions[-1]["checklist"][0]["title"] == "Restate history"
    engine.set_checklist_item(d["id"], 0, True, "steward@acme.com")
    assert engine.decisions[-1]["checklist"][0]["done"]


def test_fix_requires_reason(engine):
    with pytest.raises(ActionError):
        engine.apply_fix("C1-g_revenue", "steward@acme.com", "  ", "m_net_rev_fin", [])


def test_assign_owner_fix(engine):
    d = engine.apply_fix("C3-m_churn_mkt", "steward@acme.com", "Anita owns churn", owner_email="anita.d@acme.com")
    assert engine.store.metrics["m_churn_mkt"].owner_email == "anita.d@acme.com"
    assert d["changes"][0]["action"] == "assign_owner"


def test_confirm_fix_closes_issue(engine):
    engine.apply_fix("C4-cycle1", "steward@acme.com", "Removed RGM → Supply dependency")
    c = next(c for c in engine.conflicts if c.id == "C4-cycle1")
    assert c.status == "resolved"


def test_dismiss_records_decision(engine):
    d = engine.dismiss_issue("C5-m_otif_cs", "steward@acme.com", "CS OTIF is intentionally on-time only")
    assert d["kind"] == "dismiss"
    assert next(c for c in engine.conflicts if c.id == "C5-m_otif_cs").status == "dismissed"


def test_every_issue_type_explains_without_ids(engine):
    import re
    for c in list(engine.conflicts):
        x = explain(engine, c.id)
        text = " ".join(str(v) for v in (x["what"], x["why"], x["severity_reason"]))
        assert not re.search(r"\b(m|d|g|dp|src)_[a-z0-9_]+\b", text), (c.id, text)
