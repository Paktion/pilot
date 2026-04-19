"""Workflow engine — executes against a mock controller."""

from __future__ import annotations

import pytest

from pilot.workflow import RunContext, WorkflowEngine, parse_workflow_yaml


def _canonical(text):
    """Collapse engine's list-form keywords back to a single string for asserts."""
    if isinstance(text, list):
        return text[0] if text else ""
    return text


class MockController:
    def __init__(self, read_regex_values: dict[str, str] | None = None) -> None:
        self.actions: list[tuple[str, tuple]] = []
        self.read_values = read_regex_values or {}

    def launch(self, app: str) -> None:
        self.actions.append(("launch", (app,)))

    def wait_for(self, text, timeout_s: float = 20.0, max_scrolls: int = 4) -> bool:
        self.actions.append(("wait_for", (_canonical(text), timeout_s)))
        return True

    def tap_text(self, text, prefer: str | None = None, max_scrolls: int = 2) -> None:
        self.actions.append(("tap_text", (_canonical(text), prefer)))

    def tap_xy(self, x: int, y: int) -> None:
        self.actions.append(("tap_xy", (x, y)))

    def swipe(self, direction: str, distance: int | None = None) -> None:
        self.actions.append(("swipe", (direction, distance)))

    def type_text(self, text: str) -> None:
        self.actions.append(("type_text", (text,)))

    def press_key(self, key: str, modifiers: list[str] | None = None) -> None:
        self.actions.append(("press_key", (key, modifiers)))

    def screenshot_label(self, label: str) -> None:
        self.actions.append(("screenshot_label", (label,)))

    def read_regex(self, pattern: str) -> str | None:
        return self.read_values.get(pattern)


def _engine(ctrl: MockController, **kw) -> WorkflowEngine:
    remembered: list[tuple[str, object]] = []

    def _remember(k: str, v: object) -> None:
        remembered.append((k, v))

    engine = WorkflowEngine(controller=ctrl, remember=_remember, **kw)
    engine.remembered = remembered  # type: ignore[attr-defined]
    return engine


def test_happy_path() -> None:
    ctrl = MockController()
    engine = _engine(ctrl)
    defn = parse_workflow_yaml(
        """
name: Test
steps:
  - launch: Safari
  - wait_for: "Search"
  - tap: "Search"
  - type_text: "pilot"
  - press_key: "enter"
  - screenshot: done
"""
    )
    result = engine.run(
        defn,
        RunContext(run_id="r1", workflow_id="w1"),
    )
    assert result.status == "success"
    assert [a[0] for a in ctrl.actions] == [
        "launch", "wait_for", "tap_text", "type_text", "press_key", "screenshot_label",
    ]


def test_abort_if_aborts() -> None:
    ctrl = MockController(read_regex_values={"Total \\$([0-9.]+)": "50.00"})
    engine = _engine(ctrl)
    defn = parse_workflow_yaml(
        """
name: Abort
steps:
  - launch: App
  - read_as: bill
    pattern: "Total \\\\$([0-9.]+)"
  - abort_if: "{{ bill | float > 30 }}"
  - tap: "Pay"
"""
    )
    result = engine.run(defn, RunContext(run_id="r2", workflow_id="w2"))
    assert result.status == "aborted"
    actions = [a[0] for a in ctrl.actions]
    assert "launch" in actions
    assert "tap_text" not in actions  # never reached


def test_remember_persisted() -> None:
    ctrl = MockController(read_regex_values={"([0-9]+)": "5"})
    engine = _engine(ctrl)
    defn = parse_workflow_yaml(
        """
name: Remember
steps:
  - launch: App
  - read_as: count
    pattern: "([0-9]+)"
  - remember:
      key: swipes
      value: "{{ count }}"
"""
    )
    result = engine.run(defn, RunContext(run_id="r3", workflow_id="w3"))
    assert result.status == "success"
    assert ("swipes", 5) in engine.remembered  # type: ignore[attr-defined]


def test_params_and_templating() -> None:
    ctrl = MockController()
    engine = _engine(ctrl)
    defn = parse_workflow_yaml(
        """
name: Params
params:
  target:
    type: string
    default: "Home"
steps:
  - tap: "{{ target }}"
"""
    )
    result = engine.run(defn, RunContext(run_id="r4", workflow_id="w4", params={"target": "Custom"}))
    assert result.status == "success"
    assert ctrl.actions[0] == ("tap_text", ("Custom", None))


def test_missing_param_fails() -> None:
    ctrl = MockController()
    engine = _engine(ctrl)
    defn = parse_workflow_yaml(
        """
name: P
params:
  target:
    type: string
steps:
  - launch: X
"""
    )
    result = engine.run(defn, RunContext(run_id="r5", workflow_id="w5", params={}))
    assert result.status == "failed"
    assert "missing required param" in result.summary


def test_on_success_chains() -> None:
    ctrl = MockController()
    engine = _engine(
        MockController(),
        workflow_lookup=lambda name: parse_workflow_yaml(
            f"name: {name}\nsteps:\n  - launch: Chained\n"
        ) if name == "child" else None,
    )
    defn = parse_workflow_yaml(
        """
name: parent
steps:
  - launch: Parent
on_success:
  run: child
"""
    )
    result = engine.run(defn, RunContext(run_id="r6", workflow_id="w6"))
    assert result.status == "success"
    assert len(result.chained_run_ids) == 1


def test_wait_for_timeout_fails() -> None:
    class TimeoutController(MockController):
        def wait_for(self, text: str, timeout_s: float = 15.0) -> bool:
            self.actions.append(("wait_for", (text, timeout_s)))
            return False

    engine = _engine(TimeoutController())
    defn = parse_workflow_yaml(
        """
name: Timeout
steps:
  - wait_for: "Never"
"""
    )
    result = engine.run(defn, RunContext(run_id="r7", workflow_id="w7"))
    assert result.status == "failed"
    assert "wait_for" in result.summary


def test_done_step_sets_summary() -> None:
    ctrl = MockController()
    engine = _engine(ctrl)
    defn = parse_workflow_yaml(
        """
name: Done
steps:
  - launch: X
  - done: "all set"
"""
    )
    result = engine.run(defn, RunContext(run_id="r8", workflow_id="w8"))
    assert result.status == "success"
    assert result.summary == "all set"
