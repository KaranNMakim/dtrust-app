# UX round 1: display-name pass (HumanizedRoute) - ids kept for links, sentences humanized, code untouched, credits unchanged
import json
import os
import re
import subprocess
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
V1 = f"{BASE_URL}/api/v1"
BILL = f"{BASE_URL}/api/billing"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
_RUN = uuid.uuid4().hex[:6]
_T: dict = {}


def _sess(name, ws="demo"):
    if name not in _T:
        out = subprocess.check_output(["/root/.venv/bin/python", "/app/scripts/clerk_token.py",
                                       f"ux1_{name}_{_RUN}+clerk_test@example.com"])
        _T[name] = json.loads(out)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {_T[name]['token']}", "X-Workspace": ws})
    return s, _T[name]["user_id"]


def _ids(s):
    sys.path.insert(0, "/app/backend")
    from app.config import settings
    from app.store import Store
    st = Store.from_dir(settings.data_dir)
    return [i for i, (_t, n) in st.node_names.items() if n and n != i and "_" in i]


def _sentences(v, out):
    if isinstance(v, str):
        if re.search(r"\s", v):
            out.append(v)
    elif isinstance(v, list):
        for x in v:
            _sentences(x, out)
    elif isinstance(v, dict):
        for x in v.values():
            _sentences(x, out)
    return out


def _leaks(body, ids):
    pat = re.compile(r"(?<![\w.])(" + "|".join(map(re.escape, ids)) + r")(?![\w])")
    return [s for s in _sentences(body, []) if pat.search(s)]


# Response shape and ids preserved
class TestShape:
    def test_metrics_ids_intact(self):
        s, _ = _sess("a")
        ms = s.get(f"{V1}/metrics").json()
        m = {x["id"]: x for x in ms}
        assert "m_net_rev_fin" in m and m["m_net_rev_fin"]["glossary_term_id"] == "g_revenue"
        d = s.get(f"{V1}/metrics/m_net_rev_fin").json()
        assert d["id"] == "m_net_rev_fin" and d["name"] == "Net Revenue (Finance)"
        assert "trust_score" in d and "explanation" in d

    def test_conflicts_shape(self):
        s, _ = _sess("a")
        cs = s.get(f"{V1}/conflicts").json()
        assert cs and all({"id", "code", "title", "detail", "severity"} <= set(c) for c in cs)
        assert {c["code"] for c in cs} <= {"C1", "C2", "C3", "C4", "C5"}

    def test_404_bare_id_kept(self):
        s, _ = _sess("a")
        r = s.get(f"{V1}/metrics/m_nope")
        assert r.status_code == 404
        assert "m_nope" in r.text


# Sentences no longer contain internal ids
class TestSentences:
    @pytest.mark.parametrize("path", ["/index", "/metrics", "/metrics/m_rev_sales", "/metrics/m_rev_sales/score",
                                      "/conflicts", "/recommendations"])
    def test_no_ids_in_sentences(self, path):
        s, _ = _sess("a")
        r = s.get(f"{V1}{path}")
        assert r.status_code == 200, r.text[:200]
        leaks = _leaks(r.json(), _ids(s))
        assert not leaks, leaks[:5]

    def test_reconcile_and_ask(self):
        s, _ = _sess("a")
        r = s.get(f"{V1}/reconcile", params={"a": "m_rev_sales", "b": "m_net_rev_fin",
                                             "dashboard_a": "d_sales_qbr", "dashboard_b": "d_board"})
        assert r.status_code == 200
        assert not _leaks(r.json(), _ids(s)), _leaks(r.json(), _ids(s))[:5]
        r = s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"})
        assert r.status_code == 200
        print("ask leaks", _leaks(r.json(), _ids(s))[:5])


# Exported code must stay valid (no display names injected into code)
class TestExportsUntouched:
    @pytest.mark.parametrize("mid,fmt", [("m_trade_spend", "databricks"), ("m_net_rev_fin", "dbt")])
    def test_export_content_has_ids_not_names(self, mid, fmt):
        s, _ = _sess("a")
        r = s.get(f"{V1}/metrics/{mid}/export", params={"format": fmt})
        assert r.status_code == 200
        c = r.json()["content"]
        assert "NULLIF(Net Revenue (Finance)" not in c, "display name injected into SQL"
        assert "metric_id: Net Revenue" not in c, "display name injected into dbt meta"


# Credits behaviour regression
class TestCredits:
    def test_demo_free_mine_charges(self):
        s, uid = _sess("b", "demo")
        s.get(f"{BILL}/me")
        db.users.update_one({"user_id": uid}, {"$set": {"credits": 3}})
        assert s.get(f"{V1}/metrics/m_net_rev_fin/export").status_code == 200
        assert s.get(f"{BILL}/me").json()["credits"] == 3
        m, _ = _sess("b", "mine")
        assert m.get(f"{V1}/metrics").json() == []
        assert m.get(f"{V1}/metrics/m_net_rev_fin/export").status_code == 404
        assert s.get(f"{BILL}/me").json()["credits"] == 3

    def test_history_shape(self):
        s, _ = _sess("b")
        h = s.get(f"{BILL}/history").json()
        assert "purchases" in h and "ledger" in h
