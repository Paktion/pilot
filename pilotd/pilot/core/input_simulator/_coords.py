"""
Shared coordinate-space helpers used by both input backends.

All public InputSimulator coordinates are phone-screen-relative.  These
helpers resolve the iPhone Mirroring window bounds (with the phone-screen
sub-region offsets for title bar and bezels), validate that a point lies
within the phone display rectangle, and convert phone-screen-relative
(x, y) into screen-absolute pixels.

A single bounds snapshot is used per public action so that
``bounds_check_with`` and ``to_absolute_with`` always operate on the same
view of the world.  This eliminates the TOCTOU race that would exist if
each helper queried the window manager independently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from pilot.core.window_capture import MirroringWindowManager


# The macOS title bar height (in points) for the iPhone Mirroring window.
# Used as a fallback when the window manager cannot provide the phone
# screen region.  The actual value is determined at runtime via
# get_phone_screen_region() when available.
_DEFAULT_TITLE_BAR_HEIGHT: float = 28


class InputError(Exception):
    """Raised when an input simulation operation fails."""


class OutOfBoundsError(InputError):
    """Raised when the target coordinates fall outside the mirroring window."""


def refresh_bounds(wm: "MirroringWindowManager") -> None:
    """Re-query the window server so cached bounds stay current.

    Called at the start of every public action to handle the case where
    the user drags or resizes the iPhone Mirroring window between steps.
    Failures are silently ignored -- the subsequent ``get_bounds()`` call
    will raise if the window truly cannot be found.
    """
    try:
        wm.refresh()
    except Exception:
        pass  # Will fail at the bounds/absolute-coord stage anyway.


def get_bounds(wm: "MirroringWindowManager") -> Dict[str, Any]:
    """Return fresh window bounds and phone-screen region in one call.

    Returns a dict with keys:
      ``x``, ``y``, ``width``, ``height``  -- full window bounds
      ``phone_x``, ``phone_y``             -- phone-screen origin (window-relative)
      ``phone_w``, ``phone_h``             -- phone-screen size

    This single query is used by both ``bounds_check_with`` and
    ``to_absolute_with`` so they always operate on the same snapshot.
    """
    try:
        bounds = wm.get_window_bounds()
    except Exception as exc:
        raise InputError(
            "Cannot determine the iPhone Mirroring window position. "
            "Make sure iPhone Mirroring is open and visible on screen, "
            "and that your iPhone is locked (screen off). If you just "
            "unlocked your iPhone, lock it again and wait a few seconds."
        ) from exc

    # Try to get the precise phone-screen region (accounts for title bar
    # and bezels).  Fall back to the default 28pt title-bar offset if the
    # window manager does not support get_phone_screen_region().
    try:
        region = wm.get_phone_screen_region()
        phone_x = region["x"]
        phone_y = region["y"]
        phone_w = region["width"]
        phone_h = region["height"]
    except Exception:
        # Fallback: assume only a title bar offset, no bezel.
        phone_x = 0.0
        phone_y = _DEFAULT_TITLE_BAR_HEIGHT
        phone_w = bounds["width"]
        phone_h = bounds["height"] - _DEFAULT_TITLE_BAR_HEIGHT

    return {
        **bounds,
        "phone_x": phone_x,
        "phone_y": phone_y,
        "phone_w": phone_w,
        "phone_h": phone_h,
    }


def to_absolute_with(
    x: float, y: float, bounds: Dict[str, Any]
) -> tuple[int, int]:
    """Convert phone-screen-relative *(x, y)* to screen-absolute pixels.

    Uses the pre-fetched *bounds* dict (from ``get_bounds()``) so that
    the coordinate conversion shares the same window snapshot as the
    bounds check.

    The title-bar / bezel offset is added automatically: callers pass
    coordinates relative to the phone display area, not the macOS window
    origin.
    """
    abs_x = round(bounds["x"] + bounds["phone_x"] + x)
    abs_y = round(bounds["y"] + bounds["phone_y"] + y)
    return abs_x, abs_y


def bounds_check_with(
    x: float, y: float, bounds: Dict[str, Any]
) -> None:
    """Ensure *(x, y)* lies inside the phone-screen region.

    Uses the pre-fetched *bounds* dict so it shares the same snapshot as
    ``to_absolute_with``.

    Raises
    ------
    OutOfBoundsError
        If the point is outside the phone display rectangle.
    """
    pw = bounds["phone_w"]
    ph = bounds["phone_h"]
    if not (0 <= x <= pw and 0 <= y <= ph):
        raise OutOfBoundsError(
            f"Coordinates ({x:.0f}, {y:.0f}) are outside the phone screen "
            f"region ({pw:.0f}x{ph:.0f}). The LLM may have generated "
            f"coordinates outside the visible area. This is usually a "
            f"transient issue -- the agent will retry with corrected coordinates."
        )
