"""Unix-socket client that proxies MCP tool calls to the live daemon."""

from __future__ import annotations

import json
import logging
import socket
import threading
import uuid
from pathlib import Path
from typing import Any

from pilot.core import paths

log = logging.getLogger("pilotd.mcp.client")


class DaemonClient:
    """Thread-safe blocking client over the daemon's newline-delimited JSON-RPC."""

    def __init__(self, socket_path: Path | None = None, timeout: float = 30.0) -> None:
        self._path = socket_path or paths.socket_path()
        self._timeout = timeout
        self._lock = threading.Lock()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a request, return the first ``done`` or ``error`` event."""
        request_id = str(uuid.uuid4())
        envelope = {"request_id": request_id, "method": method, "params": params or {}}
        with self._lock:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self._timeout)
                sock.connect(str(self._path))
                sock.sendall((json.dumps(envelope) + "\n").encode("utf-8"))
                buf = b""
                while b"\n" not in buf:
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise ConnectionError("daemon closed connection")
                    buf += chunk
                    # Keep reading — multiple events may stream in before `done`.
                    frames = buf.split(b"\n")
                    buf = frames[-1]
                    for raw_line in frames[:-1]:
                        if not raw_line.strip():
                            continue
                        frame = json.loads(raw_line)
                        event = frame.get("event")
                        if event in ("done", "error"):
                            return frame
        raise RuntimeError(f"no terminal event for method {method}")
