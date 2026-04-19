"""Session recording RPCs. Filled out in M4."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

Emit = Callable[[dict[str, Any]], Awaitable[None]]


async def _stub(name: str, emit: Emit) -> None:
    await emit({"event": "error", "error": f"session.{name} not implemented (M4)"})


async def start_record(_: dict[str, Any], emit: Emit) -> None:
    await _stub("start_record", emit)


async def stop_record(_: dict[str, Any], emit: Emit) -> None:
    await _stub("stop_record", emit)


METHODS = {
    "start_record": start_record,
    "stop_record": stop_record,
}
