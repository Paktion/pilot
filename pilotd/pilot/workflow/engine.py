"""
Workflow execution engine.

Receives a ``WorkflowDef`` + ``RunContext`` and drives the agent through each
step, supporting:

* Jinja-lite ``{{ var }}`` templating on all string fields
* ``abort_if`` predicates that abort cleanly with status ``aborted``
* ``read_as`` step that runs OCR/regex over the current screenshot
* ``remember`` step that writes to the memory store
* ``screenshot`` step that tags the session recording
* top-level ``on_success: run: <other_workflow>`` chaining (single-level)

The engine is agent-agnostic: it calls a small set of "controls"
(``tap_text``, ``tap_xy``, ``swipe``, ``type_text``, ``launch``,
``wait_for``, ``screenshot`` and ``read_regex``) on an injectable controller
object. This keeps the engine testable without a live iPhone.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from pilot.workflow.expr import ExprError, TemplateEngine
from pilot.workflow.schema import Step, StepKind, WorkflowDef

log = logging.getLogger("pilotd.workflow")


class WorkflowAborted(RuntimeError):
    """Raised by ``abort_if`` to short-circuit the run cleanly."""


class WorkflowFailed(RuntimeError):
    """Raised by control adapters when a step can't execute."""


class Controller(Protocol):
    """Minimum surface the engine needs from a live agent adapter."""

    def launch(self, app: str) -> None: ...
    def wait_for(self, text: str, timeout_s: float = 15.0) -> bool: ...
    def tap_text(self, text: str, prefer: str | None = None) -> None: ...
    def tap_xy(self, x: int, y: int) -> None: ...
    def swipe(self, direction: str, distance: int | None = None) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press_key(self, key: str, modifiers: list[str] | None = None) -> None: ...
    def screenshot_label(self, label: str) -> None: ...
    def read_regex(self, pattern: str) -> str | None: ...


class EventEmitter(Protocol):
    def __call__(self, event: dict[str, Any]) -> None: ...


@dataclass
class RunContext:
    """State that flows through a single workflow run."""

    run_id: str
    workflow_id: str
    params: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)

    def templating_vars(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self.params)
        merged.update(self.variables)
        merged["memory"] = self.memory_snapshot
        return merged


@dataclass
class WorkflowResult:
    run_id: str
    status: str  # 'success' | 'failed' | 'aborted' | 'skipped'
    summary: str
    extracted: dict[str, Any] = field(default_factory=dict)
    chained_run_ids: list[str] = field(default_factory=list)


class WorkflowEngine:
    """YAML workflow runtime."""

    def __init__(
        self,
        controller: Controller,
        *,
        workflow_lookup: Callable[[str], WorkflowDef | None] | None = None,
        memory_lookup: Callable[[str, str], Any] | None = None,
        remember: Callable[[str, Any], None] | None = None,
        emit: EventEmitter | None = None,
    ) -> None:
        self._controller = controller
        self._workflow_lookup = workflow_lookup
        self._memory_lookup = memory_lookup
        self._remember = remember
        self._emit = emit or (lambda event: None)
        self._tmpl = TemplateEngine()

    def run(self, defn: WorkflowDef, ctx: RunContext) -> WorkflowResult:
        """Execute a workflow. Returns a ``WorkflowResult``."""
        self._emit({"event": "started", "run_id": ctx.run_id, "workflow": defn.name})
        try:
            ctx.params = self._resolve_params(defn, ctx.params)
            for idx, step in enumerate(defn.steps):
                self._emit({
                    "event": "step",
                    "step": idx,
                    "kind": step.kind.value,
                    "run_id": ctx.run_id,
                })
                self._run_step(step, ctx)
        except WorkflowAborted as exc:
            return WorkflowResult(
                run_id=ctx.run_id,
                status="aborted",
                summary=str(exc),
                extracted=dict(ctx.variables),
            )
        except WorkflowFailed as exc:
            return WorkflowResult(
                run_id=ctx.run_id,
                status="failed",
                summary=str(exc),
                extracted=dict(ctx.variables),
            )
        except Exception as exc:
            log.exception("workflow %s crashed", defn.name)
            return WorkflowResult(
                run_id=ctx.run_id,
                status="failed",
                summary=f"{type(exc).__name__}: {exc}",
                extracted=dict(ctx.variables),
            )

        summary = self._build_summary(defn, ctx)
        chained: list[str] = []
        if defn.on_success and self._workflow_lookup:
            chained = self._chain_on_success(defn, ctx)
        return WorkflowResult(
            run_id=ctx.run_id,
            status="success",
            summary=summary,
            extracted=dict(ctx.variables),
            chained_run_ids=chained,
        )

    def _resolve_params(
        self, defn: WorkflowDef, supplied: dict[str, Any]
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, spec in defn.params.items():
            if key in supplied:
                resolved[key] = supplied[key]
            elif "default" in spec:
                resolved[key] = spec["default"]
            else:
                raise WorkflowFailed(f"missing required param: {key}")
        # Also carry over supplied params that aren't declared (user provided
        # extras).
        for key, value in supplied.items():
            resolved.setdefault(key, value)
        return resolved

    def _interp(self, value: Any, ctx: RunContext) -> Any:
        if not isinstance(value, str):
            return value
        if "{{" not in value:
            return value
        return self._tmpl.render(value, ctx.templating_vars())

    def _run_step(self, step: Step, ctx: RunContext) -> None:
        kind = step.kind
        if kind is StepKind.LAUNCH:
            app = self._interp(step.primary, ctx)
            self._controller.launch(app)
        elif kind is StepKind.WAIT_FOR:
            text = self._interp(step.primary, ctx)
            if not self._controller.wait_for(text):
                raise WorkflowFailed(f"wait_for timed out: {text!r}")
        elif kind is StepKind.TAP:
            text = self._interp(step.primary, ctx)
            self._controller.tap_text(text, prefer=step.value_for("prefer"))
        elif kind is StepKind.TAP_NEAR:
            text = self._interp(step.primary, ctx)
            self._controller.tap_text(text, prefer=step.value_for("prefer", "first"))
        elif kind is StepKind.TAP_XY:
            x = int(self._interp(step.value_for("x"), ctx))
            y = int(self._interp(step.value_for("y"), ctx))
            self._controller.tap_xy(x, y)
        elif kind is StepKind.SWIPE:
            direction = self._interp(step.value_for("direction"), ctx)
            self._controller.swipe(direction, step.value_for("distance"))
        elif kind is StepKind.TYPE_TEXT:
            text = self._interp(step.primary or step.value_for("text"), ctx)
            self._controller.type_text(text)
        elif kind is StepKind.PRESS_KEY:
            key = self._interp(step.primary, ctx)
            self._controller.press_key(key, step.value_for("modifiers"))
        elif kind is StepKind.READ_AS:
            var_name = step.primary
            pattern = self._interp(step.value_for("pattern"), ctx)
            value = self._controller.read_regex(pattern)
            if value is None:
                raise WorkflowFailed(f"read_as: pattern {pattern!r} not found on screen")
            ctx.variables[var_name] = value
        elif kind is StepKind.REMEMBER:
            key = self._interp(step.value_for("key"), ctx)
            raw_val = self._interp(step.value_for("value"), ctx)
            try:
                val = _coerce_number(raw_val)
            except ValueError:
                val = raw_val
            if self._remember:
                self._remember(key, val)
            ctx.memory_snapshot[key] = val
        elif kind is StepKind.ABORT_IF:
            try:
                triggered = self._tmpl.evaluate_predicate(
                    step.primary, ctx.templating_vars()
                )
            except ExprError as exc:
                raise WorkflowFailed(f"abort_if failed to evaluate: {exc}")
            if triggered:
                raise WorkflowAborted(f"abort_if triggered: {step.primary}")
        elif kind is StepKind.SCREENSHOT:
            label = self._interp(step.primary or step.value_for("label", "step"), ctx)
            self._controller.screenshot_label(label)
        elif kind is StepKind.DONE:
            ctx.variables["_done_summary"] = self._interp(step.primary or "", ctx)
        else:  # pragma: no cover — enum exhaustiveness
            raise WorkflowFailed(f"unhandled step kind: {kind}")

        time.sleep(0.05)  # tiny pacing so the phone UI can catch up

    def _build_summary(self, defn: WorkflowDef, ctx: RunContext) -> str:
        explicit = ctx.variables.get("_done_summary")
        if explicit:
            return str(explicit)
        if ctx.variables:
            kvs = ", ".join(
                f"{k}={v}" for k, v in ctx.variables.items() if not k.startswith("_")
            )
            return f"{defn.name}: {kvs}"
        return f"{defn.name}: {len(defn.steps)} steps completed"

    def _chain_on_success(self, defn: WorkflowDef, ctx: RunContext) -> list[str]:
        assert defn.on_success is not None
        assert self._workflow_lookup is not None
        target_name = defn.on_success["run"]
        target = self._workflow_lookup(target_name)
        if not target:
            log.warning("on_success target %r not found", target_name)
            return []
        params = defn.on_success.get("params") or {}
        interp_params = {
            k: self._interp(v, ctx) for k, v in params.items()
        }
        sub_ctx = RunContext(
            run_id=str(uuid.uuid4()),
            workflow_id="",  # caller fills in
            params=interp_params,
        )
        result = self.run(target, sub_ctx)
        self._emit({
            "event": "chain",
            "parent_run_id": ctx.run_id,
            "child_run_id": result.run_id,
            "status": result.status,
        })
        return [result.run_id]


def _coerce_number(raw: Any) -> float | int:
    if isinstance(raw, (int, float)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if re.match(r"^-?\d+$", s):
            return int(s)
        if re.match(r"^-?\d+\.\d+$", s):
            return float(s)
    raise ValueError(f"not numeric: {raw!r}")
