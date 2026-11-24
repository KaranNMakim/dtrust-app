"""Per-user workspaces. 'demo' = the Acme sample company (free, in memory, resets).
'mine' = the user's own data, saved as an event log in Mongo and replayed on load; actions there use credits."""

from __future__ import annotations

import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from pymongo import ReturnDocument
from starlette.concurrency import run_in_threadpool

from clerk_auth import require_user
from billing import db, ensure_member, spend_credit

from .config import settings
from .engine import TrustEngine
from .llm import ClaudeGateway
from .store import Store

log = logging.getLogger("decision_trust")
llm = ClaudeGateway(settings)
events = db["workspace_events"]
events.create_index([("user_id", 1), ("seq", 1)])

WORKSPACES = ("demo", "mine")
_engines: dict[tuple[str, str], TrustEngine] = {}
_ask_logs: dict[tuple[str, str], list[dict]] = {}
_lock = threading.Lock()
_engine_var: ContextVar[TrustEngine] = ContextVar("engine")
_member_var: ContextVar[dict] = ContextVar("member")
_ws_var: ContextVar[str] = ContextVar("workspace")

INGEST_LOADERS = {
    "glossary": ("glossary", "add_glossary"),
    "metric": ("metrics", "add_metric"),
    "dashboard": ("dashboards", "add_dashboard"),
    "lineage": ("lineage", "add_lineage"),
    "recommendation": ("recommendations", "add_recommendation"),
}


def apply_ingest(eng: TrustEngine, source_type: str, rows: list[dict], mode: str) -> tuple[int, list[dict]]:
    attr, loader = INGEST_LOADERS[source_type]
    if mode == "replace":
        getattr(eng.store, attr).clear()
    errors, ok = [], 0
    for i, r in enumerate(rows, start=2):
        try:
            getattr(eng.store, loader)(r)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"row": i, "error": str(exc)})
    return ok, errors


def apply_extract(eng: TrustEngine, metrics: list[dict], dashboards: list[dict]) -> None:
    for row in metrics:
        eng.store.add_metric(row)
    for row in dashboards:
        eng.store.add_dashboard(row)


def _replay(eng: TrustEngine, user_id: str) -> None:
    for ev in events.find({"user_id": user_id}, {"_id": 0}).sort([("seq", 1), ("created_at", 1)]):
        try:
            p = ev["payload"]
            if ev["op"] == "ingest":
                apply_ingest(eng, p["source_type"], p["rows"], p["mode"])
                eng.recompute()
            elif ev["op"] == "extract":
                apply_extract(eng, p["metrics"], p["dashboards"])
                eng.recompute()
            elif ev["op"] == "action":
                getattr(eng, p["method"])(*p["args"], **p["kwargs"])
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipped workspace event %s for %s: %s", ev.get("seq"), user_id, exc)
    eng.recompute()


def engine_for(user_id: str, ws: str) -> TrustEngine:
    key = (user_id, ws)
    with _lock:
        if key not in _engines:
            explainer = llm.explain if llm.enabled else None
            if ws == "demo":
                eng = TrustEngine(Store.from_dir(settings.data_dir), settings.now, explainer=explainer)
            else:
                eng = TrustEngine(Store(), settings.now, explainer=explainer)
                _replay(eng, user_id)
            _engines[key] = eng
            _ask_logs[key] = []
        return _engines[key]


class _EngineProxy:
    def __getattr__(self, name):
        return getattr(_engine_var.get(), name)


engine = _EngineProxy()


async def bind_user(request: Request) -> dict:
    ws = request.headers.get("x-workspace", "demo")
    if ws not in WORKSPACES:
        raise HTTPException(400, detail="Unknown workspace")
    user = await run_in_threadpool(require_user, request)
    member = await run_in_threadpool(ensure_member, user["user_id"])
    eng = await run_in_threadpool(engine_for, user["user_id"], ws)
    _engine_var.set(eng)
    _member_var.set(member)
    _ws_var.set(ws)
    return member


def current_email() -> str:
    m = _member_var.get()
    return m.get("email") or m["user_id"]


def current_workspace() -> str:
    return _ws_var.get()


def user_ask_log() -> list[dict]:
    return _ask_logs[(_member_var.get()["user_id"], _ws_var.get())]


def paid_action() -> str | None:
    """Free in the demo workspace; 1 credit in the user's own workspace. Returns the user id to charge."""
    if _ws_var.get() == "demo":
        return None
    m = _member_var.get()
    if m.get("credits", 0) < 1:
        raise HTTPException(402, detail={"title": "Out of credits", "status": 402,
                                         "detail": "You're out of credits. Buy a credit pack to keep going."})
    return m["user_id"]


def charge(uid: str | None, action: str, detail: str | None = None) -> None:
    if uid:
        spend_credit(uid, action, detail)


def own_data_only() -> None:
    if _ws_var.get() == "demo":
        raise HTTPException(403, detail={"title": "Demo workspace", "status": 403,
                                         "detail": "The Acme demo is read-only for new data. Switch to My workspace to add your own."})


def record(op: str, payload: dict) -> None:
    """Persist a change to the user's own workspace so it survives restarts."""
    if _ws_var.get() != "mine":
        return
    uid = _member_var.get()["user_id"]
    key = f"ws_events:{uid}"
    if not db["counters"].find_one({"_id": key}):
        db["counters"].update_one({"_id": key}, {"$setOnInsert": {"n": events.count_documents({"user_id": uid}) - 1}},
                                  upsert=True)
    seq = db["counters"].find_one_and_update({"_id": key}, {"$inc": {"n": 1}}, upsert=True,
                                             return_document=ReturnDocument.AFTER)["n"]
    events.insert_one({"user_id": uid, "seq": seq, "op": op, "payload": payload,
                       "created_at": datetime.now(timezone.utc).isoformat()})
