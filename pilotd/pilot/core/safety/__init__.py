"""Safety subsystem: guardrails that screen every task and action.

Public API:

- :class:`SafetyGuard` -- main gate; call ``check_task`` or ``check_action``.
- :class:`SafetyResult` -- dataclass returned by both check methods.
"""

from pilot.core.safety.guard import SafetyGuard
from pilot.core.safety.result import SafetyResult

__all__ = ["SafetyGuard", "SafetyResult"]
