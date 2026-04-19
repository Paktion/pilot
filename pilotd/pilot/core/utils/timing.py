"""Timing / retry helpers with exponential backoff."""

from __future__ import annotations

import time
from typing import Any, Callable


def adaptive_wait(
    base: float = 0.5,
    max_wait: float = 3.0,
    check_fn: Callable[[], bool] | None = None,
) -> bool:
    """Wait with exponential backoff until ``check_fn`` returns True.

    Returns True if the condition was met (or no predicate was supplied).
    """
    if check_fn is None:
        time.sleep(base)
        return True
    elapsed = 0.0
    delay = base
    while elapsed < max_wait:
        if check_fn():
            return True
        time.sleep(delay)
        elapsed += delay
        delay = min(delay * 2, max_wait - elapsed) if elapsed < max_wait else 0
    return check_fn()


def retry(
    fn: Callable[[], Any],
    max_retries: int = 3,
    delay: float = 1.0,
) -> Any:
    """Call ``fn`` up to ``max_retries`` times with exponential backoff.

    Raises the last exception if all attempts fail.
    """
    last_exc: BaseException | None = None
    current_delay = delay
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(current_delay)
                current_delay *= 2
    assert last_exc is not None
    raise last_exc
