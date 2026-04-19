"""Task-level (whole-string) safety screening.

Distinct from :mod:`pilot.core.safety.detectors` which inspects individual
actions; ``check_task_text`` inspects a full natural-language task string up
front, before any action is generated.
"""

from __future__ import annotations

import logging
import re

from pilot.core.safety.keywords import (
    _BLOCKED_CONTENT_KEYWORDS,
    _FINANCIAL_KEYWORDS,
    match_destructive_keyword_label,
)
from pilot.core.safety.result import SafetyResult

logger = logging.getLogger("pilotd.safety")


_SPAM_PATTERNS: tuple[str, ...] = (
    r"send\s+\d{2,}\s+messages",
    r"message\s+everyone",
    r"spam",
    r"send\s+to\s+all\s+contacts",
    r"bulk\s+send",
    r"mass\s+message",
)


def check_task_text(task: str, blocked_apps: list[str]) -> SafetyResult:
    """Screen a whole task description for prohibited or high-risk content.

    Parameters
    ----------
    task : str
        The natural-language task description provided by the user.
    blocked_apps : list[str]
        Lower-cased app names the caller has opted out of.

    Returns
    -------
    SafetyResult
    """
    task_lower = task.lower()

    for keyword in _BLOCKED_CONTENT_KEYWORDS:
        if keyword in task_lower:
            logger.warning("Task blocked by content filter: %r", task)
            return SafetyResult(
                allowed=False,
                reason=(
                    f"Task blocked: contains prohibited content ({keyword!r})."
                ),
                risk_level="critical",
            )

    for pattern in _SPAM_PATTERNS:
        if re.search(pattern, task_lower):
            logger.warning("Task blocked by spam filter: %r", task)
            return SafetyResult(
                allowed=False,
                reason=(
                    "Task blocked: appears to involve mass messaging or spam."
                ),
                risk_level="critical",
            )

    for app in blocked_apps:
        if app in task_lower:
            return SafetyResult(
                allowed=False,
                reason=f"Task blocked: involves blocked app ({app!r}).",
                risk_level="high",
            )

    destructive_kw = match_destructive_keyword_label(task_lower)
    if destructive_kw is not None:
        logger.warning(
            "Task contains destructive keyword %r: %r", destructive_kw, task
        )
        return SafetyResult(
            allowed=True,
            reason=(
                f"Task involves destructive action ({destructive_kw!r}); "
                "individual actions will require confirmation."
            ),
            requires_confirmation=True,
            confirmation_message=(
                f"This task may involve a destructive action "
                f"({destructive_kw!r}). Do you want to proceed?\n\n"
                f"Task: {task}"
            ),
            risk_level="high",
        )

    for keyword in _FINANCIAL_KEYWORDS:
        if keyword in task_lower:
            return SafetyResult(
                allowed=True,
                reason=(
                    f"Task involves financial action ({keyword!r}); "
                    "individual actions will require confirmation."
                ),
                requires_confirmation=True,
                confirmation_message=(
                    f"This task may involve a financial transaction "
                    f"({keyword!r}). Do you want to proceed?\n\n"
                    f"Task: {task}"
                ),
                risk_level="high",
            )

    return SafetyResult(
        allowed=True,
        reason="Task passed safety screening.",
        risk_level="low",
    )
