# Cleanup: delete test users this run created (by user_id) from Mongo and Clerk
import json, os, sys, requests
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
for f in sys.argv[1:]:
    uid = json.load(open(f))["user_id"]
    print(uid, db.users.delete_many({"user_id": uid}).deleted_count, db.credit_ledger.delete_many({"user_id": uid}).deleted_count,
          db.payment_transactions.delete_many({"user_id": uid}).deleted_count,
          requests.delete(f"https://api.clerk.com/v1/users/{uid}", headers={"Authorization": f"Bearer {os.environ['CLERK_SECRET_KEY']}", "User-Agent": "emergent-test"}).status_code)
