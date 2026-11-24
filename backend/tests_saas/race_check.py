# Manual race checks: concurrent first requests (grant dup) and concurrent spend at 1 credit
import json, os, sys, concurrent.futures as cf
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
d = json.load(open(sys.argv[1]))
h = {"Authorization": f"Bearer {d['token']}"}
with cf.ThreadPoolExecutor(8) as ex:
    rs = list(ex.map(lambda _: requests.get(f"{B}/api/billing/me", headers=h).status_code, range(8)))
print("first-req statuses", rs)
print("users docs", db.users.count_documents({"user_id": d["user_id"]}),
      "grant rows", db.credit_ledger.count_documents({"user_id": d["user_id"], "type": "grant"}))
db.users.update_one({"user_id": d["user_id"]}, {"$set": {"credits": 1}})
with cf.ThreadPoolExecutor(6) as ex:
    rs = list(ex.map(lambda _: requests.post(f"{B}/api/v1/ask", headers=h, json={"question": "Which revenue metric should I trust?"}).status_code, range(6)))
print("concurrent ask statuses at 1 credit", rs, "credits now", db.users.find_one({"user_id": d["user_id"]})["credits"])
