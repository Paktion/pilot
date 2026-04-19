"""MCP permission policy — fail-closed defaults + overrides."""

from __future__ import annotations

import json
from pathlib import Path

from pilot.mcp.permissions import PermissionPolicy, load_policy


def test_default_allow_only_read_only(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_permissions.json"
    policy = load_policy(cfg)
    # Read-only tools visible by default.
    for name in (
        "check_health",
        "list_workflows",
        "get_run_status",
        "get_run_events",
        "get_memory",
        "diagnose_failure",
        "draft_workflow",
    ):
        assert policy.is_tool_visible(name), f"expected {name} visible by default"
    # Mutating tools HIDDEN by default.
    for name in ("run_workflow", "save_workflow", "schedule_workflow", "abort_run"):
        assert not policy.is_tool_visible(name), f"expected {name} hidden by default"


def test_defaults_file_written_on_first_use(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_permissions.json"
    assert not cfg.exists()
    load_policy(cfg)
    assert cfg.exists()
    contents = json.loads(cfg.read_text())
    assert "run_workflow" not in contents["allow"]


def test_wildcard_allows_all(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_permissions.json"
    cfg.write_text(json.dumps({"allow": ["*"], "deny": [], "blockedWorkflows": []}))
    policy = load_policy(cfg)
    assert policy.is_tool_visible("run_workflow")
    assert policy.is_tool_visible("anything_goes")


def test_deny_overrides_allow(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_permissions.json"
    cfg.write_text(
        json.dumps({"allow": ["*"], "deny": ["run_workflow"], "blockedWorkflows": []})
    )
    policy = load_policy(cfg)
    assert not policy.is_tool_visible("run_workflow")


def test_blocked_workflows_case_insensitive() -> None:
    policy = PermissionPolicy(
        allow=frozenset(("list_workflows", "run_workflow")),
        deny=frozenset(),
        blocked_workflows=frozenset(("Pay Spectrum Bill",)),
    )
    assert policy.is_workflow_blocked("Pay Spectrum Bill")
    assert policy.is_workflow_blocked("pay spectrum bill")
    assert not policy.is_workflow_blocked("Reorder")


def test_malformed_config_falls_back_to_defaults(tmp_path: Path) -> None:
    cfg = tmp_path / "mcp_permissions.json"
    cfg.write_text("{ not valid json")
    policy = load_policy(cfg)
    # Falls back to defaults: run_workflow hidden.
    assert not policy.is_tool_visible("run_workflow")
    assert policy.is_tool_visible("list_workflows")
