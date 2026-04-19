"""Typing helpers for the CGEvent backend.

ASCII text is sent as per-character key-down/key-up pairs; non-ASCII
text is routed through ``pbcopy`` + ``Cmd+V``. Both paths dispatch
events via a caller-supplied ``post`` callback so the same helpers work
regardless of which event-posting strategy the backend is using.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from Quartz import CGEventCreateKeyboardEvent, CGEventSetFlags
from Quartz.CoreGraphics import kCGEventFlagMaskCommand

from pilot.core.input_simulator._coords import InputError
from pilot.core.input_simulator._keycodes import (
    _KEY_NAME_TO_KEYCODE,
    _char_to_keycode_and_flags,
)
from pilot.core.input_simulator.unicode_input import (
    _ClipboardError,
    copy_to_clipboard,
)


def type_ascii_via_cgevent(
    text: str,
    interval: float,
    post: Callable[[Any], None],
) -> None:
    """Type ASCII *text* character-by-character via CGEvent keyboard events."""
    for ch in text:
        keycode, flags = _char_to_keycode_and_flags(ch)
        down = CGEventCreateKeyboardEvent(None, keycode, True)
        up = CGEventCreateKeyboardEvent(None, keycode, False)
        if flags:
            CGEventSetFlags(down, flags)
            CGEventSetFlags(up, flags)
        post(down)
        post(up)
        if interval > 0:
            time.sleep(interval)


def type_via_clipboard_cgevent(
    text: str,
    post: Callable[[Any], None],
) -> None:
    """Paste *text* via pbcopy + Cmd+V (routed through *post*)."""
    try:
        copy_to_clipboard(text)
    except _ClipboardError as exc:
        raise InputError(str(exc)) from exc

    v_keycode = _KEY_NAME_TO_KEYCODE["v"]
    down = CGEventCreateKeyboardEvent(None, v_keycode, True)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    up = CGEventCreateKeyboardEvent(None, v_keycode, False)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    post(down)
    post(up)
    time.sleep(0.1)
