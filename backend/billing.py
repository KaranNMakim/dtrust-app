"""Credits ledger and Razorpay credit-pack purchases."""

import hmac
import hashlib
import json
import os
from datetime import datetime, timezone

import razorpay
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from pymongo import MongoClient, ReturnDocument

from clerk_auth import require_user

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
users = db["users"]
ledger = db["credit_ledger"]
payments = db["payment_transactions"]

FREE_CREDITS = 3
PACKS = {
    "pack_10": {"id": "pack_10", "name": "Starter", "credits": 10, "amount": 850.0},
    "pack_50": {"id": "pack_50", "name": "Team", "credits": 50, "amount": 3800.0},
    "pack_200": {"id": "pack_200", "name": "Enterprise", "credits": 200, "amount": 13500.0},
}
CURRENCY = "INR"
PAID_ACTIONS = {
    "ask": "Ask a trust question",
    "reconcile": "Reconcile two numbers",
    "extract": "Add metrics from a Power BI or Tableau file",
    "ingest": "Upload metadata CSV",
    "export": "Publish to dbt / Databricks",
}

billing_router = APIRouter(prefix="/api/billing")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clerk_email(user_id: str) -> str | None:
    r = requests.get(f"https://api.clerk.com/v1/users/{user_id}", timeout=10,
                     headers={"Authorization": f"Bearer {os.environ['CLERK_SECRET_KEY']}", "User-Agent": "emergent-app"})
    r.raise_for_status()
    data = r.json()
    primary = data.get("primary_email_address_id")
    emails = data.get("email_addresses", [])
    for e in emails:
        if e["id"] == primary:
            return e["email_address"]
    return emails[0]["email_address"] if emails else None


def ensure_member(user_id: str) -> dict:
    member = users.find_one({"user_id": user_id}, {"_id": 0})
    if member:
        return member
    email = _clerk_email(user_id)
    member = users.find_one_and_update(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "email": email, "credits": FREE_CREDITS, "created_at": _now()}},
        upsert=True, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if member["created_at"] and not ledger.find_one({"user_id": user_id, "type": "grant"}):
        ledger.insert_one({"user_id": user_id, "type": "grant", "credits": FREE_CREDITS,
                           "detail": "Free starter credits", "created_at": _now()})
    return member


def member_dep(user: dict = Depends(require_user)) -> dict:
    return ensure_member(user["user_id"])


def require_credit(member: dict = Depends(member_dep)) -> str:
    if member.get("credits", 0) < 1:
        raise HTTPException(402, detail={"title": "Out of credits", "status": 402,
                                         "detail": "You're out of credits. Buy a credit pack to keep going."})
    return member["user_id"]


def spend_credit(user_id: str, action: str, detail: str | None = None) -> None:
    updated = users.find_one_and_update({"user_id": user_id, "credits": {"$gte": 1}}, {"$inc": {"credits": -1}})
    if not updated:
        raise HTTPException(402, detail={"title": "Out of credits", "status": 402,
                                         "detail": "You're out of credits. Buy a credit pack to keep going."})
    ledger.insert_one({"user_id": user_id, "type": "usage", "credits": -1, "action": action,
                       "label": PAID_ACTIONS.get(action, action), "detail": (detail or "")[:200], "created_at": _now()})


def _razorpay() -> razorpay.Client:
    key_id, secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not secret:
        raise HTTPException(503, detail="Payments are not set up yet")
    return razorpay.Client(auth=(key_id, secret))


def _grant_for_order(order_id: str, payment_id: str | None) -> bool:
    res = payments.update_one({"order_id": order_id, "payment_status": {"$ne": "paid"}},
                              {"$set": {"status": "completed", "payment_status": "paid",
                                        "payment_id": payment_id, "updated_at": _now()}})
    if res.modified_count != 1:
        return False
    tx = payments.find_one({"order_id": order_id}, {"_id": 0})
    users.update_one({"user_id": tx["user_id"]}, {"$inc": {"credits": tx["credits"]}})
    ledger.insert_one({"user_id": tx["user_id"], "type": "purchase", "credits": tx["credits"],
                       "detail": f"{tx['pack_name']} pack", "order_id": order_id, "created_at": _now()})
    return True


@billing_router.get("/me")
def me(member: dict = Depends(member_dep)):
    return {"credits": member.get("credits", 0), "email": member.get("email"), "currency": CURRENCY,
            "packs": list(PACKS.values()), "paid_actions": PAID_ACTIONS, "free_credits": FREE_CREDITS,
            "payments_enabled": bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"))}


class OrderIn(BaseModel):
    pack_id: str


@billing_router.post("/orders")
def create_order(body: OrderIn, member: dict = Depends(member_dep)):
    pack = PACKS.get(body.pack_id)
    if not pack:
        raise HTTPException(404, detail="Unknown credit pack")
    client = _razorpay()
    receipt = f"dt_{int(datetime.now(timezone.utc).timestamp())}_{member['user_id'][-8:]}"[:40]
    order = client.order.create({"amount": int(round(pack["amount"] * 100)), "currency": CURRENCY,
                                 "receipt": receipt, "payment_capture": 1,
                                 "notes": {"user_id": member["user_id"], "pack_id": pack["id"]}})
    payments.insert_one({"order_id": order["id"], "user_id": member["user_id"], "pack_id": pack["id"],
                         "pack_name": pack["name"], "credits": pack["credits"], "amount": pack["amount"],
                         "currency": CURRENCY, "status": "initiated", "payment_status": "pending",
                         "created_at": _now(), "updated_at": _now()})
    return {"order_id": order["id"], "amount": order["amount"], "currency": CURRENCY,
            "key_id": os.environ["RAZORPAY_KEY_ID"], "email": member.get("email"),
            "description": f"{pack['credits']} Decision Trust credits"}


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@billing_router.post("/verify")
def verify_payment(body: VerifyIn, member: dict = Depends(member_dep)):
    tx = payments.find_one({"order_id": body.razorpay_order_id, "user_id": member["user_id"]}, {"_id": 0})
    if not tx:
        raise HTTPException(404, detail="Order not found")
    try:
        _razorpay().utility.verify_payment_signature(body.model_dump())
    except razorpay.errors.SignatureVerificationError:
        payments.update_one({"order_id": body.razorpay_order_id, "payment_status": {"$ne": "paid"}},
                            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": _now()}})
        raise HTTPException(400, detail="Payment could not be verified")
    _grant_for_order(body.razorpay_order_id, body.razorpay_payment_id)
    fresh = users.find_one({"user_id": member["user_id"]}, {"_id": 0})
    return {"payment_status": "paid", "credits": fresh["credits"]}


class FailIn(BaseModel):
    order_id: str
    reason: str | None = None


@billing_router.post("/failed")
def mark_failed(body: FailIn, member: dict = Depends(member_dep)):
    payments.update_one({"order_id": body.order_id, "user_id": member["user_id"], "payment_status": "pending"},
                        {"$set": {"status": "failed", "payment_status": "failed",
                                  "failure_reason": (body.reason or "")[:200], "updated_at": _now()}})
    return {"ok": True}


@billing_router.post("/webhook")
async def razorpay_webhook(request: Request):
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, detail="Webhook not configured")
    payload = await request.body()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(400, detail="Invalid signature")
    event = json.loads(payload)
    if event.get("event") in ("payment.captured", "order.paid"):
        pay = event["payload"]["payment"]["entity"]
        if pay.get("order_id"):
            _grant_for_order(pay["order_id"], pay.get("id"))
    elif event.get("event") == "payment.failed":
        pay = event["payload"]["payment"]["entity"]
        payments.update_one({"order_id": pay.get("order_id"), "payment_status": "pending"},
                            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": _now()}})
    return {"status": "ok"}


@billing_router.get("/history")
def history(member: dict = Depends(member_dep)):
    uid = member["user_id"]
    purchases = list(payments.find({"user_id": uid, "payment_status": {"$in": ["paid", "failed", "pending"]}},
                                   {"_id": 0, "user_id": 0}).sort("created_at", -1).limit(200))
    usage = list(ledger.find({"user_id": uid}, {"_id": 0, "user_id": 0}).sort("created_at", -1).limit(500))
    return {"purchases": purchases, "ledger": usage, "credits": member.get("credits", 0)}
