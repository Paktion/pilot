"""Semantic-memory query RPC."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from pilot import service

Emit = Callable[[dict[str, Any]], Awaitable[None]]


async def query(params: dict[str, Any], emit: Emit) -> None:
    q = params.get("query")
    if not q:
        await emit({"event": "error", "error": "missing 'query'"})
        return
    workflow_id = params.get("workflow_id")
    k = int(params.get("k", 5))
    hits = service.container().memory().search_similar(
        query_text=q, workflow_id=workflow_id, k=k
    )
    # value_json is a JSON-encoded string; decode for ergonomics.
    for h in hits:
        try:
            h["value"] = json.loads(h.get("value_json", "null"))
        except (TypeError, json.JSONDecodeError):
            h["value"] = h.get("value_json")
    await emit({"event": "done", "status": "ok", "hits": hits})


METHODS = {"query": query}
