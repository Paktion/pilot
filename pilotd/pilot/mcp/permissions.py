"""
Fail-closed permission policy for the Pilot MCP server.

Config file: ``$PILOT_HOME/mcp_permissions.json``

Schema
------
    {
      "allow": ["list_workflows", "get_run_status", "get_memory"],
      "deny":  [],
      "blockedWorkflows": []
    }

Defaults are read-only. ``run_workflow`` is hidden until the user explicitly
adds it to ``allow`` in the config file — the MCP client literally does not
see a tool it is not allowed to call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pilot.core import paths

log = logging.getLogger("pilotd.mcp.permissions")

_DEFAULT_ALLOW: tuple[str, ...] = (
    "list_workflows",
    "get_run_status",
    "get_memory",
)


@dataclass(frozen=True)
class PermissionPolicy:
    allow: frozenset[str] = field(default_factory=lambda: frozenset(_DEFAULT_ALLOW))
    deny: frozenset[str] = field(default_factory=frozenset)
    blocked_workflows: frozenset[str] = field(default_factory=frozenset)

    def is_tool_visible(self, tool_name: str) -> bool:
        if tool_name in self.deny:
            return False
        return "*" in self.allow or tool_name in self.allow

    def is_workflow_blocked(self, name: str) -> bool:
        name_lc = name.lower()
        return any(b.lower() == name_lc for b in self.blocked_workflows)


def load_policy(path: Path | None = None) -> PermissionPolicy:
    """Read the policy file. Missing or invalid files yield fail-closed defaults."""
    cfg_path = path or paths.mcp_permissions_path()
    if not cfg_path.exists():
        _ensure_defaults_file(cfg_path)
        return PermissionPolicy()
    try:
        raw = json.loads(cfg_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("permissions file unreadable (%s) — falling back to defaults", exc)
        return PermissionPolicy()
    return PermissionPolicy(
        allow=frozenset(str(s) for s in raw.get("allow") or _DEFAULT_ALLOW),
        deny=frozenset(str(s) for s in raw.get("deny") or ()),
        blocked_workflows=frozenset(str(s) for s in raw.get("blockedWorkflows") or ()),
    )


def _ensure_defaults_file(path: Path) -> None:
    """Seed a read-only defaults file on first use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "allow": list(_DEFAULT_ALLOW),
                "deny": [],
                "blockedWorkflows": [],
            },
            indent=2,
        )
        + "\n"
    )
    log.info("wrote default MCP permissions to %s", path)


__all__ = ["PermissionPolicy", "load_policy"]
