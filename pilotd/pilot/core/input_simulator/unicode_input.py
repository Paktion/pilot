"""
Clipboard-based Unicode text input helper.

``pyautogui.typewrite()`` supports ASCII only. For any string containing
non-ASCII characters we fall back to the macOS clipboard via ``pbcopy``
and paste through ``Cmd+V``. This helper is shared by both input backends
(the ``pyautogui`` default path and the ``CGEvent`` non-intrusive path).
"""

from __future__ import annotations

import subprocess
import time
from typing import Callable


class _ClipboardError(Exception):
    """Raised when writing to the macOS clipboard fails."""


def copy_to_clipboard(text: str) -> None:
    """Write *text* to the macOS clipboard via ``pbcopy``.

    Raises
    ------
    _ClipboardError
        If the ``pbcopy`` subprocess exits non-zero.
    """
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))
    if process.returncode != 0:
        raise _ClipboardError(
            "Failed to write to the macOS clipboard via pbcopy. "
            "This is needed for typing non-ASCII text. Ensure the "
            "'pbcopy' command is available in your PATH."
        )


def paste_via_pyautogui(text: str) -> None:
    """Copy *text* to the clipboard and dispatch ``Cmd+V`` via pyautogui."""
    import pyautogui

    copy_to_clipboard(text)
    pyautogui.hotkey("command", "v")
    # Allow a brief moment for the paste to register.
    time.sleep(0.1)


def paste_via_callback(text: str, send_cmd_v: Callable[[], None]) -> None:
    """Copy *text* to the clipboard, then call *send_cmd_v* to paste it.

    The *send_cmd_v* callback is expected to dispatch a ``Cmd+V``
    keystroke by whatever backend the caller is using (e.g. CGEvent).
    """
    copy_to_clipboard(text)
    send_cmd_v()
    time.sleep(0.1)
