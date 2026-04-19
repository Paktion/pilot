"""Smoke-test the asyncio socket server against health.check."""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest

from pilot.sockserver import SocketServer


@contextlib.asynccontextmanager
async def _short_socket() -> AsyncIterator[Path]:
    # macOS caps AF_UNIX paths at ~104 bytes; pytest's tmp_path under
    # /private/var/folders/... is too deep, so anchor directly under /tmp.
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        yield Path(d) / "p.sock"


@pytest.mark.asyncio
async def test_health_check_round_trip() -> None:
    async with _short_socket() as sock:
        server = SocketServer(sock)
        async with server.serve():
            reader, writer = await asyncio.open_unix_connection(str(sock))
            writer.write(
                (json.dumps({"request_id": "abc", "method": "health.check"}) + "\n").encode()
            )
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            frame = json.loads(line)

            assert frame["request_id"] == "abc"
            assert frame["event"] == "done"
            assert frame["status"] == "ok"
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_unknown_method_returns_error() -> None:
    async with _short_socket() as sock:
        server = SocketServer(sock)
        async with server.serve():
            reader, writer = await asyncio.open_unix_connection(str(sock))
            writer.write(
                (json.dumps({"request_id": "1", "method": "nope.nope"}) + "\n").encode()
            )
            await writer.drain()
            frame = json.loads(await asyncio.wait_for(reader.readline(), timeout=2.0))
            assert frame["event"] == "error"
            assert "unknown method" in frame["error"]
            writer.close()
            await writer.wait_closed()
