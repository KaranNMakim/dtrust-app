# Premium waitlist API (GET/POST /api/premium/waitlist) + iteration-1 regression (ingest spend-before-apply, credits)
# Tokens: /tmp/wl_api_t2.json (fresh user). Only ONE real email send happens in this file.
import json
import os
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PREM = f"{BASE_URL}/api/premium/waitlist"
V1 = f"{BASE_URL}/api/v1"
BILL = f"{BASE_URL}/api/billing"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def user():
    d = json.load(open("/tmp/wl_api_t2.json"))
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {d['token']}"
    assert s.get(f"{BILL}/me").status_code == 200  # ensure member exists
    return s, d["user_id"]


# Waitlist auth + validation
class TestWaitlistValidation:
    def test_get_401(self):
        assert requests.get(PREM).status_code == 401

    def test_post_401(self):
        r = requests.post(PREM, json={"subject": "TEST_x", "reason": "long enough reason here"})
        assert r.status_code == 401

    def test_get_initial_not_joined(self, user):
        s, _ = user
        r = s.get(PREM)
        assert r.status_code == 200
        assert r.json() == {"joined": False, "entries": []}

    def test_short_reason_422(self, user):
        s, uid = user
        r = s.post(PREM, json={"subject": "TEST_sub", "reason": "short"})
        assert r.status_code == 422
        assert db.premium_waitlist.count_documents({"user_id": uid}) == 0

    def test_short_subject_422(self, user):
        s, _ = user
        assert s.post(PREM, json={"subject": "ab", "reason": "a long enough reason"}).status_code == 422

    def test_missing_fields_422(self, user):
        s, _ = user
        assert s.post(PREM, json={}).status_code == 422


# Waitlist join (1 real email) + rate limit
class TestWaitlistJoin:
    def test_join_then_get(self, user):
        s, uid = user
        r = s.post(PREM, json={"subject": "TEST_ QA automated test - please ignore",
                               "reason": "TEST_ automated QA check of the premium waitlist form. Please ignore."})
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "joined"}
        g = s.get(PREM).json()
        assert g["joined"] is True
        assert len(g["entries"]) == 1
        e = g["entries"][0]
        assert e["subject"].startswith("TEST_")
        assert e["status"] == "joined"
        assert "_id" not in e and "user_id" not in e
        doc = db.premium_waitlist.find_one({"user_id": uid})
        assert doc.get("email_id"), "email id not stored -> email send may have failed"

    def test_rate_limit_429(self, user):
        s, uid = user
        now = datetime.now(timezone.utc).isoformat()
        # seed 2 more entries directly (no email) so the user has 3 in 24h
        db.premium_waitlist.insert_many([
            {"user_id": uid, "subject": "TEST_seed", "reason": "TEST_seed reason", "status": "joined", "created_at": now},
            {"user_id": uid, "subject": "TEST_seed2", "reason": "TEST_seed reason", "status": "joined", "created_at": now},
        ])
        r = s.post(PREM, json={"subject": "TEST_limit", "reason": "this one should be rate limited"})
        assert r.status_code == 429
        assert "waitlist" in r.json().get("detail", "").lower()
        assert db.premium_waitlist.count_documents({"user_id": uid}) == 3

    def test_waitlist_does_not_spend_credits(self, user):
        s, _ = user
        assert s.get(f"{BILL}/me").json()["credits"] == 3


# Regression: ingest at 0 credits leaves workspace unchanged; ask spends 1
class TestRegression:
    def test_free_browse_no_spend(self, user):
        s, _ = user
        for p in ["/index", "/metrics", "/conflicts", "/recommendations"]:
            assert s.get(f"{V1}{p}").status_code == 200, p
        assert s.get(f"{BILL}/me").json()["credits"] == 3

    def test_ask_spends_one(self, user):
        s, _ = user
        r = s.post(f"{V1}/ask", json={"question": "Which revenue metric should I trust?"})
        assert r.status_code == 200
        assert s.get(f"{BILL}/me").json()["credits"] == 2

    def test_ingest_replace_at_zero_credits_unchanged(self, user):
        s, uid = user
        before = s.get(f"{V1}/metrics").json()
        db.users.update_one({"user_id": uid}, {"$set": {"credits": 0}})
        csv_ = "metric_id,name,definition\nTEST_m,TEST metric,x\n"
        r = s.post(f"{V1}/ingest/metric", params={"mode": "replace"}, files={"file": ("TEST_m.csv", csv_.encode())})
        assert r.status_code in (402, 422), r.text
        after = s.get(f"{V1}/metrics").json()
        assert len(after) == len(before)
        assert s.get(f"{BILL}/me").json()["credits"] == 0
