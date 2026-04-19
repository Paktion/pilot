"""The :class:`SafetyResult` dataclass shared by guard and detectors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyResult:
    """Outcome of a safety check on an action or task.

    Attributes
    ----------
    allowed : bool
        ``True`` if the action may proceed (possibly after confirmation).
    reason : str
        Human-readable explanation of why the action was allowed or blocked.
    requires_confirmation : bool
        When ``True`` the caller must obtain explicit user approval before
        executing the action.
    confirmation_message : str
        The message to present to the user when confirmation is needed.
        Empty string when no confirmation is required.
    risk_level : str
        One of ``"low"``, ``"medium"``, ``"high"``, or ``"critical"``.
    """

    allowed: bool
    reason: str
    requires_confirmation: bool = False
    confirmation_message: str = ""
    risk_level: str = "low"
