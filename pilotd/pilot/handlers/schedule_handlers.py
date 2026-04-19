"""Schedule CRUD + NL-cadence helper RPCs."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pilot import service
from pilot.scheduler import Scheduler, register as register_scheduler

log = logging.getLogger("pilotd.handlers.schedule")

Emit = Callable[[dict[str, Any]], Awaitable[None]]

_SCHEDULER: Scheduler | None = None


def _get_scheduler() -> Scheduler:
    global _SCHEDULER
    if _SCHEDULER is None:
        from pilot.scheduler_runtime import run_workflow_sync  # lazy to avoid cycles

        _SCHEDULER = Scheduler(run_callable=run_workflow_sync)
        register_scheduler(_SCHEDULER)
        _SCHEDULER.start()
    return _SCHEDULER


async def list_(_: dict[str, Any], emit: Emit) -> None:
    try:
        jobs = _get_scheduler().list_jobs()
    except Exception as exc:
        log.exception("schedule.list failed")
        await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    await emit({"event": "done", "status": "ok", "jobs": jobs})


async def create(params: dict[str, Any], emit: Emit) -> None:
    name = params.get("workflow_name") or params.get("name")
    cron_expr = params.get("cron_expr") or params.get("cron")
    if not name or not cron_expr:
        await emit({
            "event": "error",
            "error": "missing 'workflow_name' or 'cron_expr'",
        })
        return
    if service.container().load_workflow(name) is None:
        await emit({"event": "error", "error": f"unknown workflow: {name}"})
        return
    jid = _get_scheduler().add_job(
        workflow_name=name,
        cron_expr=cron_expr,
        params=params.get("params") or {},
    )
    await emit({"event": "done", "status": "ok", "job_id": jid})


async def delete(params: dict[str, Any], emit: Emit) -> None:
    jid = params.get("job_id")
    if not jid:
        await emit({"event": "error", "error": "missing 'job_id'"})
        return
    _get_scheduler().remove_job(jid)
    await emit({"event": "done", "status": "ok", "job_id": jid})


async def toggle(params: dict[str, Any], emit: Emit) -> None:
    jid = params.get("job_id")
    enabled = bool(params.get("enabled", True))
    if not jid:
        await emit({"event": "error", "error": "missing 'job_id'"})
        return
    sch = _get_scheduler()
    if enabled:
        sch.resume_job(jid)
    else:
        sch.pause_job(jid)
    await emit({"event": "done", "status": "ok", "job_id": jid, "enabled": enabled})


async def run_now(params: dict[str, Any], emit: Emit) -> None:
    name = params.get("workflow_name") or params.get("name")
    if not name:
        await emit({"event": "error", "error": "missing 'workflow_name'"})
        return
    if service.container().load_workflow(name) is None:
        await emit({"event": "error", "error": f"unknown workflow: {name}"})
        return
    jid = _get_scheduler().run_now(name, params=params.get("params") or {})
    await emit({"event": "done", "status": "ok", "job_id": jid})


async def parse_cadence(params: dict[str, Any], emit: Emit) -> None:
    """NL cadence → 5-field cron. Haiku-backed."""
    text = params.get("text")
    if not text:
        await emit({"event": "error", "error": "missing 'text'"})
        return
    try:
        cron_expr = service.container().planner().parse_cron(text)
    except Exception as exc:
        await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    await emit({"event": "done", "status": "ok", "cron_expr": cron_expr})


METHODS = {
    "list": list_,
    "create": create,
    "delete": delete,
    "toggle": toggle,
    "run_now": run_now,
    "parse_cadence": parse_cadence,
}
