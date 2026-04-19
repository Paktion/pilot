"""Per-category safety detectors used by :class:`SafetyGuard`.

Each detector is a pure function that takes the action dict and a lower-cased
screen-context string and returns a :class:`SafetyResult`. Splitting these out
of the guard class keeps orchestration in ``guard.py`` and rule logic here.
"""

from __future__ import annotations

import logging
from typing import Any

from pilot.core.safety.helpers import format_confirmation_prompt
from pilot.core.safety.keywords import (
    _AUTH_KEYWORDS,
    _CHECKOUT_SCREEN_KEYWORDS,
    _CONFIRMATION_DIALOG_KEYWORDS,
    _FINANCIAL_KEYWORDS,
    _SENSITIVE_EMAIL_APPS,
    _SENSITIVE_MESSAGING_APPS,
    _SENSITIVE_SOCIAL_APPS,
    match_destructive_keyword_label,
)
from pilot.core.safety.result import SafetyResult

logger = logging.getLogger("pilotd.safety")


def check_blocked_apps(context: str, blocked_apps: list[str]) -> SafetyResult:
    """Return a blocking result if *context* mentions any user-blocked app."""
    for app in blocked_apps:
        if app in context:
            logger.warning("Blocked app detected in context: %s", app)
            return SafetyResult(
                allowed=False,
                reason=f"Action blocked: {app!r} is on the blocked apps list.",
                risk_level="high",
            )
    return SafetyResult(allowed=True, reason="No blocked apps detected.")


def check_destructive(action: dict[str, Any], context: str) -> SafetyResult:
    """Detect potentially destructive actions (delete, remove, erase, ...)."""
    action_type = action.get("type", "")
    text = action.get("text", "").lower()

    if action_type == "type_text":
        keyword = match_destructive_keyword_label(text)
        if keyword is not None:
            return SafetyResult(
                allowed=True,
                reason=f"Text contains destructive keyword ({keyword!r}).",
                requires_confirmation=True,
                confirmation_message=format_confirmation_prompt(
                    action,
                    context,
                    override_desc=(
                        f"The agent wants to type text containing "
                        f"{keyword!r}: \"{action.get('text', '')}\""
                    ),
                ),
                risk_level="high",
            )

    if action_type == "swipe":
        start_x = action.get("start_x", 0)
        end_x = action.get("end_x", 0)
        start_y = action.get("start_y", 0)
        end_y = action.get("end_y", 0)
        dx = abs(end_x - start_x)
        dy = abs(end_y - start_y)
        is_horizontal = dx > 50 and dy < 30
        is_right_to_left = end_x < start_x
        if is_horizontal and is_right_to_left:
            delete_indicators = ["delete", "trash", "remove", "swipe"]
            if any(ind in context for ind in delete_indicators):
                return SafetyResult(
                    allowed=True,
                    reason="Detected potential swipe-to-delete gesture.",
                    requires_confirmation=True,
                    confirmation_message=format_confirmation_prompt(
                        action,
                        context,
                        override_desc=(
                            "The agent is performing a swipe gesture that "
                            "may trigger a delete action."
                        ),
                    ),
                    risk_level="high",
                )

    if action_type == "tap":
        keyword = match_destructive_keyword_label(context)
        if keyword is not None:
            return SafetyResult(
                allowed=True,
                reason=(
                    f"Screen context contains destructive keyword ({keyword!r})."
                ),
                requires_confirmation=True,
                confirmation_message=format_confirmation_prompt(
                    action,
                    context,
                    override_desc=(
                        f"The agent is tapping on a screen that contains "
                        f"'{keyword}'. This might be a destructive action."
                    ),
                ),
                risk_level="high",
            )

    return SafetyResult(allowed=True, reason="No destructive action detected.")


def check_financial(action: dict[str, Any], context: str) -> SafetyResult:
    """Detect financial transaction contexts and require confirmation."""
    text = action.get("text", "").lower()

    for keyword in _CHECKOUT_SCREEN_KEYWORDS:
        if keyword in context:
            return SafetyResult(
                allowed=True,
                reason=f"Checkout/payment screen detected ({keyword!r}).",
                requires_confirmation=True,
                confirmation_message=format_confirmation_prompt(
                    action,
                    context,
                    override_desc=(
                        f"The agent is interacting with what appears to be "
                        f"a payment or checkout screen (detected: "
                        f"'{keyword}'). Review and confirm."
                    ),
                ),
                risk_level="high",
            )

    for keyword in _FINANCIAL_KEYWORDS:
        if keyword in text:
            return SafetyResult(
                allowed=True,
                reason=f"Financial keyword in text input ({keyword!r}).",
                requires_confirmation=True,
                confirmation_message=format_confirmation_prompt(
                    action,
                    context,
                    override_desc=(
                        f"The agent wants to type text related to a "
                        f"financial action ({keyword!r}): "
                        f"\"{action.get('text', '')}\""
                    ),
                ),
                risk_level="high",
            )

    return SafetyResult(allowed=True, reason="No financial context detected.")


def check_messaging(action: dict[str, Any], context: str) -> SafetyResult:
    """Detect messaging contexts and require confirmation before sending."""
    action_type = action.get("type", "")
    text = action.get("text", "")

    in_messaging_app = any(app in context for app in _SENSITIVE_MESSAGING_APPS)
    in_email_app = any(app in context for app in _SENSITIVE_EMAIL_APPS)
    in_social_app = any(app in context for app in _SENSITIVE_SOCIAL_APPS)

    send_indicators = ["send", "post", "publish", "submit", "reply"]
    context_has_send = any(ind in context for ind in send_indicators)

    if action_type == "tap" and context_has_send:
        if in_messaging_app or in_email_app or in_social_app:
            app_type = (
                "messaging" if in_messaging_app
                else "email" if in_email_app
                else "social media"
            )
            return SafetyResult(
                allowed=True,
                reason=f"Potential send action in {app_type} app.",
                requires_confirmation=True,
                confirmation_message=format_confirmation_prompt(
                    action,
                    context,
                    override_desc=(
                        f"The agent is about to tap what may be a 'send' "
                        f"button in a {app_type} app. Please confirm."
                    ),
                ),
                risk_level="medium",
            )

    if action_type == "type_text" and text and (in_messaging_app or in_email_app):
        preview = text if len(text) <= 200 else text[:197] + "..."
        return SafetyResult(
            allowed=True,
            reason="Composing a message in a communication app.",
            requires_confirmation=True,
            confirmation_message=(
                f"The agent wants to type the following message:\n\n"
                f"\"{preview}\"\n\n"
                f"Allow this?"
            ),
            risk_level="medium",
        )

    if action_type == "type_text" and text and in_social_app:
        preview = text if len(text) <= 200 else text[:197] + "..."
        return SafetyResult(
            allowed=True,
            reason="Composing a post on social media.",
            requires_confirmation=True,
            confirmation_message=(
                f"The agent wants to post on social media:\n\n"
                f"\"{preview}\"\n\n"
                f"Allow this?"
            ),
            risk_level="medium",
        )

    return SafetyResult(allowed=True, reason="No messaging context detected.")


def check_authentication(action: dict[str, Any], context: str) -> SafetyResult:
    """Detect password / credential entry and require confirmation.

    The actual text of a password is never included in log output or
    confirmation prompts.
    """
    action_type = action.get("type", "")
    text = action.get("text", "")

    password_context_indicators = [
        "password",
        "passcode",
        "secure text",
        "enter your password",
        "current password",
        "new password",
        "confirm password",
    ]
    on_password_screen = any(
        ind in context for ind in password_context_indicators
    )

    if action_type == "type_text" and on_password_screen:
        logger.info(
            "Password entry detected -- requiring confirmation. "
            "(Text content redacted.)"
        )
        return SafetyResult(
            allowed=True,
            reason="Typing into a password / credential field.",
            requires_confirmation=True,
            confirmation_message=(
                "The agent is about to enter text into what appears to be "
                "a password or credential field. The text content has been "
                "redacted for security.\n\n"
                "Allow this?"
            ),
            risk_level="high",
        )

    sign_in_indicators = [
        "sign in",
        "log in",
        "login",
        "create account",
        "register",
        "forgot password",
    ]
    on_sign_in_screen = any(ind in context for ind in sign_in_indicators)

    if action_type == "tap" and on_sign_in_screen:
        return SafetyResult(
            allowed=True,
            reason="Interacting with a sign-in / login screen.",
            requires_confirmation=True,
            confirmation_message=format_confirmation_prompt(
                action,
                context,
                override_desc=(
                    "The agent is interacting with a sign-in or login "
                    "screen. Please confirm this action."
                ),
            ),
            risk_level="high",
        )

    if action_type == "type_text" and text:
        for keyword in _AUTH_KEYWORDS:
            if keyword in text.lower():
                logger.info("Auth keyword %r detected in typed text.", keyword)
                return SafetyResult(
                    allowed=True,
                    reason=f"Typed text contains auth keyword ({keyword!r}).",
                    requires_confirmation=True,
                    confirmation_message=(
                        "The agent wants to type text related to "
                        "authentication or credentials. The full text has "
                        "been redacted for security.\n\n"
                        "Allow this?"
                    ),
                    risk_level="high",
                )

    settings_security_keywords = [
        "change password",
        "security",
        "privacy",
        "two-factor",
        "face id",
        "touch id",
        "apple id",
        "icloud",
    ]
    if "settings" in context and action_type == "tap":
        for keyword in settings_security_keywords:
            if keyword in context:
                return SafetyResult(
                    allowed=True,
                    reason=(
                        f"Tapping in Settings near security option ({keyword!r})."
                    ),
                    requires_confirmation=True,
                    confirmation_message=format_confirmation_prompt(
                        action,
                        context,
                        override_desc=(
                            f"The agent is tapping in Settings near a "
                            f"security-related option ({keyword}). "
                            f"Please confirm."
                        ),
                    ),
                    risk_level="high",
                )

    return SafetyResult(
        allowed=True, reason="No authentication context detected."
    )


def check_confirmation_dialog(
    action: dict[str, Any], context: str
) -> SafetyResult:
    """Detect on-screen confirmation dialogs and escalate to the user."""
    for keyword in _CONFIRMATION_DIALOG_KEYWORDS:
        if keyword in context:
            return SafetyResult(
                allowed=True,
                reason=(
                    f"On-screen confirmation dialog detected ({keyword!r})."
                ),
                requires_confirmation=True,
                confirmation_message=format_confirmation_prompt(
                    action,
                    context,
                    override_desc=(
                        f"The device is showing a confirmation dialog "
                        f"('{keyword}'). The agent wants to proceed. "
                        f"Please review and confirm."
                    ),
                ),
                risk_level="medium",
            )
    return SafetyResult(allowed=True, reason="No confirmation dialog detected.")
