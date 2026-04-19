"""
Synchronous workflow runner used by the scheduler.

Kept as a separate module so `handlers/schedule_handlers.py` can import it
without pulling in the async event loop plumbing. The scheduler's
``ThreadPoolExecutor`` ultimately calls this function in a worker thread.
"""

from __future__ import annotations

import logging
from typing import Any

from pilot import service
from pilot.workflow import RunContext, WorkflowEngine

log = logging.getLogger("pilotd.scheduler.run")


def run_workflow_sync(workflow_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Load → execute → record outcome. Used by the scheduler thread-pool."""
    defn = service.container().load_workflow(workflow_name)
    if defn is None:
        log.warning("scheduled run: unknown workflow %r", workflow_name)
        return {"status": "failed", "summary": f"unknown workflow: {workflow_name}"}

    mem = service.container().memory()
    row = mem.get_workflow_by_name(workflow_name)
    assert row is not None
    run_id = mem.start_run(row["id"])

    try:
        controller = _build_live_controller()
    except Exception as exc:
        log.exception("could not build agent controller")
        mem.finish_run(
            run_id,
            status="failed",
            summary=f"controller init failed: {type(exc).__name__}: {exc}",
        )
        return {"status": "failed", "summary": str(exc), "run_id": run_id}

    def _remember(key: str, value: Any) -> None:
        mem.remember(
            workflow_id=row["id"],
            run_id=run_id,
            kind="observation",
            key=key,
            value=value,
        )

    ctx = RunContext(
        run_id=run_id,
        workflow_id=row["id"],
        params=params,
    )
    engine = WorkflowEngine(
        controller=controller,
        workflow_lookup=service.container().load_workflow,
        remember=_remember,
    )

    result = engine.run(defn, ctx)
    mem.finish_run(
        run_id,
        status=result.status,
        summary=result.summary,
    )
    log.info("scheduled run %s → %s", workflow_name, result.status)
    return {"status": result.status, "summary": result.summary, "run_id": run_id}


def _build_live_controller():
    from pilot.core.controller import AgentController
    from pilot.core.input_simulator import InputSimulator
    from pilot.core.vision import VisionAgent
    from pilot.core.window_capture import MirroringWindowManager

    window = MirroringWindowManager()
    inputs = InputSimulator(window_manager=window)
    vision = VisionAgent(model=service.container().config().get("model"))
    return AgentController(vision=vision, inputs=inputs, window=window)
