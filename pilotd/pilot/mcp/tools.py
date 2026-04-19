"""
MCP tool registry (scaffold).

Actual wire-up to the MCP Python SDK happens in M8. The shape of each tool
is fixed here so callers can reference it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    read_only: bool


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="list_workflows",
        description="Return the array of saved workflows (name, app, tags, last_run).",
        read_only=True,
    ),
    Tool(
        name="run_workflow",
        description="Trigger a workflow by name. Returns run_id.",
        read_only=False,
    ),
    Tool(
        name="get_run_status",
        description="Fetch status + summary + cost for a run_id.",
        read_only=True,
    ),
    Tool(
        name="get_memory",
        description="Vector top-k over memory scoped to a workflow.",
        read_only=True,
    ),
)
