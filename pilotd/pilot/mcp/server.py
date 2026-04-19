"""
Minimal MCP JSON-RPC-over-stdio server.

Implements just enough of the MCP spec (``initialize``, ``tools/list``,
``tools/call``) to be registered with Claude Code via:

    claude mcp add --transport stdio pilot -- python -m pilot.mcp

Tools surfaced are gated by the permission policy (``permissions.py``);
hidden tools are literally absent from ``tools/list``, so the model cannot
call what it can't see.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable

from pilot.mcp.client import DaemonClient
from pilot.mcp.permissions import PermissionPolicy, load_policy

log = logging.getLogger("pilotd.mcp.server")

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "pilot", "version": "0.0.1"}

ToolHandler = Callable[[dict[str, Any], DaemonClient], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


def _list_workflows(_args: dict[str, Any], client: DaemonClient) -> dict[str, Any]:
    res = client.call("workflow.list", {})
    if res.get("event") == "error":
        raise RuntimeError(res.get("error", "unknown error"))
    return {"workflows": res.get("workflows", [])}


def _run_workflow(args: dict[str, Any], client: DaemonClient) -> dict[str, Any]:
    name = args["name"]
    params = args.get("params") or {}
    res = client.call("workflow.run", {"name": name, "params": params})
    if res.get("event") == "error":
        raise RuntimeError(res.get("error", "unknown error"))
    return {
        "run_id": res.get("run_id", ""),
        "status": res.get("status", "started"),
    }


def _get_run_status(args: dict[str, Any], client: DaemonClient) -> dict[str, Any]:
    run_id = args["run_id"]
    res = client.call("run.get", {"run_id": run_id})
    if res.get("event") == "error":
        raise RuntimeError(res.get("error", "unknown error"))
    return {
        "status": res.get("status"),
        "summary": res.get("summary", ""),
        "cost_usd": res.get("cost_usd", 0.0),
    }


def _get_memory(args: dict[str, Any], client: DaemonClient) -> dict[str, Any]:
    workflow_id = args.get("workflow_id")
    query = args["query"]
    res = client.call("memory.query", {"workflow_id": workflow_id, "query": query})
    if res.get("event") == "error":
        raise RuntimeError(res.get("error", "unknown error"))
    return {"hits": res.get("hits", [])}


_TOOLS: dict[str, ToolSpec] = {
    "list_workflows": ToolSpec(
        name="list_workflows",
        description="List saved Pilot workflows (name, app, tags, last run).",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_list_workflows,
    ),
    "run_workflow": ToolSpec(
        name="run_workflow",
        description="Trigger a workflow by name and return its run_id.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["name"],
        },
        handler=_run_workflow,
    ),
    "get_run_status": ToolSpec(
        name="get_run_status",
        description="Return status, summary, and cost for a run_id.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
        handler=_get_run_status,
    ),
    "get_memory": ToolSpec(
        name="get_memory",
        description="Semantic search over memory rows scoped to a workflow.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": ["string", "null"]},
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
        handler=_get_memory,
    ),
}


class MCPServer:
    def __init__(
        self,
        *,
        policy: PermissionPolicy | None = None,
        client: DaemonClient | None = None,
        stdin=None,
        stdout=None,
    ) -> None:
        self._policy = policy or load_policy()
        self._client = client or DaemonClient()
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout

    def serve(self) -> None:
        for line in self._stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                self._write(_error_reply(None, -32700, f"parse error: {exc}"))
                continue
            reply = self._dispatch(request)
            if reply is not None:
                self._write(reply)

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}
        if method == "initialize":
            return _result(request_id, {
                "protocolVersion": _PROTOCOL_VERSION,
                "serverInfo": _SERVER_INFO,
                "capabilities": {"tools": {}},
            })
        if method == "initialized":
            return None  # notification
        if method == "tools/list":
            visible = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in _TOOLS.values()
                if self._policy.is_tool_visible(t.name)
            ]
            return _result(request_id, {"tools": visible})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        return _error_reply(request_id, -32601, f"method not found: {method}")

    def _call_tool(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        args = params.get("arguments") or {}
        tool = _TOOLS.get(name)
        if tool is None or not self._policy.is_tool_visible(name):
            return _error_reply(request_id, -32601, f"unknown or blocked tool: {name}")
        if name == "run_workflow":
            wf_name = args.get("name", "")
            if self._policy.is_workflow_blocked(wf_name):
                return _tool_error_reply(
                    request_id, f"workflow {wf_name!r} is blocked by policy"
                )
        try:
            out = tool.handler(args, self._client)
        except Exception as exc:  # surface to client, keep server alive
            log.exception("tool %s failed", name)
            return _tool_error_reply(request_id, f"{type(exc).__name__}: {exc}")
        return _result(request_id, {
            "content": [{"type": "text", "text": json.dumps(out)}],
            "isError": False,
        })

    def _write(self, reply: dict[str, Any]) -> None:
        self._stdout.write(json.dumps(reply) + "\n")
        self._stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_reply(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_error_reply(request_id: Any, message: str) -> dict[str, Any]:
    return _result(request_id, {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    })


__all__ = ["MCPServer", "ToolSpec"]
