"""Display-name pass: rewrite internal ids inside user-facing sentences as display names.

Only strings containing whitespace are rewritten; single-token values (ids used for links and keys) stay intact.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute

from .store import Store

_cache: dict[int, tuple[int, re.Pattern | None, dict[str, str]]] = {}


def _names(store: Store) -> tuple[re.Pattern | None, dict[str, str]]:
    key = id(store)
    size = len(store.node_names)
    hit = _cache.get(key)
    if hit and hit[0] == size:
        return hit[1], hit[2]
    names = {i: n for i, (_t, n) in store.node_names.items() if n and n != i and "_" in i}
    pattern = re.compile(r"(?<![\w.])(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")(?![\w])") \
        if names else None
    _cache[key] = (size, pattern, names)
    return pattern, names


def humanize(value: Any, store: Store) -> Any:
    pattern, names = _names(store)
    if not pattern:
        return value

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            if not any(ch.isspace() for ch in v):
                return v
            return pattern.sub(lambda m: names[m.group(1)], v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(value)


class HumanizedRoute(APIRoute):
    """Applies the display-name pass to every JSON response and error detail of the user's workspace."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            from .tenancy import current_store
            try:
                response = await original(request)
            except HTTPException as exc:
                store = current_store()
                if store is not None:
                    exc.detail = humanize(exc.detail, store)
                raise
            store = current_store()
            if store is None or response.media_type != "application/json":
                return response
            body = humanize(json.loads(response.body), store)
            headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
            return Response(json.dumps(body), status_code=response.status_code,
                            media_type="application/json", headers=headers)

        return handler
