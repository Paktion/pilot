"""
Asyncio Unix-socket JSON-RPC server.

Each connection reads newline-delimited JSON requests of the shape::

    {"request_id": "<uuid>", "method": "workflow.run", "params": {...}}

and emits one or more newline-delimited JSON events back::

    {"request_id": "<uuid>", "event": "started", "run_id": "..."}
    {"request_id": "<uuid>", "event": "done", "status": "success"}

Method names are ``<category>.<action>``. Dispatch is done by category —
each ``pilot.handlers.<category>_handlers`` module exposes a ``METHODS``
dict ``{action_name: async_callable}``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

log = logging.getLogger("pilotd.sock")

# Dispatch callable: (params, emit) -> None.
# ``emit`` writes an event frame for the current request.
Emit = Callable[[dict[str, Any]], Awaitable[None]]
Handler = Callable[[dict[str, Any], Emit], Awaitable[None]]


def _load_handlers() -> dict[str, Handler]:
    """Collect ``{method: handler}`` from every handlers submodule."""
    from pilot.handlers import (
        health_handlers,
        memory_handlers,
        run_handlers,
        schedule_handlers,
        session_handlers,
        workflow_handlers,
    )

    registry: dict[str, Handler] = {}
    modules = {
        "health": health_handlers,
        "memory": memory_handlers,
        "run": run_handlers,
        "schedule": schedule_handlers,
        "session": session_handlers,
        "workflow": workflow_handlers,
    }
    for category, mod in modules.items():
        for action, fn in getattr(mod, "METHODS", {}).items():
            registry[f"{category}.{action}"] = fn
    return registry


class SocketServer:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path
        self._handlers: dict[str, Handler] = {}
        self._server: asyncio.base_events.Server | None = None

    @contextlib.asynccontextmanager
    async def serve(self) -> AsyncIterator["SocketServer"]:
        self._handlers = _load_handlers()
        self._server = await asyncio.start_unix_server(
            self._on_connection, path=str(self.socket_path)
        )
        try:
            yield self
        finally:
            self._server.close()
            await self._server.wait_closed()
            with contextlib.suppress(FileNotFoundError):
                self.socket_path.unlink()

    async def _on_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername", "<unix>")
        log.debug("client connected: %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line)
                except json.JSONDecodeError as exc:
                    await _write(writer, {"event": "error", "error": f"bad json: {exc}"})
                    continue
                asyncio.create_task(self._dispatch(req, writer))
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _dispatch(self, req: dict[str, Any], writer: asyncio.StreamWriter) -> None:
        request_id = req.get("request_id")
        method = req.get("method", "")
        params = req.get("params") or {}
        handler = self._handlers.get(method)

        async def emit(event: dict[str, Any]) -> None:
            frame = {"request_id": request_id, **event}
            await _write(writer, frame)

        if handler is None:
            await emit({"event": "error", "error": f"unknown method: {method}"})
            return

        try:
            await handler(params, emit)
        except Exception as exc:  # surface to client, keep daemon alive
            log.exception("handler %s failed", method)
            await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})


async def _write(writer: asyncio.StreamWriter, frame: dict[str, Any]) -> None:
    payload = (json.dumps(frame) + "\n").encode("utf-8")
    writer.write(payload)
    await writer.drain()
