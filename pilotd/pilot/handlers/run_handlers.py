"""Run history RPCs — backed by the memory store."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from pilot import service

Emit = Callable[[dict[str, Any]], Awaitable[None]]


async def list_(params: dict[str, Any], emit: Emit) -> None:
    workflow_id = params.get("workflow_id")
    limit = int(params.get("limit", 50))
    rows = service.container().memory().list_runs(workflow_id=workflow_id, limit=limit)
    await emit({"event": "done", "status": "ok", "runs": rows})


async def get(params: dict[str, Any], emit: Emit) -> None:
    run_id = params.get("run_id")
    if not run_id:
        await emit({"event": "error", "error": "missing 'run_id'"})
        return
    row = service.container().memory().get_run(run_id)
    if row is None:
        await emit({"event": "error", "error": f"run not found: {run_id}"})
        return
    await emit({"event": "done", "status": row.get("status"), **row})


METHODS = {
    "list": list_,
    "get": get,
}
