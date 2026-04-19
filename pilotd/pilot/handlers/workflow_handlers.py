"""Workflow CRUD + execution RPCs."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Awaitable, Callable

from pilot import service
from pilot.workflow import RunContext, WorkflowDef, WorkflowEngine, parse_workflow_yaml

log = logging.getLogger("pilotd.handlers.workflow")

Emit = Callable[[dict[str, Any]], Awaitable[None]]


async def list_(_: dict[str, Any], emit: Emit) -> None:
    rows = service.container().memory().list_workflows()
    await emit({"event": "done", "status": "ok", "workflows": rows})


async def save(params: dict[str, Any], emit: Emit) -> None:
    yaml_text = params.get("yaml")
    if not yaml_text:
        await emit({"event": "error", "error": "missing 'yaml'"})
        return
    try:
        defn = parse_workflow_yaml(yaml_text)
    except ValueError as exc:
        await emit({"event": "error", "error": f"parse: {exc}"})
        return
    wf_id = service.container().save_workflow(
        name=defn.name,
        app=defn.app,
        yaml_text=yaml_text,
        id=params.get("id"),
    )
    await emit({"event": "done", "status": "ok", "id": wf_id, "name": defn.name})


async def delete(params: dict[str, Any], emit: Emit) -> None:
    wf_id = params.get("id")
    if not wf_id:
        await emit({"event": "error", "error": "missing 'id'"})
        return
    service.container().delete_workflow(wf_id)
    await emit({"event": "done", "status": "ok", "id": wf_id})


async def draft(params: dict[str, Any], emit: Emit) -> None:
    description = params.get("description")
    if not description:
        await emit({"event": "error", "error": "missing 'description'"})
        return
    try:
        yaml_text = service.container().planner().draft_workflow(description)
    except Exception as exc:
        log.exception("draft failed")
        await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    await emit({"event": "done", "status": "ok", "yaml": yaml_text})


async def run(params: dict[str, Any], emit: Emit) -> None:
    name = params.get("name")
    if not name:
        await emit({"event": "error", "error": "missing 'name'"})
        return
    defn = service.container().load_workflow(name)
    if defn is None:
        await emit({"event": "error", "error": f"workflow not found: {name}"})
        return

    mem = service.container().memory()
    row = mem.get_workflow_by_name(name)
    if row is None:
        await emit({"event": "error", "error": f"workflow row missing: {name}"})
        return
    run_id = mem.start_run(row["id"])
    await emit({"event": "started", "run_id": run_id, "workflow": name})

    # Execute in a worker thread so we can stream events back without
    # blocking the asyncio loop.
    threading.Thread(
        target=_execute_workflow,
        args=(run_id, row["id"], defn, params.get("params") or {}),
        daemon=True,
    ).start()

    await emit({"event": "done", "status": "running", "run_id": run_id})


async def approve_step(params: dict[str, Any], emit: Emit) -> None:
    # Approval hook is exposed for completeness; the workflow engine accepts
    # synchronous controls, so the approval dialog is handled client-side
    # (confirm_each_action toggle passed in params on workflow.run).
    await emit({"event": "done", "status": "ok", "decision": params.get("decision", "approve")})


def _execute_workflow(
    run_id: str,
    workflow_id: str,
    defn: WorkflowDef,
    params: dict[str, Any],
) -> None:
    """Thread worker: build a live agent stack, execute the workflow, persist outcome."""
    try:
        controller = _build_live_controller()
    except Exception as exc:
        log.exception("could not build agent controller")
        service.container().memory().finish_run(
            run_id,
            status="failed",
            summary=f"controller init failed: {type(exc).__name__}: {exc}",
        )
        return

    mem = service.container().memory()
    median_spectrum = _precompute_memory_snapshot(mem)

    def _remember(key: str, value: Any) -> None:
        mem.remember(
            workflow_id=workflow_id,
            run_id=run_id,
            kind="observation",
            key=key,
            value=value,
        )

    def _lookup(name: str) -> WorkflowDef | None:
        return service.container().load_workflow(name)

    ctx = RunContext(
        run_id=run_id,
        workflow_id=workflow_id,
        params=params,
        memory_snapshot=median_spectrum,
    )
    engine = WorkflowEngine(
        controller=controller,
        workflow_lookup=_lookup,
        remember=_remember,
    )

    result = engine.run(defn, ctx)
    summary = result.summary
    cost = _estimate_cost_usd()
    mem.finish_run(
        run_id,
        status=result.status,
        summary=summary,
        cost_usd=cost,
    )
    log.info("workflow %s → %s (%s)", defn.name, result.status, summary)


def _precompute_memory_snapshot(mem) -> dict[str, Any]:
    """Inject common computed memory values used in abort_if expressions."""
    snap: dict[str, Any] = {}
    values = mem.numeric_values(workflow_id=None, key="last_spectrum_bill", limit=6)
    if values:
        values_sorted = sorted(values)
        mid = len(values_sorted) // 2
        if len(values_sorted) % 2 == 0:
            snap["median_spectrum_last6"] = (
                values_sorted[mid - 1] + values_sorted[mid]
            ) / 2
        else:
            snap["median_spectrum_last6"] = values_sorted[mid]
    return snap


def _estimate_cost_usd() -> float:
    usage = service.container().usage()
    return usage.get_daily_cost()  # cheap proxy; replace with per-task cost when available


def _build_live_controller():
    """Construct the real agent-controller stack. Imports are deferred so test
    paths can avoid the native Quartz/pyobjc dependencies.
    """
    from pilot.core.controller import AgentController
    from pilot.core.input_simulator import InputSimulator
    from pilot.core.vision import VisionAgent
    from pilot.core.window_capture import MirroringWindowManager

    window = MirroringWindowManager()
    inputs = InputSimulator(window_manager=window)
    vision = VisionAgent(model=service.container().config().get("model"))
    return AgentController(vision=vision, inputs=inputs, window=window)


METHODS = {
    "list": list_,
    "save": save,
    "delete": delete,
    "draft": draft,
    "run": run,
    "approve_step": approve_step,
}
