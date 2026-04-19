"""Usage / cost RPCs."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from pilot import service

Emit = Callable[[dict[str, Any]], Awaitable[None]]


async def summary(_: dict[str, Any], emit: Emit) -> None:
    usage = service.container().usage()
    cfg = service.container().config()
    out = usage.get_usage_summary()
    out.update({
        "daily_cost": usage.get_daily_cost(),
        "monthly_cost": usage.get_monthly_cost(),
        "daily_budget": float(cfg.get("max_daily_budget", 5.0)),
        "monthly_budget": float(cfg.get("max_monthly_budget", 50.0)),
        "per_task_budget": float(cfg.get("per_task_budget", 1.0)),
    })
    await emit({"event": "done", "status": "ok", **out})


async def report(params: dict[str, Any], emit: Emit) -> None:
    days = int(params.get("days", 30))
    usage = service.container().usage()
    await emit({"event": "done", "status": "ok", "days": usage.get_usage_report(days)})


METHODS = {
    "summary": summary,
    "report": report,
}
