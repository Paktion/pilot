"""
Workflow engine — YAML-authored automation flows with abort_if + on_success.

Shape (per private spec):

    version: 1
    name: ...
    app: ...
    params: { key: {type, default} }
    steps:
      - launch: Grubhub
      - wait_for: "Reorder"
      - tap: "Reorder"
      - read_as: bill, pattern: "\\$([0-9.]+)"
      - abort_if: "{{ bill | float > 20.0 }}"
      - remember: {key, value}
      - screenshot: label
      - done: "summary"
    on_success:
      run: other_workflow_name
      params: { ... }
"""

from pilot.workflow.schema import (
    Step,
    StepKind,
    WorkflowDef,
    WorkflowParseError,
    parse_workflow_yaml,
)
from pilot.workflow.expr import ExprError, TemplateEngine
from pilot.workflow.engine import RunContext, WorkflowEngine, WorkflowResult

__all__ = [
    "ExprError",
    "RunContext",
    "Step",
    "StepKind",
    "TemplateEngine",
    "WorkflowDef",
    "WorkflowEngine",
    "WorkflowParseError",
    "WorkflowResult",
    "parse_workflow_yaml",
]
