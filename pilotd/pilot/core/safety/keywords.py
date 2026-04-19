"""Keyword and pattern constants used by the safety guard.

Centralises every keyword list, screen-context indicator, and compiled regex
pattern consumed by the guard module. Keeping these in one place makes them
easy to audit and adjust without touching the orchestration logic.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Destructive verbs / phrases
# ---------------------------------------------------------------------------

# Verbs and phrases that imply destructive intent. Word-boundary matching is
# used elsewhere to avoid false positives (e.g. "format" inside "information").
_DESTRUCTIVE_VERBS: list[str] = [
    "delete",
    "remove",
    "erase",
    "cancel subscription",
    "unsubscribe",
    "clear all",
    "reset",
    "format",
    "factory reset",
    "wipe",
    "trash",
    "purge",
    "nuke",
    "uninstall",
    "deactivate",
    "close account",
]

# Backwards-compatible alias used internally.
_DESTRUCTIVE_KEYWORDS: list[str] = _DESTRUCTIVE_VERBS


def _compile_destructive_patterns() -> list[re.Pattern[str]]:
    """Compile word-boundary regex patterns for every destructive verb."""
    patterns: list[re.Pattern[str]] = []
    seen: set[str] = set()
    for kw in _DESTRUCTIVE_VERBS:
        if kw in seen:
            continue
        seen.add(kw)
        patterns.append(re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE))
    return patterns


_DESTRUCTIVE_PATTERNS: list[re.Pattern[str]] = _compile_destructive_patterns()


def match_destructive_keyword_label(text: str) -> Optional[str]:
    """Return the human-readable verb for the first destructive match in *text*.

    Parameters
    ----------
    text : str
        Text to scan.

    Returns
    -------
    str or None
        The matched keyword (not a regex), or ``None`` if nothing matched.
    """
    seen: set[str] = set()
    for kw in _DESTRUCTIVE_VERBS:
        if kw in seen:
            continue
        seen.add(kw)
        if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
            return kw
    return None


# ---------------------------------------------------------------------------
# Sensitive-context keyword groups
# ---------------------------------------------------------------------------

# Financial transaction indicators.
_FINANCIAL_KEYWORDS: list[str] = [
    "buy",
    "purchase",
    "pay",
    "payment",
    "subscribe",
    "order",
    "checkout",
    "add to cart",
    "place order",
    "confirm purchase",
    "send money",
    "transfer",
    "donate",
    "tip",
    "venmo",
    "zelle",
    "apple pay",
]

# Communication / messaging indicators.
_MESSAGING_KEYWORDS: list[str] = [
    "send message",
    "send text",
    "send email",
    "compose",
    "reply",
    "forward",
    "post",
    "tweet",
    "comment",
    "dm",
    "direct message",
]

# Authentication / credential indicators.
_AUTH_KEYWORDS: list[str] = [
    "password",
    "passcode",
    "sign in",
    "log in",
    "login",
    "credential",
    "two-factor",
    "2fa",
    "otp",
    "verification code",
    "biometric",
    "face id",
    "touch id",
]

# NSFW / harmful content categories that should never be automated.
_BLOCKED_CONTENT_KEYWORDS: list[str] = [
    "nsfw",
    "porn",
    "explicit",
    "nude",
    "harass",
    "spam",
    "scam",
    "phishing",
    "stalk",
    "bully",
    "threaten",
    "hate speech",
    "self-harm",
    "suicide",
]


# ---------------------------------------------------------------------------
# App-category heuristics (used for context classification, not blocking)
# ---------------------------------------------------------------------------

# NOTE: The previous reference implementation shipped a default blocklist of
# finance apps. That behaviour is intentionally dropped here: automating
# finance apps is a supported use case and users opt in explicitly via the
# constructor's ``blocked_apps`` argument.

_SENSITIVE_MESSAGING_APPS: list[str] = [
    "messages",
    "imessage",
    "whatsapp",
    "telegram",
    "signal",
    "messenger",
    "slack",
    "discord",
    "teams",
    "wechat",
    "line",
]

_SENSITIVE_EMAIL_APPS: list[str] = [
    "mail",
    "gmail",
    "outlook",
    "yahoo mail",
    "protonmail",
    "spark",
]

_SENSITIVE_SOCIAL_APPS: list[str] = [
    "twitter",
    "x",
    "instagram",
    "facebook",
    "tiktok",
    "snapchat",
    "reddit",
    "linkedin",
    "threads",
    "bluesky",
    "mastodon",
    "youtube",
]


# ---------------------------------------------------------------------------
# On-screen context keywords
# ---------------------------------------------------------------------------

# Screen-context keywords that suggest we're on a confirmation/payment page.
_CHECKOUT_SCREEN_KEYWORDS: list[str] = [
    "confirm order",
    "place order",
    "pay now",
    "complete purchase",
    "checkout",
    "payment method",
    "billing",
    "credit card",
    "debit card",
    "cvv",
    "expiry",
    "total:",
    "subtotal:",
    "order summary",
    "apple pay",
    "subscribe",
]

_CONFIRMATION_DIALOG_KEYWORDS: list[str] = [
    "are you sure",
    "confirm",
    "cannot be undone",
    "permanently",
    "delete forever",
    "this action",
    "do you want to",
]


# ---------------------------------------------------------------------------
# Defaults and tuning constants
# ---------------------------------------------------------------------------

# Default action categories that require user confirmation.
_DEFAULT_CONFIRMATION_CATEGORIES: list[str] = [
    "send_message",
    "delete",
    "purchase",
    "payment",
    "password",
    "sign_in",
]

# Numeric scores for cumulative risk tracking.
_RISK_SCORE_MAP: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 3,
    "critical": 5,
}

# Coordinate proximity threshold (pixels) for loop detection.
_LOOP_COORD_THRESHOLD: int = 20
