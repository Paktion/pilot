"""
Daemon entry: ``python -m pilot``.

M0 scope — load prompt env, start asyncio Unix-socket server, serve
``health.check``. Handlers are dispatched by method prefix; see
``pilot.sockserver`` and ``pilot.handlers``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from pilot import prompts
from pilot.sockserver import SocketServer


def _default_socket_path() -> Path:
    override = os.environ.get("PILOT_SOCKET")
    if override:
        return Path(override).expanduser()
    home = os.environ.get("PILOT_HOME", "~/Library/Application Support/Pilot")
    return Path(home).expanduser() / "pilotd.sock"


async def _run() -> int:
    logging.basicConfig(
        level=os.environ.get("PILOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("pilotd")

    prompts.load_env()
    # NOTE: don't require_all() yet — M0 only needs health.check to work.
    # Once the agent loop is wired in M1, call prompts.require_all() here.
    log.info("prompt env loaded, sizes=%s", prompts.snapshot())

    socket_path = _default_socket_path()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    server = SocketServer(socket_path)
    stop = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        log.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    async with server.serve():
        log.info("pilotd listening at %s", socket_path)
        await stop.wait()

    log.info("pilotd stopped")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
