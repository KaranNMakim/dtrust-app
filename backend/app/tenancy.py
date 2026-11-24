"""Per-user workspaces: each signed-in user gets their own in-memory TrustEngine seeded with the demo data."""

from __future__ import annotations

import threading
from contextvars import ContextVar

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from clerk_auth import require_user
from billing import ensure_member

from .config import settings
from .engine import TrustEngine
from .llm import ClaudeGateway
from .store import Store

llm = ClaudeGateway(settings)

_engines: dict[str, TrustEngine] = {}
_ask_logs: dict[str, list[dict]] = {}
_lock = threading.Lock()
_engine_var: ContextVar[TrustEngine] = ContextVar("engine")
_member_var: ContextVar[dict] = ContextVar("member")


def engine_for(user_id: str) -> TrustEngine:
    with _lock:
        if user_id not in _engines:
            _engines[user_id] = TrustEngine(Store.from_dir(settings.data_dir), settings.now,
                                            explainer=llm.explain if llm.enabled else None)
            _ask_logs[user_id] = []
        return _engines[user_id]


class _EngineProxy:
    def __getattr__(self, name):
        return getattr(_engine_var.get(), name)


engine = _EngineProxy()


async def bind_user(request: Request) -> dict:
    user = await run_in_threadpool(require_user, request)
    member = await run_in_threadpool(ensure_member, user["user_id"])
    eng = await run_in_threadpool(engine_for, user["user_id"])
    _engine_var.set(eng)
    _member_var.set(member)
    return member


def current_email() -> str:
    m = _member_var.get()
    return m.get("email") or m["user_id"]


def engine_user_id() -> str:
    return _member_var.get()["user_id"]


def user_ask_log() -> list[dict]:
    return _ask_logs[_member_var.get()["user_id"]]
