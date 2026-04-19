"""Pure helper functions for safety classification and formatting.

These live outside :mod:`pilot.core.safety.guard` to keep the guard module
focused on orchestration and to let tests import them in isolation.
"""

from __future__ import annotations

from typing import Any, Optional

from pilot.core.safety.keywords import (
    _AUTH_KEYWORDS,
    _BLOCKED_CONTENT_KEYWORDS,
    _CHECKOUT_SCREEN_KEYWORDS,
    _FINANCIAL_KEYWORDS,
    _LOOP_COORD_THRESHOLD,
    _MESSAGING_KEYWORDS,
    _SENSITIVE_EMAIL_APPS,
    _SENSITIVE_MESSAGING_APPS,
    _SENSITIVE_SOCIAL_APPS,
    match_destructive_keyword_label,
)


def detect_sensitive_context(
    thought: str, action: dict[str, Any]
) -> list[str]:
    """Identify sensitive contexts present in thought / action text.

    Returns a (possibly empty) list drawn from ``"payment"``, ``"messaging"``,
    ``"authentication"``, ``"destructive"``, ``"messaging_app"``, and
    ``"social_media"``.
    """
    combined = (thought + " " + action.get("text", "")).lower()
    contexts: list[str] = []

    if any(kw in combined for kw in _FINANCIAL_KEYWORDS):
        contexts.append("payment")
    if any(kw in combined for kw in _MESSAGING_KEYWORDS):
        contexts.append("messaging")
    if any(kw in combined for kw in _AUTH_KEYWORDS):
        contexts.append("authentication")
    if match_destructive_keyword_label(combined) is not None:
        contexts.append("destructive")
    if any(app in combined for app in _SENSITIVE_MESSAGING_APPS):
        contexts.append("messaging_app")
    if any(app in combined for app in _SENSITIVE_SOCIAL_APPS):
        contexts.append("social_media")

    return contexts


def classify_risk(action: dict[str, Any], context: str) -> str:
    """Classify an action's risk level given its screen context.

    Returns ``"low"``, ``"medium"``, ``"high"``, or ``"critical"``.
    """
    context_lower = context.lower() if context else ""
    action_type = action.get("type", "")
    text = action.get("text", "").lower()

    if any(kw in context_lower for kw in _CHECKOUT_SCREEN_KEYWORDS):
        return "critical"

    if any(kw in text for kw in _BLOCKED_CONTENT_KEYWORDS):
        return "critical"

    if any(
        kw in context_lower for kw in ("password", "passcode", "sign in", "login")
    ):
        return "high"
    if match_destructive_keyword_label(text) is not None:
        return "high"

    if any(app in context_lower for app in _SENSITIVE_MESSAGING_APPS):
        return "medium"
    if any(app in context_lower for app in _SENSITIVE_SOCIAL_APPS):
        return "medium"
    if any(app in context_lower for app in _SENSITIVE_EMAIL_APPS):
        return "medium"

    if action_type == "type_text" and len(text) > 20:
        return "medium"

    return "low"


def format_confirmation_prompt(
    action: dict[str, Any],
    context: str,
    override_desc: Optional[str] = None,
) -> str:
    """Create a human-readable confirmation message for an action."""
    desc = override_desc if override_desc else describe_action(action)

    lines = [
        "Pilot Safety Check",
        "=" * 40,
        "",
        desc,
        "",
    ]

    if context:
        context_preview = context[:300] + ("..." if len(context) > 300 else "")
        lines.append(f"Screen context: {context_preview}")
        lines.append("")

    lines.append("Do you want to allow this action? (yes/no)")
    return "\n".join(lines)


def coords_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return ``True`` if two coordinate-based actions target the same spot."""
    ax, ay = a.get("x", 0), a.get("y", 0)
    bx, by = b.get("x", 0), b.get("y", 0)
    return (
        abs(ax - bx) <= _LOOP_COORD_THRESHOLD
        and abs(ay - by) <= _LOOP_COORD_THRESHOLD
    )


def swipe_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return ``True`` if two swipe actions have similar start / end points."""
    for key in ("start_x", "start_y", "end_x", "end_y"):
        if abs(a.get(key, 0) - b.get(key, 0)) > _LOOP_COORD_THRESHOLD:
            return False
    return True


def describe_action(action: dict[str, Any]) -> str:
    """Return a human-readable one-line description of *action*.

    Password text is redacted and descriptions are phrased as intentions
    rather than commands.
    """
    action_type = action.get("type", "unknown")

    if action_type == "tap":
        return f"Tap at coordinates ({action.get('x')}, {action.get('y')})."

    if action_type == "double_tap":
        return f"Double-tap at ({action.get('x')}, {action.get('y')})."

    if action_type == "long_press":
        duration = action.get("duration", 1.0)
        return (
            f"Long-press at ({action.get('x')}, {action.get('y')}) "
            f"for {duration}s."
        )

    if action_type == "swipe":
        return (
            f"Swipe from ({action.get('start_x')}, {action.get('start_y')}) "
            f"to ({action.get('end_x')}, {action.get('end_y')})."
        )

    if action_type == "type_text":
        text = action.get("text", "")
        display = text if len(text) <= 60 else text[:57] + "..."
        return f"Type text: \"{display}\""

    if action_type == "key":
        mods = action.get("modifiers", [])
        prefix = "+".join(mods) + "+" if mods else ""
        return f"Press key: {prefix}{action.get('key')}."

    if action_type == "home":
        return "Navigate to the home screen."

    if action_type == "back":
        return "Go back (swipe-back gesture)."

    if action_type == "scroll":
        return (
            f"Scroll {action.get('direction', 'down')} "
            f"(amount: {action.get('amount', 3)})."
        )

    if action_type == "wait":
        return f"Wait {action.get('seconds', 1.0)} seconds."

    return f"Unknown action: {action}"
