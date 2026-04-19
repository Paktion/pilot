"""Safety gate that screens every task and action before execution.

Every action flows through :class:`SafetyGuard` before it is executed. The
guard enforces rate limiting, detects sensitive contexts (payments, messaging,
authentication), blocks prohibited content, and gates high-risk operations
behind explicit user confirmation.

Typical usage::

    guard = SafetyGuard(
        confirm_callback=my_confirm_fn,
        blocked_apps=["Venmo", "Cash App"],
    )

    result = guard.check_task("Send a text to Mom")
    if not result.allowed:
        print(f"Task blocked: {result.reason}")

    result = guard.check_action({"type": "type_text", "text": "hello"})
    if result.requires_confirmation:
        confirmed = await my_confirm_fn(result.confirmation_message)
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Callable, Optional

from pilot.core.safety.detectors import (
    check_authentication,
    check_blocked_apps,
    check_confirmation_dialog,
    check_destructive,
    check_financial,
    check_messaging,
)
from pilot.core.safety.helpers import (
    classify_risk,
    coords_similar,
    swipe_similar,
)
from pilot.core.safety.keywords import (
    _DEFAULT_CONFIRMATION_CATEGORIES,
    _RISK_SCORE_MAP,
)
from pilot.core.safety.rate_limiter import RateLimiter
from pilot.core.safety.result import SafetyResult
from pilot.core.safety.task_check import check_task_text

logger = logging.getLogger("pilotd.safety")


class SafetyGuard:
    """Central safety gate that screens every action before execution.

    Parameters
    ----------
    confirm_callback : callable, optional
        An async or sync function with signature ``(description: str) -> bool``
        that is called when user confirmation is needed. If ``None``, high-
        risk actions requiring confirmation are auto-denied (fail-closed).
    blocked_apps : list[str], optional
        Application names the agent must never interact with. Example:
        ``["Venmo", "Cash App"]``. There is no default blocklist -- the
        caller opts in explicitly.
    require_confirmation_for : list[str], optional
        Categories of actions that require explicit user confirmation.
        Defaults to send_message/delete/purchase/payment/password/sign_in.
    max_actions_per_minute : int
        Maximum number of actions permitted in any rolling 60-second window.
        Defaults to ``20``.
    block_cooldown_seconds : float
        Minimum time after a blocked action before another attempt is allowed.
    cumulative_risk_threshold : int
        Total risk score across the session at which further low/medium
        actions start requiring confirmation.
    """

    def __init__(
        self,
        confirm_callback: Optional[Callable[..., Any]] = None,
        blocked_apps: Optional[list[str]] = None,
        require_confirmation_for: Optional[list[str]] = None,
        max_actions_per_minute: int = 20,
        block_cooldown_seconds: float = 2.0,
        cumulative_risk_threshold: int = 10,
    ) -> None:
        self._confirm_callback = confirm_callback
        self._blocked_apps: list[str] = [
            app.lower() for app in (blocked_apps or [])
        ]
        self._confirmation_categories: list[str] = (
            require_confirmation_for
            if require_confirmation_for is not None
            else list(_DEFAULT_CONFIRMATION_CATEGORIES)
        )

        self._rate_limiter = RateLimiter(max_actions_per_minute)

        self._block_cooldown_seconds = block_cooldown_seconds
        self._last_block_time: Optional[float] = None

        self._cumulative_risk_score: int = 0
        self._cumulative_risk_threshold = cumulative_risk_threshold

        logger.info(
            "SafetyGuard initialised  blocked_apps=%s  rate_limit=%d/min  "
            "cooldown=%.1fs  cumulative_threshold=%d",
            self._blocked_apps,
            self._rate_limiter.max_actions_per_minute,
            self._block_cooldown_seconds,
            self._cumulative_risk_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_action(
        self,
        action: dict[str, Any],
        screenshot_context: Optional[str] = None,
    ) -> SafetyResult:
        """Check whether *action* is safe to execute.

        Runs, in order: cooldown, rate limiting, blocked apps, destructive
        detection, financial detection, messaging detection, authentication
        protection, on-screen confirmation dialog awareness, and cumulative
        risk escalation.
        """
        context = (screenshot_context or "").lower()

        cooldown_result = self._check_block_cooldown()
        if not cooldown_result.allowed:
            return cooldown_result

        rate_result = self._check_rate_limit()
        if not rate_result.allowed:
            self._record_block()
            return rate_result

        app_result = check_blocked_apps(context, self._blocked_apps)
        if not app_result.allowed:
            self._record_block()
            return app_result

        ordered_checks = (
            check_destructive,
            check_financial,
            check_messaging,
            check_authentication,
        )
        for detector in ordered_checks:
            result = detector(action, context)
            if not result.allowed:
                self._record_block()
                return result
            if result.requires_confirmation:
                return result

        dialog_result = check_confirmation_dialog(action, context)
        if dialog_result.requires_confirmation:
            return dialog_result

        risk = classify_risk(action, context)
        cumulative_result = self._check_cumulative_risk(risk)
        if cumulative_result is not None:
            return cumulative_result

        return SafetyResult(
            allowed=True,
            reason="Action passed all safety checks.",
            risk_level=risk,
        )

    def check_task(self, task: str) -> SafetyResult:
        """Check whether the overall task description is safe to attempt.

        Screens for prohibited content, spam / mass-action patterns, blocked
        apps, destructive verbs, and financial intent.
        """
        return check_task_text(task, self._blocked_apps)

    def record_action(
        self, action: dict[str, Any], screenshot_context: Optional[str] = None
    ) -> None:
        """Record that an action was executed (for rate limiting and risk)."""
        self._rate_limiter.record()
        context = (screenshot_context or "").lower()
        risk = classify_risk(action, context)
        self._cumulative_risk_score += _RISK_SCORE_MAP.get(risk, 0)

    def reset_rate_limit(self) -> None:
        """Clear the rate-limit counter, allowing a fresh burst of actions."""
        self._rate_limiter.clear()

    def check_action_loop(
        self, recent_actions: list[dict[str, Any]]
    ) -> SafetyResult:
        """Detect when the agent is stuck repeating the same action."""
        if len(recent_actions) < 4:
            return SafetyResult(
                allowed=True, reason="Not enough actions to detect a loop."
            )

        tail = recent_actions[-4:]
        ref = tail[0]
        ref_type = ref.get("type", "")
        if not ref_type:
            return SafetyResult(
                allowed=True, reason="No action type to compare."
            )

        all_same = True
        for act in tail[1:]:
            if act.get("type", "") != ref_type:
                all_same = False
                break
            if ref_type in ("tap", "double_tap", "long_press"):
                if not coords_similar(ref, act):
                    all_same = False
                    break
            if ref_type == "type_text":
                if ref.get("text", "") != act.get("text", ""):
                    all_same = False
                    break
            if ref_type == "swipe":
                if not swipe_similar(ref, act):
                    all_same = False
                    break

        if all_same:
            logger.warning(
                "Stuck-loop detected: action %r repeated %d times.",
                ref_type,
                len(tail),
            )
            return SafetyResult(
                allowed=False,
                reason=(
                    f"Action loop detected: '{ref_type}' has been repeated "
                    f"{len(tail)} times at the same location. The agent "
                    f"appears to be stuck."
                ),
                risk_level="high",
            )

        return SafetyResult(allowed=True, reason="No action loop detected.")

    def reset_cumulative_risk(self) -> None:
        """Reset the cumulative risk score to zero."""
        self._cumulative_risk_score = 0
        logger.debug("Cumulative risk score reset.")

    @property
    def cumulative_risk_score(self) -> int:
        """Current cumulative risk score for the session."""
        return self._cumulative_risk_score

    async def request_confirmation(
        self, message: str, risk_level: str = "high"
    ) -> bool:
        """Ask the user for confirmation via the registered callback.

        When no callback is registered, low/medium risk auto-approves and
        high/critical risk auto-denies (fail-closed).
        """
        if self._confirm_callback is None:
            if risk_level in ("high", "critical"):
                logger.warning(
                    "No confirm_callback set; auto-DENYING %s-risk action.",
                    risk_level,
                )
                return False
            logger.debug(
                "No confirm_callback set; auto-approving %s-risk action.",
                risk_level,
            )
            return True

        try:
            if inspect.iscoroutinefunction(self._confirm_callback):
                return await self._confirm_callback(message)
            return self._confirm_callback(message)
        except Exception as exc:
            logger.error("Confirmation callback failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_rate_limit(self) -> SafetyResult:
        within, count = self._rate_limiter.check()
        if not within:
            return SafetyResult(
                allowed=False,
                reason=(
                    f"Rate limit exceeded: {count} actions in the last "
                    f"minute (limit: "
                    f"{self._rate_limiter.max_actions_per_minute}). "
                    f"This may indicate a runaway loop."
                ),
                risk_level="critical",
            )
        return SafetyResult(allowed=True, reason="Within rate limit.")

    def _record_block(self) -> None:
        self._last_block_time = time.monotonic()

    def _check_block_cooldown(self) -> SafetyResult:
        if self._last_block_time is None:
            return SafetyResult(allowed=True, reason="No recent block.")
        elapsed = time.monotonic() - self._last_block_time
        remaining = self._block_cooldown_seconds - elapsed
        if remaining > 0:
            logger.info("Block cooldown active: %.1fs remaining.", remaining)
            return SafetyResult(
                allowed=False,
                reason=(
                    f"Cooldown active: an action was blocked {elapsed:.1f}s "
                    f"ago. Please wait {remaining:.1f}s before retrying."
                ),
                risk_level="medium",
            )
        return SafetyResult(
            allowed=True, reason="Cooldown period elapsed."
        )

    def _check_cumulative_risk(self, risk: str) -> Optional[SafetyResult]:
        if risk not in ("low", "medium"):
            return None
        if self._cumulative_risk_score >= self._cumulative_risk_threshold:
            logger.warning(
                "Cumulative risk threshold reached: score=%d  threshold=%d",
                self._cumulative_risk_score,
                self._cumulative_risk_threshold,
            )
            return SafetyResult(
                allowed=True,
                reason=(
                    f"Cumulative risk threshold reached "
                    f"(score: {self._cumulative_risk_score}, "
                    f"threshold: {self._cumulative_risk_threshold})."
                ),
                requires_confirmation=True,
                confirmation_message=(
                    "The agent has performed a large number of elevated-risk "
                    "actions in this session. Do you want to continue?"
                ),
                risk_level="high",
            )
        return None
