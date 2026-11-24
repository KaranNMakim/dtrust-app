"""HTTP-level smoke tests. Skipped automatically if FastAPI is not installed."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_index_and_metrics():
    idx = client.get("/api/v1/index").json()
    assert 0 <= idx["index"] <= 100
    metrics = client.get("/api/v1/metrics").json()
    assert metrics[0]["trust_score"] >= metrics[-1]["trust_score"]


def test_ask_endpoint():
    r = client.post("/api/v1/ask", json={"question": "Which revenue metric should I trust?"})
    assert r.status_code == 200
    assert r.json()["certified_metric"]["id"] == "m_net_rev_fin"


def test_certify_rejected_is_problem_json():
    r = client.post("/api/v1/metrics/m_rev_sales/certify", json={})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_404():
    assert client.get("/api/v1/metrics/nope").status_code == 404


def test_reconcile_endpoint():
    r = client.get("/api/v1/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin",
                                               "dashboard_a": "d_sales_qbr", "dashboard_b": "d_board"})
    assert r.status_code == 200 and r.json()["bridge"]["closes"]


def test_export_plan_calibration_endpoints():
    assert "derived" in client.get("/api/v1/metrics/m_net_rev_fin/export?format=dbt").json()["content"]
    assert client.get("/api/v1/conflicts/C1-g_revenue/plan").json()["canonical"]["metric_id"] == "m_net_rev_fin"
    assert "current_auc" in client.get("/api/v1/calibration").json()


def test_extract_preview():
    from pathlib import Path
    twb = (Path(__file__).resolve().parents[1] / "data" / "samples" / "acme_sales.twb").read_bytes()
    r = client.post("/api/v1/extract/tableau", files={"file": ("acme_sales.twb", twb)})
    assert r.status_code == 200 and len(r.json()["metrics"]) == 3
