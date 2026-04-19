"""
AppleScript helpers for focusing the iPhone Mirroring window.

Keyboard events dispatched via ``pyautogui`` go to whichever window has
focus, so the default backend must briefly activate the iPhone Mirroring
app before calling ``typewrite`` or ``hotkey``. After the keystroke the
caller's previously-focused app is restored so the agent does not steal
focus for longer than necessary.
"""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger("pilotd.input")


def get_frontmost_app() -> str | None:
    """Return the name of the currently-frontmost process, or ``None``."""
    try:
        result = subprocess.run(
            [
                "osascript", "-e",
                'tell application "System Events" to get name of first '
                'application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception as exc:
        logger.warning("Failed to read frontmost app: %s", exc)
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def activate_mirroring() -> None:
    """Activate the iPhone Mirroring app and give it a moment to focus."""
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "iPhone Mirroring" to activate'],
            capture_output=True,
            timeout=3,
        )
        time.sleep(0.1)
    except Exception as exc:
        logger.warning("Failed to activate iPhone Mirroring: %s", exc)


def activate_app(app_name: str) -> None:
    """Activate *app_name*; best effort, never raises."""
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{app_name}" to activate'],
            capture_output=True,
            timeout=3,
        )
    except Exception:
        pass  # Best effort -- don't interrupt the agent over this
