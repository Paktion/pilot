"""
Shared runtime path resolver.

Every core module that needs to read or write state off disk routes through
``pilot_home()`` so the location is controlled by a single env var. No
module should hard-code ``~/Library/Application Support/Pilot/`` directly.

Env overrides:
    PILOT_HOME       — base directory (default ``~/Library/Application Support/Pilot``)
    PILOT_SOCKET     — daemon socket path (default ``<PILOT_HOME>/pilotd.sock``)
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_HOME = "~/Library/Application Support/Pilot"


def pilot_home() -> Path:
    """Return the Pilot runtime directory, creating it with 0700 if missing.

    Restricting the directory to the owner prevents other local users from
    reading .env, memory.db, or connecting to the daemon's Unix socket on
    a shared Mac.
    """
    root = Path(os.environ.get("PILOT_HOME", _DEFAULT_HOME)).expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        if (root.stat().st_mode & 0o777) != 0o700:
            root.chmod(0o700)
    except OSError:
        pass
    return root


def db_path() -> Path:
    return pilot_home() / "memory.db"


def socket_path() -> Path:
    override = os.environ.get("PILOT_SOCKET")
    if override:
        return Path(override).expanduser()
    return pilot_home() / "pilotd.sock"


def sessions_dir() -> Path:
    d = pilot_home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def workflows_dir() -> Path:
    d = pilot_home() / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    return d


def prompts_dir() -> Path:
    d = pilot_home() / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def screenshots_dir() -> Path:
    d = pilot_home() / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def mcp_permissions_path() -> Path:
    return pilot_home() / "mcp_permissions.json"


def config_path() -> Path:
    return pilot_home() / "config.json"


def usage_path() -> Path:
    return pilot_home() / "usage.json"


def compiled_skill_path(source_yaml: str | Path) -> Path:
    p = Path(source_yaml)
    return p.with_suffix("").with_suffix(".compiled.json")
