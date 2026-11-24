# Decision Trust SaaS layer: auth gating, credits/billing, paid vs free actions, per-user isolation
import json
import os
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
V1 = f"{BASE_URL}/api/v1"
BILL = f"{BASE_URL}/api/billing"
SAMPLES = Path("/app/backend/data/samples")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _user(name):
    d = json.load(open(f"/tmp/{name}.json"))
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {d['token']}"
    return s, d["user_id"]


def credits(s):
    r = s.get(f"{BILL}/me")
    assert r.status_code == 200, r.text
    return r.json()["credits"]


def set_credits(uid, n):
    s_ = db.users.update_one({"user_id": uid}, {"$set": {"credits": n}})
    assert s_.matched_count == 1


# Public / auth gating
class TestAuthGating:
    def test_public(self):
        assert requests.get(f"{BASE_URL}/api/health").json()["status"] == "ok"
        r = requests.get(f"{BASE_URL}/api/clerk/config")
        assert r.status_code == 200 and r.json()["enabled"] is True

    @pytest.mark.parametrize("path", ["/api/v1/index", "/api/v1/metrics", "/api/v1/health", "/api/billing/me",
                                      "/api/billing/history", "/api/v1/conflicts"])
    def test_unauth_401(self, path):
        assert requests.get(f"{BASE_URL}{path}").status_code == 401

    def test_unauth_post_401(self):
        assert requests.post(f"{V1}/ask", json={"question": "Which revenue?"}).status_code == 401
        assert requests.post(f"{BILL}/orders", json={"pack_id": "pack_10"}).status_code == 401

    def test_bad_token_401(self):
        r = requests.get(f"{V1}/index", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401


# Credits, free browsing, paid actions (user A)
class TestCreditsAndPaid:
    def test_new_user_me(self):
        s, uid = _user("qa_a")
        d = s.get(f"{BILL}/me").json()
        assert d["credits"] == 3 and d["currency"] == "INR" and d["payments_enabled"] is False
        packs = {p["id"]: (p["credits"], p["amount"]) for p in d["packs"]}
        assert packs == {"pack_10": (10, 850.0), "pack_50": (50, 3800.0), "pack_200": (200, 13500.0)}
        h = s.get(f"{BILL}/history").json()
        grants = [l for l in h["ledger"] if l["type"] == "grant"]
        assert len(grants) == 1 and grants[0]["credits"] == 3
        assert h["purchases"] == []

    def test_free_browsing(self):
        s, uid = _user("qa_a")
        before = credits(s)
        idx = s.get(f"{V1}/index").json()
        print("index", {k: idx[k] for k in list(idx)[:6]})
        ms = s.get(f"{V1}/metrics").json()
        assert len(ms) > 5
        mid = ms[0]["id"]
        for p in [f"/metrics/{mid}", f"/metrics/{mid}/score", f"/metrics/{mid}/score/history",
                  f"/metrics/{mid}/lineage", f"/metrics/{mid}/usage", "/dashboards", "/recommendations",
                  "/graph", "/calibration", "/incidents", "/audit", "/health"]:
            r = s.get(f"{V1}{p}")
            assert r.status_code == 200, (p, r.status_code, r.text[:200])
        cs = s.get(f"{V1}/conflicts").json()
        assert cs
        assert s.get(f"{V1}/conflicts/{cs[0]['id']}/plan").status_code == 200
        recs = s.get(f"{V1}/recommendations").json()
        assert s.get(f"{V1}/recommendations/{recs[0]['id']}/score").status_code == 200
        # extract preview free
        twb = (SAMPLES / "acme_sales.twb").read_bytes()
        r = s.post(f"{V1}/extract/tableau", files={"file": ("acme_sales.twb", twb)})
        assert r.status_code == 200, r.text
        assert credits(s) == before

    def test_index_score_56(self):
        s, _ = _user("qa_a")
        idx = s.get(f"{V1}/index").json()
        txt = json.dumps(idx)
        print(txt[:400])
        assert "56" in txt

    def test_paid_actions_deduct(self):
        s, uid = _user("qa_a")
        set_credits(uid, 10)
        c = credits(s)
        r = s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"})
        assert r.status_code == 200, r.text
        assert credits(s) == c - 1
        r = s.get(f"{V1}/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin",
                                             "dashboard_a": "d_sales_qbr", "dashboard_b": "d_board"})
        assert r.status_code == 200, r.text
        assert credits(s) == c - 2
        r = s.get(f"{V1}/metrics/m_net_rev_fin/export", params={"format": "dbt"})
        assert r.status_code == 200, r.text
        assert credits(s) == c - 3
        csv_ = "term_id,term,definition\nTEST_g_x,TEST_Term,TEST definition here\n"
        r = s.post(f"{V1}/ingest/glossary", files={"file": ("TEST_g.csv", csv_.encode())})
        assert r.status_code == 200, r.text
        assert r.json()["rows_ingested"] == 1
        assert credits(s) == c - 4
        twb = (SAMPLES / "acme_sales.twb").read_bytes()
        r = s.post(f"{V1}/extract/tableau", params={"commit": "true"}, files={"file": ("acme_sales.twb", twb)})
        assert r.status_code == 200, r.text
        assert credits(s) == c - 5
        h = s.get(f"{BILL}/history").json()
        actions = [l["action"] for l in h["ledger"] if l["type"] == "usage"]
        for a in ["ask", "reconcile", "export", "ingest", "extract"]:
            assert a in actions, (a, actions)
        assert all(l["credits"] == -1 for l in h["ledger"] if l["type"] == "usage")

    def test_failed_paid_actions_not_charged(self):
        s, uid = _user("qa_a")
        c = credits(s)
        assert s.get(f"{V1}/reconcile", params={"a": "nope", "b": "m_net_rev_fin"}).status_code in (404, 422)
        assert s.get(f"{V1}/metrics/nope/export").status_code == 404
        assert s.post(f"{V1}/ask", json={"question": "x"}).status_code == 422
        r = s.post(f"{V1}/ingest/glossary", files={"file": ("bad.csv", b"a,b\n1,2\n")})
        assert r.status_code == 422
        r = s.post(f"{V1}/extract/tableau", params={"commit": "true"}, files={"file": ("bad.twb", b"not xml")})
        print("bad extract", r.status_code, r.text[:200])
        assert credits(s) == c

    def test_zero_credits_402(self):
        s, uid = _user("qa_a")
        set_credits(uid, 0)
        r = s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"})
        assert r.status_code == 402 and r.json()["title"] == "Out of credits"
        assert s.get(f"{V1}/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin"}).status_code == 402
        assert s.get(f"{V1}/metrics/m_net_rev_fin/export").status_code == 402
        r = s.post(f"{V1}/ingest/glossary", files={"file": ("g.csv", b"term_id,term,definition\nx,y,zzzzzz\n")})
        assert r.status_code == 402
        twb = (SAMPLES / "acme_sales.twb").read_bytes()
        assert s.post(f"{V1}/extract/tableau", params={"commit": "true"},
                      files={"file": ("acme_sales.twb", twb)}).status_code == 402
        # preview still free
        assert s.post(f"{V1}/extract/tableau", files={"file": ("acme_sales.twb", twb)}).status_code == 200
        assert s.get(f"{V1}/index").status_code == 200
        assert credits(s) == 0

    def test_orders_503(self):
        s, _ = _user("qa_a")
        assert s.post(f"{BILL}/orders", json={"pack_id": "pack_10"}).status_code == 503
        assert s.post(f"{BILL}/orders", json={"pack_id": "zzz"}).status_code == 404


# Per-user workspace isolation (A vs B)
class TestIsolation:
    def test_isolation(self):
        a, _ = _user("qa_b")
        b, _ = _user("qa_c")
        ms = a.get(f"{V1}/metrics").json()
        target = next(m for m in ms if m["certification"] != "deprecated" and m["id"] != "m_net_rev_fin")
        before_b = b.get(f"{V1}/metrics/{target['id']}").json()["certification"]
        r = a.post(f"{V1}/metrics/{target['id']}/deprecate", json={"reason": "TEST_isolation"})
        print("deprecate", r.status_code, r.text[:200])
        assert r.status_code == 200
        assert a.get(f"{V1}/metrics/{target['id']}").json()["certification"] == "deprecated"
        assert b.get(f"{V1}/metrics/{target['id']}").json()["certification"] == before_b
        audit_b = json.dumps(b.get(f"{V1}/audit").json())
        assert "TEST_isolation" not in audit_b
        # ledger isolation
        hb = b.get(f"{BILL}/history").json()
        assert all(l["type"] == "grant" for l in hb["ledger"])
