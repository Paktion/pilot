"""
Env-var prompt loader.

All prompt text is loaded from environment variables at daemon startup — the
repo never contains prompt content. This keeps the authoring surface, planner
instructions, and agent system prompts out of any tracked file.

Conventions
-----------
* Keys are UPPER_SNAKE and prefixed ``PILOT_PROMPT_``.
* Missing keys raise ``PromptConfigError`` at startup — fail-loud, not silent.
* A companion ``.env.example`` in the repo root documents the required keys
  with placeholder values. The real ``.env`` is gitignored.

Usage
-----
    from pilot import prompts
    prompts.load_env()             # call once at daemon boot
    prompts.require_all()          # assert every required key is present
    sys_prompt = prompts.get("AGENT_SYSTEM")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

try:
    from dotenv import load_dotenv as _dotenv_load
except ImportError:  # dotenv is optional at runtime; launchd sets env directly
    _dotenv_load = None

_PREFIX = "PILOT_PROMPT_"

# Every prompt name the daemon depends on. Add to this list whenever a new
# prompt is introduced in code — loader will enforce presence at boot.
REQUIRED: tuple[str, ...] = (
    "DRAFT_WORKFLOW",
    "CRON_PARSE",
    "DIAGNOSE_FAILURE",
    "AGENT_SYSTEM",
    "TASK_PLANNER",
    "SAFETY_GUARD",
    "EXTRACT_ANSWER",
    "GOAL_AGENT",
    "REPLAN",
    "SUCCESS_CRITERIA",
)


class PromptConfigError(RuntimeError):
    """Raised when a required prompt env var is missing or empty."""


def load_env(dotenv_path: str | Path | None = None) -> None:
    """
    Populate ``os.environ`` from a .env file if present.

    Lookup order:
        1. Explicit ``dotenv_path`` argument.
        2. ``$PILOT_HOME/.env`` (runtime install location).
        3. ``<repo-root>/.env`` walked up from this file.

    Safe to call multiple times. Never overwrites existing process env.
    """
    if _dotenv_load is None:
        return

    candidates: list[Path] = []
    if dotenv_path is not None:
        candidates.append(Path(dotenv_path).expanduser())

    pilot_home = os.environ.get("PILOT_HOME")
    if pilot_home:
        candidates.append(Path(pilot_home).expanduser() / ".env")

    # Walk up from this file looking for a repo-root .env.
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidates.append(parent / ".env")

    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve() if path.exists() else path
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            _dotenv_load(dotenv_path=path, override=False)


def get(name: str) -> str:
    """Return the prompt text for ``name`` (without the ``PILOT_PROMPT_`` prefix)."""
    key = name if name.startswith(_PREFIX) else _PREFIX + name
    value = os.environ.get(key, "").strip()
    if not value:
        raise PromptConfigError(
            f"Prompt env var {key!r} is missing or empty. "
            "Copy .env.example to .env in the repo root and populate it, "
            "or set the variable in your launchd plist."
        )
    return value


def require_all(names: Iterable[str] = REQUIRED) -> None:
    """Assert every prompt in ``names`` resolves to non-empty text."""
    missing: list[str] = []
    for n in names:
        key = n if n.startswith(_PREFIX) else _PREFIX + n
        if not os.environ.get(key, "").strip():
            missing.append(key)
    if missing:
        raise PromptConfigError(
            "Missing required prompt env vars: "
            + ", ".join(sorted(missing))
            + ". See .env.example."
        )


def snapshot() -> dict[str, int]:
    """Return {prompt_name: length} — safe to log without leaking content."""
    out: dict[str, int] = {}
    for n in REQUIRED:
        key = _PREFIX + n
        out[n] = len(os.environ.get(key, ""))
    return out
