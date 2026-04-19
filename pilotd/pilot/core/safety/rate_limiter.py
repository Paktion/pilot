"""Rolling 60-second action rate limiter.

Tracks the timestamps of recent actions in a deque and reports whether the
configured ceiling has been exceeded. The tracker is intentionally minimal --
it has no knowledge of action payloads; callers invoke :meth:`record` when an
action actually executes and :meth:`check` whenever they want to know if the
next action would breach the limit.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

logger = logging.getLogger("pilotd.safety")


# ---------------------------------------------------------------------------
# Window size
# ---------------------------------------------------------------------------

# Length of the rolling window, in seconds.
_WINDOW_SECONDS: float = 60.0


class RateLimiter:
    """Rolling-window rate limiter with an integer per-minute ceiling.

    Parameters
    ----------
    max_actions_per_minute : int
        Maximum number of actions allowed in any rolling 60-second window.
        Defaults to ``20``.

    Notes
    -----
    Timestamps come from :func:`time.monotonic` so the limiter is immune to
    wall-clock adjustments. Old entries are pruned lazily on every call.
    """

    def __init__(self, max_actions_per_minute: int = 20) -> None:
        self._max_actions_per_minute = int(max_actions_per_minute)
        self._timestamps: deque[float] = deque()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, now: Optional[float] = None) -> None:
        """Record that an action was executed.

        Parameters
        ----------
        now : float, optional
            Monotonic timestamp to record. Defaults to the current time.
        """
        ts = time.monotonic() if now is None else now
        self._timestamps.append(ts)
        self._prune(ts)

    def clear(self) -> None:
        """Forget all recorded timestamps."""
        self._timestamps.clear()
        logger.debug("Rate limit counter reset.")

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def check(self) -> tuple[bool, int]:
        """Return ``(within_limit, current_count)`` for the rolling window.

        Returns
        -------
        tuple[bool, int]
            ``within_limit`` is ``True`` when a further action would be
            permitted, ``False`` when the ceiling has been reached.
            ``current_count`` is the number of timestamps still inside the
            rolling 60-second window after pruning.
        """
        now = time.monotonic()
        self._prune(now)
        count = len(self._timestamps)
        within = count < self._max_actions_per_minute
        if not within:
            logger.warning(
                "Rate limit exceeded: %d actions in the last 60s (limit %d).",
                count,
                self._max_actions_per_minute,
            )
        return within, count

    @property
    def max_actions_per_minute(self) -> int:
        """The configured maximum number of actions per 60-second window."""
        return self._max_actions_per_minute

    @property
    def current_count(self) -> int:
        """Number of recorded actions still inside the rolling window."""
        self._prune(time.monotonic())
        return len(self._timestamps)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prune(self, now: float) -> None:
        """Drop timestamps older than the rolling-window size."""
        cutoff = now - _WINDOW_SECONDS
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
