"""Workflow YAML schema + parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class StepKind(str, Enum):
    LAUNCH = "launch"
    WAIT_FOR = "wait_for"
    TAP = "tap"
    TAP_NEAR = "tap_near"
    TAP_XY = "tap_xy"
    SWIPE = "swipe"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    READ_AS = "read_as"
    EXTRACT = "extract"
    REMEMBER = "remember"
    ABORT_IF = "abort_if"
    SCREENSHOT = "screenshot"
    DONE = "done"
    GOAL = "goal"


_VALID_KINDS = {k.value for k in StepKind}


class WorkflowParseError(ValueError):
    """Raised when a .skill.yaml file doesn't match the schema."""


@dataclass
class Step:
    kind: StepKind
    # Raw payload as it appeared in YAML. Different kinds read different fields
    # (tap: text; tap_xy: x+y; read_as: pattern; abort_if: expr; etc.).
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def primary(self) -> str | None:
        """The primary string value for single-shorthand steps (tap, launch, etc.)."""
        return self.data.get("_primary")

    def value_for(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class WorkflowDef:
    version: int
    name: str
    app: str | None
    description: str
    tags: list[str]
    params: dict[str, dict[str, Any]]
    steps: list[Step]
    on_success: dict[str, Any] | None

    @property
    def slug(self) -> str:
        return (self.name or "").lower().replace(" ", "_").replace("/", "_")


def parse_workflow_yaml(yaml_text: str) -> WorkflowDef:
    """Parse a ``.skill.yaml`` string into a ``WorkflowDef``.

    Raises ``WorkflowParseError`` on shape violations. Extra keys are ignored.
    """
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise WorkflowParseError(f"invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise WorkflowParseError("top-level must be a mapping")

    if "name" not in raw or not isinstance(raw["name"], str):
        raise WorkflowParseError("'name' (string) is required")

    steps_raw = raw.get("steps") or []
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WorkflowParseError("'steps' must be a non-empty list")

    steps = [_parse_step(s, idx) for idx, s in enumerate(steps_raw)]

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise WorkflowParseError("'params' must be a mapping")

    on_success = raw.get("on_success")
    if on_success is not None:
        if not isinstance(on_success, dict) or "run" not in on_success:
            raise WorkflowParseError("'on_success' must be a mapping with 'run'")

    return WorkflowDef(
        version=int(raw.get("version", 1)),
        name=str(raw["name"]),
        app=raw.get("app"),
        description=str(raw.get("description", "")),
        tags=list(raw.get("tags") or []),
        params=params,
        steps=steps,
        on_success=on_success,
    )


def _parse_step(raw: Any, idx: int) -> Step:
    if not isinstance(raw, dict):
        raise WorkflowParseError(f"step {idx}: must be a mapping, got {type(raw).__name__}")

    known_keys = set(raw) & _VALID_KINDS
    if len(known_keys) != 1:
        raise WorkflowParseError(
            f"step {idx}: exactly one of {_VALID_KINDS} must be set (got {sorted(raw)})"
        )
    kind_str = known_keys.pop()
    kind = StepKind(kind_str)

    primary = raw[kind_str]
    data: dict[str, Any] = {k: v for k, v in raw.items() if k != kind_str}

    # For shorthand forms like ``tap: "Checkout"``, stash the string under
    # ``_primary`` so the engine can grab it without caring about the key name.
    if isinstance(primary, str):
        data["_primary"] = primary
    elif isinstance(primary, dict):
        # e.g. ``remember: {key, value}`` or ``drag: {from, to}``
        data.update(primary)
    else:
        data["_primary"] = primary

    _validate_step(kind, data, idx)
    return Step(kind=kind, data=data)


def _validate_step(kind: StepKind, data: dict[str, Any], idx: int) -> None:
    if kind in (StepKind.TAP, StepKind.WAIT_FOR, StepKind.LAUNCH, StepKind.PRESS_KEY):
        if not data.get("_primary"):
            raise WorkflowParseError(f"step {idx} ({kind.value}): needs a string value")
    if kind is StepKind.TAP_XY:
        if "x" not in data or "y" not in data:
            raise WorkflowParseError(f"step {idx} (tap_xy): needs 'x' and 'y'")
    if kind is StepKind.READ_AS:
        if "pattern" not in data:
            raise WorkflowParseError(f"step {idx} (read_as): needs 'pattern'")
    if kind is StepKind.EXTRACT:
        if not data.get("_primary"):
            raise WorkflowParseError(f"step {idx} (extract): needs a variable name")
        if not data.get("question"):
            raise WorkflowParseError(f"step {idx} (extract): needs 'question'")
    if kind is StepKind.GOAL:
        if not data.get("_primary"):
            raise WorkflowParseError(f"step {idx} (goal): needs a goal description")
    if kind is StepKind.REMEMBER:
        if "key" not in data or "value" not in data:
            raise WorkflowParseError(f"step {idx} (remember): needs 'key' and 'value'")
    if kind is StepKind.ABORT_IF and not data.get("_primary"):
        raise WorkflowParseError(f"step {idx} (abort_if): needs an expression string")
    if kind is StepKind.SWIPE and "direction" not in data:
        raise WorkflowParseError(f"step {idx} (swipe): needs 'direction'")
    if kind is StepKind.TYPE_TEXT and not data.get("_primary") and "text" not in data:
        raise WorkflowParseError(f"step {idx} (type_text): needs a text value")
