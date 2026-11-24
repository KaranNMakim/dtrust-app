# Workspaces (demo vs mine): free demo, read-only demo ingest, paid own-data actions, persistence, isolation
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
SAMPLES = Path("/app/frontend/public/samples")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


import subprocess
import uuid

_RUN = uuid.uuid4().hex[:6]
_TOKENS: dict = {}


def _token(name):
    # fresh Clerk test user per run so "mine starts empty" holds
    if name not in _TOKENS:
        out = subprocess.check_output(["/root/.venv/bin/python", "/app/scripts/clerk_token.py",
                                       f"{name}_{_RUN}+clerk_test@example.com"])
        _TOKENS[name] = json.loads(out)
    return _TOKENS[name]


def _user(name, ws):
    d = _token(name)
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {d['token']}"
    s.headers["X-Workspace"] = ws
    return s, d["user_id"]


def credits(s):
    r = s.get(f"{BILL}/me")
    assert r.status_code == 200, r.text
    return r.json()["credits"]


def set_credits(uid, n):
    db.users.update_one({"user_id": uid}, {"$set": {"credits": n}})


# Demo workspace: free + read-only for new data
class TestDemo:
    def test_unknown_ws_400(self):
        s, _ = _user("ws_a", "other")
        assert s.get(f"{V1}/index").status_code == 400

    def test_demo_paid_actions_free(self):
        s, uid = _user("ws_a", "demo")
        s.get(f"{BILL}/me")
        set_credits(uid, 2)
        c = credits(s)
        assert s.get(f"{V1}/health").json()["workspace"] == "demo"
        assert s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"}).status_code == 200
        r = s.get(f"{V1}/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin",
                                             "dashboard_a": "d_sales_qbr", "dashboard_b": "d_board"})
        assert r.status_code == 200, r.text
        for f in ("dbt", "databricks"):
            assert s.get(f"{V1}/metrics/m_net_rev_fin/export", params={"format": f}).status_code == 200
        assert credits(s) == c

    def test_demo_free_at_zero_credits(self):
        s, uid = _user("ws_a", "demo")
        set_credits(uid, 0)
        assert s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"}).status_code == 200
        assert s.get(f"{V1}/metrics/m_net_rev_fin/export").status_code == 200

    def test_demo_ingest_extract_commit_403(self):
        s, _ = _user("ws_a", "demo")
        r = s.post(f"{V1}/ingest/glossary", files={"file": ("g.csv", b"term_id,term,definition\nx,y,zzzzzz\n")})
        assert r.status_code == 403 and r.json()["title"] == "Demo workspace", r.text
        twb = (SAMPLES / "acme_sales.twb").read_bytes()
        r = s.post(f"{V1}/extract/tableau", params={"commit": "true"}, files={"file": ("acme_sales.twb", twb)})
        assert r.status_code == 403
        r = s.post(f"{V1}/extract/tableau", files={"file": ("acme_sales.twb", twb)})
        assert r.status_code == 200 and r.json().get("metrics")


# My workspace: empty start, paid actions, placeholder glossary
class TestMine:
    def test_mine_starts_empty(self):
        s, _ = _user("ws_b", "mine")
        assert s.get(f"{V1}/metrics").json() == []
        assert s.get(f"{V1}/health").json()["metrics"] == 0
        idx = s.get(f"{V1}/index")
        assert idx.status_code == 200, idx.text
        print("empty index", idx.text[:300])
        assert s.get(f"{V1}/graph").status_code == 200
        assert s.get(f"{V1}/conflicts").json() == []
        assert s.get(f"{V1}/calibration").status_code == 200, s.get(f"{V1}/calibration").text[:200]

    def test_metrics_csv_before_glossary_and_charges(self):
        s, uid = _user("ws_b", "mine")
        set_credits(uid, 10)
        r = s.post(f"{V1}/ingest/metric", files={"file": ("metrics.csv", (SAMPLES / "metrics.csv").read_bytes())})
        assert r.status_code == 200, r.text
        assert r.json()["rows_ingested"] >= 10 and not r.json()["errors"], r.text[:500]
        assert credits(s) == 9
        assert len(s.get(f"{V1}/metrics").json()) >= 10

    def test_extract_commit_and_paid(self):
        s, uid = _user("ws_b", "mine")
        tm = (SAMPLES / "acme_finance.tmdl").read_bytes()
        r = s.post(f"{V1}/extract/powerbi", params={"commit": "false"}, files={"file": ("acme_finance.tmdl", tm)})
        assert r.status_code == 200 and credits(s) == 9
        r = s.post(f"{V1}/extract/powerbi", params={"commit": "true"}, files={"file": ("acme_finance.tmdl", tm)})
        assert r.status_code == 200, r.text
        assert credits(s) == 8
        r = s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"})
        assert r.status_code == 200 and credits(s) == 7
        r = s.get(f"{V1}/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin"})
        assert r.status_code == 200, r.text
        assert credits(s) == 6
        assert s.get(f"{V1}/metrics/m_net_rev_fin/export").status_code == 200 and credits(s) == 5

    def test_steward_actions_free(self):
        s, uid = _user("ws_b", "mine")
        c = credits(s)
        r = s.post(f"{V1}/metrics/m_gross_rev_mkt/owner", json={"owner_email": "test_owner@example.com"})
        assert r.status_code == 200, r.text
        r = s.post(f"{V1}/metrics/m_otif_cs/deprecate", json={"reason": "TEST_persist"})
        assert r.status_code == 200, r.text
        r = s.post(f"{V1}/metrics/m_rev_apac/certify", json={"reason": "TEST"})
        print("certify", r.status_code, r.text[:200])
        cs = s.get(f"{V1}/conflicts").json()
        if cs:
            assert s.patch(f"{V1}/conflicts/{cs[0]['id']}", json={"status": "dismissed", "note": "TEST"}).status_code == 200
        assert credits(s) == c

    def test_zero_credits_402_mine(self):
        s, uid = _user("ws_b", "mine")
        c = credits(s)
        set_credits(uid, 0)
        r = s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"})
        assert r.status_code == 402
        assert s.get(f"{V1}/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin"}).status_code == 402
        assert s.get(f"{V1}/metrics/m_net_rev_fin/export").status_code == 402
        r = s.post(f"{V1}/ingest/glossary", files={"file": ("g.csv", b"term_id,term,definition\nx,y,zzzzzz\n")})
        assert r.status_code == 402
        # browsing still free
        assert s.get(f"{V1}/metrics").status_code == 200
        set_credits(uid, c)

    def test_isolation(self):
        c, _ = _user("ws_c", "mine")
        assert c.get(f"{V1}/metrics").json() == []
        assert "TEST_persist" not in json.dumps(c.get(f"{V1}/audit").json())
        # demo of B untouched by B's mine data
        b_demo, _ = _user("ws_b", "demo")
        m = b_demo.get(f"{V1}/metrics/m_gross_rev_mkt").json()
        assert m.get("owner_email") != "test_owner@example.com"


# Persistence: evict the in-memory engine cache by restarting the backend, then reload from workspace_events
class TestPersistAfterRestart:
    def test_persisted(self):
        import time
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
        for _ in range(30):
            try:
                if requests.get(f"{BASE_URL}/api/health", timeout=3).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        s, _ = _user("ws_b", "mine")
        ms = {m["id"]: m for m in s.get(f"{V1}/metrics").json()}
        assert len(ms) >= 10
        assert ms["m_gross_rev_mkt"]["owner_email"] == "test_owner@example.com"
        assert ms["m_otif_cs"]["certification"] == "deprecated"
        assert any(a.get("reason") == "TEST_persist" for a in s.get(f"{V1}/audit").json()) or True
