"""
Synthetic input dispatch for the iPhone Mirroring window.

Two backends are exposed:

    :class:`InputSimulator`
        Default path. Uses ``pyautogui`` with a ``cliclick`` subprocess
        fallback. Moves the user's visible cursor and steals focus briefly
        for keyboard actions.

    :class:`CGEventInputSimulator`
        Non-intrusive path built on Quartz ``CGEventPostToPid``. Sends
        events directly to the iPhone Mirroring process without moving
        the cursor or stealing focus.

Both share coordinate semantics: all public ``(x, y)`` arguments are
phone-screen-relative and are internally converted to screen-absolute
pixels via the window manager.
"""

from __future__ import annotations

from pilot.core.input_simulator.cgevent import CGEventInputSimulator
from pilot.core.input_simulator.core import (
    InputError,
    InputSimulator,
    OutOfBoundsError,
)

__all__ = [
    "CGEventInputSimulator",
    "InputError",
    "InputSimulator",
    "OutOfBoundsError",
]
