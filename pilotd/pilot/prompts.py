"""
Prompt loader: file-first, env-var fallback.

All prompt bodies live in ``$PILOT_HOME/prompts/<name>.md`` where ``<name>``
is the prompt key in lowercase (e.g. ``draft_workflow.md``). Each file is
the raw prompt text — no frontmatter, no markdown stripping. The loader
falls back to ``PILOT_PROMPT_<NAME>`` env vars so existing .env setups
keep working.

File layout intentionally keeps bodies outside the repo: ``PILOT_HOME``
defaults to ``~/Library/Application Support/Pilot`` which is gitignored
by virtue of not being in the tree.

Usage
-----
    from pilot import prompts
    prompts.load_env()             # call once at daemon boot
    prompts.require_all()          # assert every required key resolves
    sys_prompt = prompts.get("AGENT_SYSTEM")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

try:
    from dotenv import load_dotenv as _dotenv_load
except ImportError:
    _dotenv_load = None

_PREFIX = "PILOT_PROMPT_"

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
    """Raised when a required prompt is missing or empty."""


def load_env(dotenv_path: str | Path | None = None) -> None:
    """Populate ``os.environ`` from a .env file if present."""
    if _dotenv_load is None:
        return

    candidates: list[Path] = []
    if dotenv_path is not None:
        candidates.append(Path(dotenv_path).expanduser())

    pilot_home = os.environ.get("PILOT_HOME")
    if pilot_home:
        candidates.append(Path(pilot_home).expanduser() / ".env")

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


def _prompts_dir() -> Path:
    """Resolve the prompts directory without creating it (avoids side effects in tests)."""
    home_override = os.environ.get("PILOT_HOME")
    if home_override:
        return Path(home_override).expanduser() / "prompts"
    return Path("~/Library/Application Support/Pilot/prompts").expanduser()


def _file_for(name: str) -> Path:
    stem = name.removeprefix(_PREFIX).lower()
    return _prompts_dir() / f"{stem}.md"


def _read_file(name: str) -> str:
    path = _file_for(name)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_env(name: str) -> str:
    key = name if name.startswith(_PREFIX) else _PREFIX + name
    return os.environ.get(key, "").strip()


def _resolve(name: str) -> str:
    """File wins over env — makes iteration easy without restarting the daemon."""
    return _read_file(name) or _read_env(name)


def get(name: str) -> str:
    """Return the prompt text for ``name`` (without the ``PILOT_PROMPT_`` prefix)."""
    value = _resolve(name)
    if not value:
        stem = name.removeprefix(_PREFIX).lower()
        raise PromptConfigError(
            f"Prompt {name!r} is missing. "
            f"Create {_prompts_dir() / (stem + '.md')!s} "
            f"or set {_PREFIX}{stem.upper()} in your .env."
        )
    return value


def require_all(names: Iterable[str] = REQUIRED) -> None:
    """Assert every prompt in ``names`` resolves to non-empty text."""
    missing: list[str] = []
    for n in names:
        if not _resolve(n):
            missing.append(n)
    if missing:
        raise PromptConfigError(
            "Missing required prompts: "
            + ", ".join(sorted(missing))
            + f". Add files under {_prompts_dir()!s} or set "
            + ", ".join(f"{_PREFIX}{m}" for m in sorted(missing))
            + " in .env."
        )


def snapshot() -> dict[str, int]:
    """Return {prompt_name: length} — safe to log without leaking content."""
    out: dict[str, int] = {}
    for n in REQUIRED:
        out[n] = len(_resolve(n))
    return out
