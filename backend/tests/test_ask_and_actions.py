import pytest

from app.ask import ask, classify
from app.engine import ActionError


def test_intent_classification():
    assert classify("Which revenue metric should I trust?") == "resolve_metric"
    assert classify("Why is Revenue (Sales) so low?") == "explain_score"
    assert classify("Show me conflicts on churn") == "find_conflicts"
    assert classify("Should we act on the promo recommendation r2?") == "recommendation_trust"


def test_revenue_question_returns_certified_metric(engine):
    out = ask(engine, "Which revenue metric should I trust?")
    assert out["intent"] == "resolve_metric"
    cm = out["certified_metric"]
    assert cm["id"] == "m_net_rev_fin"
    assert cm["certification"] == "certified"
    assert cm["owner"]["email"] == "meera.iyer@acme.com"
    assert out["lineage"][0] == "SAP S/4HANA"
    assert len(out["conflicts"]) == 4
    assert 0 < out["confidence"] <= 0.99
    assert "m_net_rev_fin" in out["citations"]


def test_synonym_matching(engine):
    out = ask(engine, "What is the right turnover number for the board?")
    assert out["certified_metric"]["id"] == "m_net_rev_fin"


def test_unknown_term_is_honest(engine):
    out = ask(engine, "Which NPS metric should I trust?")
    assert out["found"] is False
    assert out["citations"] == []


def test_recommendation_question(engine):
    out = ask(engine, "Can we trust recommendation r2?")
    assert out["recommendation_id"] == "r2"
    assert out["score"]["zone"] == "red"


def test_certify_blocked_below_80(engine):
    with pytest.raises(ActionError):
        engine.certify("m_rev_sales", "steward@acme.com")


def test_assign_owner_raises_score_and_closes_orphan(engine):
    before = engine.metric_scores["m_churn_mkt"].score
    engine.assign_owner("m_churn_mkt", "anita.d@acme.com", "steward@acme.com")
    assert engine.metric_scores["m_churn_mkt"].score > before
    assert not any(c.id == "C3-m_churn_mkt" for c in engine.conflicts)
    assert engine.store.audit[-1]["action"] == "assign_owner"


def test_resolving_conflict_removes_penalty(engine):
    before = engine.metric_scores["m_rev_sales"].score
    engine.update_conflict("C2-m_rev_sales", "resolved", "steward@acme.com", "Override documented")
    assert engine.metric_scores["m_rev_sales"].score == pytest.approx(before + 5, abs=0.2)


def test_steward_cleanup_raises_index(engine):
    before = engine.index()["index"]
    for mid in ("m_rev_sales", "m_gross_rev_mkt", "m_net_sales_ecom", "m_rev_apac"):
        engine.deprecate(mid, "steward@acme.com", "merged")
    assert engine.index()["index"] > before


def test_neighbourhood(engine):
    nb = engine.neighbourhood("g_revenue", depth=1)
    ids = {n["id"] for n in nb["nodes"]}
    assert {"m_net_rev_fin", "m_rev_sales"} <= ids
