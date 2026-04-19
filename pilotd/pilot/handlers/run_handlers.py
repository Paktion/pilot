"""Run history + live-run control RPCs."""

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


async def get_events(params: dict[str, Any], emit: Emit) -> None:
    """Return the buffered event stream for a run, from ``since`` onwards.

    Used by MCP tools that poll mid-run and by UIs that reconnect.
    """
    from pilot.handlers.workflow_handlers import active_channel

    run_id = params.get("run_id")
    if not run_id:
        await emit({"event": "error", "error": "missing 'run_id'"})
        return
    since = int(params.get("since", 0))
    channel = active_channel(run_id)
    if channel is None:
        # Run is no longer active — fall back to persisted run row.
        row = service.container().memory().get_run(run_id)
        if row is None:
            await emit({"event": "error", "error": f"unknown run: {run_id}"})
            return
        await emit({
            "event": "done",
            "status": "ok",
            "events": [],
            "still_running": False,
            "final_status": row.get("status"),
            "summary": row.get("summary"),
        })
        return
    events = channel.snapshot(since=since)
    await emit({
        "event": "done",
        "status": "ok",
        "events": events,
        "still_running": True,
        "next_since": since + len(events),
    })


async def abort(params: dict[str, Any], emit: Emit) -> None:
    """Request cooperative abort of a running workflow."""
    from pilot.handlers.workflow_handlers import active_channel

    run_id = params.get("run_id")
    if not run_id:
        await emit({"event": "error", "error": "missing 'run_id'"})
        return
    channel = active_channel(run_id)
    if channel is None:
        await emit({"event": "error", "error": f"run not active: {run_id}"})
        return
    channel.mark_abort()
    await emit({"event": "done", "status": "ok", "aborting": True})


async def diagnose(params: dict[str, Any], emit: Emit) -> None:
    """Haiku-backed post-mortem on a completed run."""
    run_id = params.get("run_id")
    if not run_id:
        await emit({"event": "error", "error": "missing 'run_id'"})
        return
    row = service.container().memory().get_run(run_id)
    if row is None:
        await emit({"event": "error", "error": f"run not found: {run_id}"})
        return
    context = (
        f"Workflow run {run_id} finished with status={row.get('status')}. "
        f"Summary: {row.get('summary','(none)')}."
    )
    try:
        text = service.container().planner().diagnose_failure(context)
    except Exception as exc:
        await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    await emit({"event": "done", "status": "ok", "diagnosis": text})


METHODS = {
    "list": list_,
    "get": get,
    "get_events": get_events,
    "abort": abort,
    "diagnose": diagnose,
}
