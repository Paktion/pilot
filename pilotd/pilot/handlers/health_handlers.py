"""Health / diagnostics RPCs."""

from __future__ import annotations

import os
import platform
import time
from typing import Any, Awaitable, Callable

from pilot import __version__, prompts
from pilot.core.utils.sys_checks import run_system_check

Emit = Callable[[dict[str, Any]], Awaitable[None]]

_STARTED_AT = time.time()


async def check(params: dict[str, Any], emit: Emit) -> None:
    """Report daemon status. Safe to call cheaply from the UI / pre-run gate."""
    await emit(
        {
            "event": "done",
            "status": "ok",
            "version": __version__,
            "pid": os.getpid(),
            "uptime_s": round(time.time() - _STARTED_AT, 1),
            "platform": platform.platform(),
            "anthropic_api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "prompts_loaded": prompts.snapshot(),
        }
    )


async def full_check(_: dict[str, Any], emit: Emit) -> None:
    """Run the full system check — macOS version, permissions, deps.

    Heavier than ``check`` because it spawns ``osascript``/``screencapture``
    subprocesses. Used by onboarding.
    """
    report = run_system_check()
    await emit({"event": "done", "status": "ok" if report["all_ok"] else "issues", **report})


async def mirroring(_: dict[str, Any], emit: Emit) -> None:
    """Fast, focused probe of iPhone Mirroring availability.

    Cheaper than ``health.full_check`` because it skips the Accessibility +
    Screen Recording subprocess round-trips. Callable on every pre-run gate
    without hammering the system.
    """
    from pilot.core.utils.sys_checks import check_iphone_mirroring_window
    ok, desc = check_iphone_mirroring_window()
    await emit({
        "event": "done",
        "status": "ok" if ok else "unavailable",
        "available": ok,
        "detail": desc,
    })


METHODS = {
    "check": check,
    "full_check": full_check,
    "mirroring": mirroring,
}
