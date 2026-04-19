"""Workflow YAML parser — schema validation + step shapes."""

from __future__ import annotations

import pytest

from pilot.workflow import StepKind, WorkflowParseError, parse_workflow_yaml


REORDER_YAML = """
version: 1
name: Reorder
app: Grubhub
tags: [food]
description: demo
params:
  tip_percent:
    type: int
    default: 20
steps:
  - launch: Grubhub
  - wait_for: "Reorder"
  - tap: "Reorder"
  - tap_near: "Chipotle"
    prefer: first
  - read_as: bill
    pattern: "Total \\\\$([0-9.]+)"
  - abort_if: "{{ bill | float > 30 }}"
  - remember:
      key: last_total
      value: "{{ bill }}"
  - screenshot: confirm
on_success:
  run: another_workflow
  params: { tip_percent: 22 }
"""


def test_parse_valid() -> None:
    defn = parse_workflow_yaml(REORDER_YAML)
    assert defn.name == "Reorder"
    assert defn.app == "Grubhub"
    assert defn.tags == ["food"]
    assert defn.params["tip_percent"]["default"] == 20
    assert defn.on_success["run"] == "another_workflow"
    assert len(defn.steps) == 8
    kinds = [s.kind for s in defn.steps]
    assert StepKind.LAUNCH in kinds
    assert StepKind.ABORT_IF in kinds
    assert StepKind.REMEMBER in kinds
    assert StepKind.READ_AS in kinds


def test_slug() -> None:
    defn = parse_workflow_yaml(REORDER_YAML)
    assert defn.slug == "reorder"


def test_missing_name_raises() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml("steps:\n  - launch: X\n")


def test_empty_steps_raises() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml("name: X\nsteps: []\n")


def test_unknown_step_key_raises() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml(
            "name: X\nsteps:\n  - yodel: loud\n"
        )


def test_two_primary_keys_raises() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml(
            "name: X\nsteps:\n  - launch: A\n    tap: B\n"
        )


def test_tap_xy_requires_coords() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml("name: X\nsteps:\n  - tap_xy: 'foo'\n")


def test_read_as_requires_pattern() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml("name: X\nsteps:\n  - read_as: bill\n")


def test_remember_requires_key_and_value() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml(
            "name: X\nsteps:\n  - remember:\n      only_key: yes\n"
        )


def test_on_success_requires_run() -> None:
    with pytest.raises(WorkflowParseError):
        parse_workflow_yaml(
            "name: X\nsteps:\n  - launch: A\non_success:\n  notrun: X\n"
        )
