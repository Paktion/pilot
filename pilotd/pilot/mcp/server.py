"""
Minimal MCP JSON-RPC-over-stdio server.

Exposes workflow-level tools to MCP clients (Claude Code, Cursor, Codex).
Tools are gated by ``permissions.py``; hidden tools are literally absent
from ``tools/list``, so the model cannot call what it can't see.

Tool surface:
    read-only (default ALLOW):
        check_health         — daemon + prompt status
        list_workflows       — array of saved workflows
        get_run_status       — status + summary + cost for a run_id
        get_run_events       — buffered event stream for an active/past run
        get_memory           — vector top-k over semantic memory
        diagnose_failure     — Haiku-backed post-mortem on a failed run
        draft_workflow       — NL description → YAML (no write)
        device_screenshot    — capture current iPhone screen (JPEG)
        device_extract       — vision-QA against the current screen
    mutating (default DENY — user must flip in permissions.json):
        save_workflow        — persist a YAML draft
        run_workflow         — trigger a workflow by name
        schedule_workflow    — register a cron schedule
        abort_run            — request cooperative abort of a running workflow
        device_tap           — raw coordinate tap
        device_tap_text      — vision-backed tap by label
        device_swipe         — directional swipe
        device_long_press    — press-and-hold
        device_type_text     — type into focused field
        device_press_key     — hardware key (+ modifiers)
        device_press_home    — return to home screen
        device_launch_app    — open app via Spotlight
        device_reset         — drop cached device controller
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
    mutating: bool = False


# ---------------------------------------------------------------------------
# Tool handlers (thin adapters over daemon RPCs)
# ---------------------------------------------------------------------------


def _unwrap(res: dict[str, Any]) -> dict[str, Any]:
    if res.get("event") == "error":
        raise RuntimeError(res.get("error", "unknown error"))
    return res


def _check_health(_args, client):
    r = _unwrap(client.call("health.check", {}))
    return {
        k: r[k] for k in (
            "status", "version", "pid", "uptime_s",
            "platform", "anthropic_api_key_set",
        ) if k in r
    }


def _list_workflows(_args, client):
    r = _unwrap(client.call("workflow.list", {}))
    return {"workflows": r.get("workflows", [])}


def _get_run_status(args, client):
    r = _unwrap(client.call("run.get", {"run_id": args["run_id"]}))
    return {k: r.get(k) for k in ("status", "summary", "cost_usd", "started_at", "ended_at")}


def _get_run_events(args, client):
    r = _unwrap(client.call(
        "run.get_events",
        {"run_id": args["run_id"], "since": args.get("since", 0)},
    ))
    return {
        "events": r.get("events", []),
        "still_running": r.get("still_running", False),
        "next_since": r.get("next_since"),
        "final_status": r.get("final_status"),
        "summary": r.get("summary"),
    }


def _get_memory(args, client):
    r = _unwrap(client.call("memory.query", {
        "workflow_id": args.get("workflow_id"),
        "query": args["query"],
        "k": args.get("k", 5),
    }))
    return {"hits": r.get("hits", [])}


def _diagnose_failure(args, client):
    r = _unwrap(client.call("run.diagnose", {"run_id": args["run_id"]}))
    return {"diagnosis": r.get("diagnosis", "")}


def _draft_workflow(args, client):
    r = _unwrap(client.call("workflow.draft", {"description": args["description"]}))
    return {"yaml": r.get("yaml", "")}


def _save_workflow(args, client):
    r = _unwrap(client.call("workflow.save", {"yaml": args["yaml"], "id": args.get("id")}))
    return {"id": r.get("id"), "name": r.get("name")}


def _run_workflow(args, client):
    # Streaming RPC — collect events until terminal. MCP can't stream, so we
    # return an accumulated result with the run_id and final status.
    import socket, json as _json
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(300)
    s.connect(str(client._path))
    envelope = {
        "request_id": "mcp-run",
        "method": "workflow.run",
        "params": {"name": args["name"], "params": args.get("params") or {}},
    }
    s.sendall((_json.dumps(envelope) + "\n").encode())
    buf = b""
    run_id = ""
    final = None
    events: list[dict] = []
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            frame = _json.loads(line)
            events.append(frame)
            ev = frame.get("event")
            if ev == "started":
                run_id = frame.get("run_id", "")
            if ev in ("done", "error", "failed", "aborted"):
                final = frame
                break
        if final is not None:
            break
    s.close()
    if final is None:
        raise RuntimeError("run terminated without a final event")
    return {
        "run_id": run_id,
        "status": final.get("status") or final.get("event"),
        "summary": final.get("summary") or final.get("error", ""),
        "event_count": len(events),
    }


def _schedule_workflow(args, client):
    r = _unwrap(client.call("schedule.create", {
        "workflow_name": args["name"],
        "cron_expr": args["cron_expr"],
        "params": args.get("params") or {},
    }))
    return {"job_id": r.get("job_id")}


def _abort_run(args, client):
    r = _unwrap(client.call("run.abort", {"run_id": args["run_id"]}))
    return {"aborting": r.get("aborting", True)}


# --- device.* thin adapters ------------------------------------------------


def _device_tap(args, client):
    r = _unwrap(client.call("device.tap", {"x": args["x"], "y": args["y"]}))
    return {"status": r.get("status")}


def _device_tap_text(args, client):
    r = _unwrap(client.call("device.tap_text", {
        "text": args["text"],
        "prefer": args.get("prefer"),
    }))
    return {"status": r.get("status")}


def _device_swipe(args, client):
    payload = {"direction": args["direction"]}
    if args.get("distance") is not None:
        payload["distance"] = args["distance"]
    r = _unwrap(client.call("device.swipe", payload))
    return {"status": r.get("status")}


def _device_long_press(args, client):
    r = _unwrap(client.call("device.long_press", {
        "x": args["x"], "y": args["y"],
        "duration": args.get("duration", 1.0),
    }))
    return {"status": r.get("status")}


def _device_type_text(args, client):
    r = _unwrap(client.call("device.type_text", {"text": args["text"]}))
    return {"status": r.get("status"), "length": r.get("length")}


def _device_press_key(args, client):
    payload: dict[str, Any] = {"key": args["key"]}
    if args.get("modifiers"):
        payload["modifiers"] = args["modifiers"]
    r = _unwrap(client.call("device.press_key", payload))
    return {"status": r.get("status")}


def _device_press_home(_args, client):
    r = _unwrap(client.call("device.press_home", {}))
    return {"status": r.get("status")}


def _device_launch_app(args, client):
    r = _unwrap(client.call("device.launch_app", {"app_name": args["app_name"]}))
    return {"status": r.get("status")}


def _device_screenshot(_args, client):
    r = _unwrap(client.call("device.screenshot", {}))
    return {
        "image_b64": r.get("image_b64"),
        "width": r.get("width"),
        "height": r.get("height"),
    }


def _device_extract(args, client):
    r = _unwrap(client.call("device.extract", {
        "question": args["question"],
        "type": args.get("expected_type", "string"),
        "hint": args.get("hint"),
    }))
    return {"answer": r.get("answer"), "confidence": r.get("confidence")}


def _device_reset(_args, client):
    r = _unwrap(client.call("device.reset", {}))
    return {"status": r.get("status")}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOLS: dict[str, ToolSpec] = {
    "check_health": ToolSpec(
        name="check_health",
        description="Return daemon status, uptime, and whether an Anthropic key is configured.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_check_health,
    ),
    "list_workflows": ToolSpec(
        name="list_workflows",
        description="Return saved workflows (name, app, tags, run/success counts).",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_list_workflows,
    ),
    "get_run_status": ToolSpec(
        name="get_run_status",
        description="Return status + summary + cost for a run_id.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
        handler=_get_run_status,
    ),
    "get_run_events": ToolSpec(
        name="get_run_events",
        description=(
            "Return the buffered event stream for a run. Poll with increasing "
            "'since' indexes to follow a live run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "since": {"type": "integer", "default": 0},
            },
            "required": ["run_id"],
        },
        handler=_get_run_events,
    ),
    "get_memory": ToolSpec(
        name="get_memory",
        description="Semantic top-k search over memory rows, optionally scoped to a workflow.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": ["string", "null"]},
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        handler=_get_memory,
    ),
    "diagnose_failure": ToolSpec(
        name="diagnose_failure",
        description="Haiku-backed one-paragraph diagnosis of a completed run by run_id.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
        handler=_diagnose_failure,
    ),
    "draft_workflow": ToolSpec(
        name="draft_workflow",
        description=(
            "Draft a workflow YAML from a natural-language description via Claude Sonnet. "
            "Does not save — pair with save_workflow."
        ),
        input_schema={
            "type": "object",
            "properties": {"description": {"type": "string"}},
            "required": ["description"],
        },
        handler=_draft_workflow,
    ),
    "save_workflow": ToolSpec(
        name="save_workflow",
        description="Persist a YAML workflow. Creates a new one or updates by id.",
        input_schema={
            "type": "object",
            "properties": {
                "yaml": {"type": "string"},
                "id": {"type": ["string", "null"]},
            },
            "required": ["yaml"],
        },
        handler=_save_workflow,
        mutating=True,
    ),
    "run_workflow": ToolSpec(
        name="run_workflow",
        description="Execute a workflow by name. Returns run_id + final status + summary.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["name"],
        },
        handler=_run_workflow,
        mutating=True,
    ),
    "schedule_workflow": ToolSpec(
        name="schedule_workflow",
        description="Register a cron schedule. cron_expr is a 5-field POSIX expression.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "cron_expr": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["name", "cron_expr"],
        },
        handler=_schedule_workflow,
        mutating=True,
    ),
    "abort_run": ToolSpec(
        name="abort_run",
        description="Request cooperative abort of a running workflow.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
        },
        handler=_abort_run,
        mutating=True,
    ),
    "device_tap": ToolSpec(
        name="device_tap",
        description=(
            "Tap at a specific pixel coordinate on the iPhone. Raw input — "
            "no confirmation, no vision. For testing/diagnostics."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        },
        handler=_device_tap,
        mutating=True,
    ),
    "device_tap_text": ToolSpec(
        name="device_tap_text",
        description="Find the visible label on screen via vision and tap it.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "prefer": {"type": "string", "enum": ["first", "last"]},
            },
            "required": ["text"],
        },
        handler=_device_tap_text,
        mutating=True,
    ),
    "device_swipe": ToolSpec(
        name="device_swipe",
        description="Swipe the iPhone in a direction (up/down/left/right).",
        input_schema={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                },
                "distance": {"type": "integer"},
            },
            "required": ["direction"],
        },
        handler=_device_swipe,
        mutating=True,
    ),
    "device_long_press": ToolSpec(
        name="device_long_press",
        description="Press and hold at a pixel coordinate for `duration` seconds.",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration": {"type": "number", "default": 1.0},
            },
            "required": ["x", "y"],
        },
        handler=_device_long_press,
        mutating=True,
    ),
    "device_type_text": ToolSpec(
        name="device_type_text",
        description="Type text into whatever field is currently focused on the iPhone.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_device_type_text,
        mutating=True,
    ),
    "device_press_key": ToolSpec(
        name="device_press_key",
        description="Press a hardware key (enter, escape, backspace, tab, etc.).",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "modifiers": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["key"],
        },
        handler=_device_press_key,
        mutating=True,
    ),
    "device_press_home": ToolSpec(
        name="device_press_home",
        description="Return to the iOS home screen (Cmd+1 via iPhone Mirroring).",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_device_press_home,
        mutating=True,
    ),
    "device_launch_app": ToolSpec(
        name="device_launch_app",
        description="Open an app by name via Spotlight.",
        input_schema={
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
        handler=_device_launch_app,
        mutating=True,
    ),
    "device_screenshot": ToolSpec(
        name="device_screenshot",
        description="Capture the current iPhone screen; returns a base64 JPEG.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_device_screenshot,
        mutating=False,
    ),
    "device_extract": ToolSpec(
        name="device_extract",
        description=(
            "Ask a visual-QA question about the current iPhone screen. "
            "Returns {answer, confidence}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "expected_type": {
                    "type": "string",
                    "enum": ["int", "float", "string", "bool"],
                    "default": "string",
                },
                "hint": {"type": "string"},
            },
            "required": ["question"],
        },
        handler=_device_extract,
        mutating=False,
    ),
    "device_reset": ToolSpec(
        name="device_reset",
        description=(
            "Drop the cached device controller. Use after Mirroring reconnects "
            "or if gestures stop registering."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_device_reset,
        mutating=True,
    ),
}


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


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
            return None
        if method == "tools/list":
            visible = [
                {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
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
        if name == "run_workflow" or name == "schedule_workflow":
            wf_name = args.get("name", "")
            if self._policy.is_workflow_blocked(wf_name):
                return _tool_error_reply(
                    request_id, f"workflow {wf_name!r} is blocked by policy"
                )
        try:
            out = tool.handler(args, self._client)
        except Exception as exc:
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
