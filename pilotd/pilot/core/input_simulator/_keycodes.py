"""
Mac virtual keycode tables used by the CGEvent input backend.

Reference: ``Events.h`` / Carbon HIToolbox headers. These keycodes
are passed to ``CGEventCreateKeyboardEvent`` to synthesise keystrokes
at the iPhone Mirroring process.
"""

from __future__ import annotations

from Quartz.CoreGraphics import (
    kCGEventFlagMaskAlphaShift,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
)

from pilot.core.input_simulator._coords import InputError

# Modifier key name -> (CGEvent flag mask, virtual keycode for the modifier)
_MODIFIER_MAP: dict[str, tuple[int, int]] = {
    "command": (kCGEventFlagMaskCommand, 0x37),
    "cmd": (kCGEventFlagMaskCommand, 0x37),
    "shift": (kCGEventFlagMaskShift, 0x38),
    "option": (kCGEventFlagMaskAlternate, 0x3A),
    "alt": (kCGEventFlagMaskAlternate, 0x3A),
    "control": (kCGEventFlagMaskControl, 0x3B),
    "ctrl": (kCGEventFlagMaskControl, 0x3B),
    "capslock": (kCGEventFlagMaskAlphaShift, 0x39),
}

_KEY_NAME_TO_KEYCODE: dict[str, int] = {
    # Letters
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E,
    "f": 0x03, "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26,
    "k": 0x28, "l": 0x25, "m": 0x2E, "n": 0x2D, "o": 0x1F,
    "p": 0x23, "q": 0x0C, "r": 0x0F, "s": 0x01, "t": 0x11,
    "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07, "y": 0x10,
    "z": 0x06,
    # Numbers
    "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15,
    "5": 0x17, "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
    # Punctuation / symbols
    "-": 0x1B, "=": 0x18, "[": 0x21, "]": 0x1E, "\\": 0x2A,
    ";": 0x29, "'": 0x27, ",": 0x2B, ".": 0x2F, "/": 0x2C,
    "`": 0x32,
    # Whitespace & editing
    "space": 0x31, " ": 0x31,
    "return": 0x24, "enter": 0x24,
    "tab": 0x30,
    "delete": 0x33, "backspace": 0x33,
    "forwarddelete": 0x75,
    "escape": 0x35, "esc": 0x35,
    # Navigation
    "up": 0x7E, "down": 0x7D, "left": 0x7B, "right": 0x7C,
    "home": 0x73, "end": 0x77,
    "pageup": 0x74, "pagedown": 0x79,
    # Function keys
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
}

# Characters that require Shift to be held on a US keyboard layout.
_SHIFT_CHARS: dict[str, str] = {
    "~": "`", "!": "1", "@": "2", "#": "3", "$": "4",
    "%": "5", "^": "6", "&": "7", "*": "8", "(": "9",
    ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".",
    "?": "/",
    # Upper-case letters handled separately in _char_to_keycode_and_flags
}


def _char_to_keycode_and_flags(ch: str) -> tuple[int, int]:
    """Return (virtual_keycode, modifier_flags) for a single character.

    For upper-case letters and shifted symbols the Shift flag is included.
    Raises ``InputError`` if the character has no known mapping.
    """
    # Check shifted symbols first
    if ch in _SHIFT_CHARS:
        base = _SHIFT_CHARS[ch]
        kc = _KEY_NAME_TO_KEYCODE.get(base)
        if kc is not None:
            return kc, kCGEventFlagMaskShift
    # Upper-case letter
    if ch.isupper():
        kc = _KEY_NAME_TO_KEYCODE.get(ch.lower())
        if kc is not None:
            return kc, kCGEventFlagMaskShift
    # Direct lookup (lower-case letters, digits, unshifted punctuation)
    kc = _KEY_NAME_TO_KEYCODE.get(ch)
    if kc is not None:
        return kc, 0
    raise InputError(
        f"No keycode mapping for character {ch!r}. "
        f"Use type_text with clipboard mode for non-ASCII characters."
    )
