"""
Engine helpers for the advanced step kinds.

Extracted from engine.py so no single file crosses the 500-line hard cap.
These three operations (extract, goal, failure handling) are all
engine-internal and share the same emit channel + RunContext.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pilot.workflow.schema import Step, WorkflowDef

if TYPE_CHECKING:
    from pilot.workflow.engine import RunContext, WorkflowEngine

log = logging.getLogger("pilotd.workflow.steps")


def run_extract(engine: "WorkflowEngine", step: Step, ctx: "RunContext") -> None:
    """Vision-based structured extraction — see engine docstring for YAML shape."""
    from pilot.workflow.engine import WorkflowFailed
    if engine._extractor is None:
        raise WorkflowFailed(
            "extract: step requires a VisionExtractor (check service wiring)"
        )
    var_name = step.primary
    question = engine._interp(step.value_for("question"), ctx)
    expected_type = str(step.value_for("type", "string"))
    hint = step.value_for("hint")
    if isinstance(hint, str):
        hint = engine._interp(hint, ctx)
    min_conf = float(step.value_for("min_confidence", 0.3))

    ss = engine._controller.screenshot()
    engine._emit({
        "event": "extract_ask",
        "variable": var_name,
        "question": question,
        "expected_type": expected_type,
    })
    value, confidence = engine._extractor.extract(
        question=question,
        screenshot=ss,
        expected_type=expected_type,
        hint=hint,
        task_id=f"extract:{ctx.run_id[:8]}",
    )
    ctx.variables[var_name] = value
    engine._emit({
        "event": "extract_answer",
        "variable": var_name,
        "value": value,
        "confidence": round(confidence, 3),
    })
    if value is None and confidence < min_conf:
        raise WorkflowFailed(
            f"extract: couldn't answer {question!r} with sufficient confidence "
            f"(got {confidence:.2f})"
        )


def run_goal(engine: "WorkflowEngine", step: Step, ctx: "RunContext") -> None:
    """Launch the goal-directed agent — see engine docstring for YAML shape."""
    from pilot.workflow.engine import WorkflowFailed
    from pilot.workflow.goal_agent import GoalAgent

    goal_text = engine._interp(step.primary, ctx)
    budget = int(step.value_for("budget", 15))
    capture_var = step.value_for("capture_as")
    vision = getattr(engine._controller, "_vision", None)
    if vision is None:
        raise WorkflowFailed("goal: controller is missing its vision agent")

    agent = GoalAgent(
        controller=engine._controller,
        vision=vision,
        emit=engine._emit,
    )
    result = agent.pursue(
        goal=goal_text, budget_steps=budget, capture_var=capture_var,
    )
    if capture_var and result.captured is not None:
        ctx.variables[capture_var] = result.captured
    if result.status != "success":
        raise WorkflowFailed(f"goal: {result.summary}")


def handle_step_failure(
    engine: "WorkflowEngine",
    defn: WorkflowDef,
    step: Step,
    idx: int,
    exc: Exception,
    ctx: "RunContext",
    replans_remaining: int,
) -> tuple[bool, list[Step], int]:
    """Step-level ``on_failure`` policy handler.

    Returns ``(handled, new_steps, remaining_budget)``. When ``handled`` is
    True, the caller should splice ``new_steps`` in place of the failed step
    and continue; otherwise, re-raise.
    """
    raw = step.value_for("on_failure")
    strategy: str = "abort"
    if isinstance(raw, str):
        strategy = raw
    elif isinstance(raw, dict):
        strategy = str(raw.get("strategy", "abort"))

    if strategy == "replan" and engine._replanner is not None and replans_remaining > 0:
        try:
            ss = engine._controller.screenshot()
        except Exception as cap_exc:
            log.warning("replan: could not capture screenshot: %s", cap_exc)
            return False, [], replans_remaining
        engine._emit({
            "event": "replan_start",
            "step": idx,
            "failed_kind": step.kind.value,
            "error": str(exc),
        })
        try:
            new_steps = engine._replanner.replan(
                defn=defn,
                failed_step=step,
                failed_idx=idx,
                error=str(exc),
                screenshot=ss,
                variables=dict(ctx.variables),
                task_id=f"replan:{ctx.run_id[:8]}",
            )
        except Exception as replan_exc:
            log.warning("replan failed: %s", replan_exc)
            engine._emit({
                "event": "replan_rejected",
                "step": idx,
                "error": str(replan_exc),
            })
            return False, [], replans_remaining
        engine._emit({
            "event": "replan_accepted",
            "step": idx,
            "new_steps": [s.kind.value for s in new_steps],
            "budget_remaining": replans_remaining - 1,
        })
        return True, new_steps, replans_remaining - 1

    if strategy == "continue":
        engine._emit({
            "event": "step_skipped",
            "step": idx,
            "error": str(exc),
        })
        return True, [], replans_remaining

    return False, [], replans_remaining


__all__ = ["handle_step_failure", "run_extract", "run_goal"]
