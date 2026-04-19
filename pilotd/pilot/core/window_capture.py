"""Window capture for the Pilot daemon.

Locates, tracks, and captures the macOS iPhone Mirroring window. Maps
coordinates between window-relative and screen-absolute spaces, and
isolates the phone screen region (excluding title bar and bezels).
Requires macOS 15 Sequoia+ with iPhone Mirroring.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from pilot.core._window_helpers import (
    capture_via_cg,
    capture_via_screencapture,
    find_mirroring_window_info,
    get_backing_scale_factor,
    window_id_is_valid,
)

logger = logging.getLogger("pilotd.window")

_MIRRORING_OWNER = "iPhone Mirroring"
_MIRRORING_WINDOW_NAME = "iPhone Mirroring"
_DEFAULT_TITLE_BAR_HEIGHT = 28
_DEFAULT_BEZEL_PADDING = 0


@dataclass(frozen=True)
class WindowBounds:
    """Immutable window position and size in screen points."""

    x: float
    y: float
    width: float
    height: float

    def contains_point(self, px: float, py: float) -> bool:
        """Return True if the screen-space point lies within these bounds."""
        return (
            self.x <= px <= self.x + self.width
            and self.y <= py <= self.y + self.height
        )


@dataclass(frozen=True)
class PhoneScreenRegion:
    """Phone display sub-region inside the mirroring window (window-relative)."""

    x: float
    y: float
    width: float
    height: float


class MirroringWindowError(Exception):
    """Raised when the iPhone Mirroring window cannot be found or captured."""


class MirroringWindowManager:
    """Discovers, tracks, and captures the iPhone Mirroring window.

    Caches the most recently discovered window ID and bounds. Call
    :meth:`find_window` again to refresh.
    """

    def __init__(
        self,
        title_bar_height: float = _DEFAULT_TITLE_BAR_HEIGHT,
        bezel_padding: float = _DEFAULT_BEZEL_PADDING,
    ) -> None:
        self._window_id: Optional[int] = None
        self._bounds: Optional[WindowBounds] = None
        self._owner_name: str = _MIRRORING_OWNER
        self._window_name: str = _MIRRORING_WINDOW_NAME
        self._title_bar_height: float = title_bar_height
        self._bezel_padding: float = bezel_padding
        self._retina_scale: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_window(self) -> int:
        """Locate the mirroring window; cache and return its CGWindowID."""
        window_info = find_mirroring_window_info(self._owner_name, self._window_name)
        if window_info is None:
            self._window_id = None
            self._bounds = None
            raise MirroringWindowError(
                "iPhone Mirroring window not found. To fix this:\n"
                "\n"
                "  1. Open the 'iPhone Mirroring' app on your Mac\n"
                "     (Spotlight: Cmd+Space, type 'iPhone Mirroring')\n"
                "  2. Make sure your iPhone is locked (screen off) --\n"
                "     iPhone Mirroring only works when the phone is locked\n"
                "  3. Wait for the mirrored screen to appear\n"
            )

        self._window_id = window_info.get("kCGWindowNumber")
        bounds_dict = window_info.get("kCGWindowBounds", {})
        self._bounds = WindowBounds(
            x=float(bounds_dict.get("X", 0)),
            y=float(bounds_dict.get("Y", 0)),
            width=float(bounds_dict.get("Width", 0)),
            height=float(bounds_dict.get("Height", 0)),
        )

        if self._bounds.width <= 0 or self._bounds.height <= 0:
            self._window_id = None
            self._bounds = None
            raise MirroringWindowError(
                "iPhone Mirroring window has invalid dimensions "
                f"({bounds_dict.get('Width', 0)}x{bounds_dict.get('Height', 0)}). "
                "The window may be minimized or not fully loaded. "
                "Make sure the iPhone Mirroring window is visible on screen "
                "and showing your iPhone's display. Try closing and reopening "
                "iPhone Mirroring, or ensure your iPhone is locked."
            )

        logger.info(
            "Found iPhone Mirroring window (id=%d) at (%s, %s) size %sx%s",
            self._window_id,
            self._bounds.x,
            self._bounds.y,
            self._bounds.width,
            self._bounds.height,
        )
        return self._window_id

    def capture_screenshot(self, *, use_fallback: bool = True) -> Image.Image:
        """Capture the mirroring window via CoreGraphics, falling back to CLI."""
        self._ensure_window()

        image = self._capture_via_cg()
        if image is not None:
            return image

        if use_fallback:
            logger.warning(
                "CoreGraphics capture returned None; falling back to screencapture CLI."
            )
            assert self._window_id is not None
            return capture_via_screencapture(self._window_id, MirroringWindowError)

        raise MirroringWindowError(
            "Screen capture failed. This usually means the Screen Recording "
            "permission is not granted. To fix this:\n"
            "\n"
            "  1. Open System Settings > Privacy & Security > Screen Recording\n"
            "  2. Enable the toggle for your terminal app (Terminal, iTerm2, etc.)\n"
            "  3. Restart your terminal and try again\n"
        )

    def get_window_bounds(self) -> dict:
        """Cached bounds as ``{x, y, width, height}`` floats."""
        self._ensure_window()
        assert self._bounds is not None
        return {
            "x": self._bounds.x,
            "y": self._bounds.y,
            "width": self._bounds.width,
            "height": self._bounds.height,
        }

    def window_to_screen_coords(self, wx: float, wy: float) -> tuple[float, float]:
        """Window-relative (incl. title bar) to screen-absolute coords."""
        self._ensure_window()
        assert self._bounds is not None
        return (self._bounds.x + wx, self._bounds.y + wy)

    def screen_to_window_coords(self, sx: float, sy: float) -> tuple[float, float]:
        """Screen-absolute to window-relative coords."""
        self._ensure_window()
        assert self._bounds is not None
        return (sx - self._bounds.x, sy - self._bounds.y)

    def is_window_available(self) -> bool:
        """Fresh (non-cached) check for whether the window currently exists."""
        return find_mirroring_window_info(self._owner_name, self._window_name) is not None

    def wait_for_window(self, timeout: float = 30, poll_interval: float = 0.5) -> int:
        """Block until the window appears; return its CGWindowID or raise."""
        logger.info("Waiting up to %.1fs for iPhone Mirroring window...", timeout)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                return self.find_window()
            except MirroringWindowError:
                time.sleep(poll_interval)

        raise MirroringWindowError(
            f"iPhone Mirroring window did not appear within {timeout:.0f} seconds. "
            "Make sure:\n"
            "  1. The 'iPhone Mirroring' app is open on your Mac\n"
            "  2. Your iPhone is locked (screen off)\n"
            "  3. Your iPhone is connected to the same Wi-Fi network\n"
            "  4. You have paired this Mac with your iPhone in System Settings\n"
            "\n"
            "Note: iPhone Mirroring is not available in the EU due to DMA regulations."
        )

    def get_phone_screen_region(self) -> dict:
        """Phone-screen sub-rect in window-relative coords (excludes title bar)."""
        self._ensure_window()
        assert self._bounds is not None
        region = self._detect_phone_screen_region()
        return {
            "x": region.x,
            "y": region.y,
            "width": region.width,
            "height": region.height,
        }

    def phone_screen_to_screen_coords(
        self, px: float, py: float
    ) -> tuple[float, float]:
        """Phone-screen-relative (below title bar, inside bezels) to screen-absolute."""
        region = self._detect_phone_screen_region()
        wx = region.x + px
        wy = region.y + py
        return self.window_to_screen_coords(wx, wy)

    def refresh(self) -> int:
        """Re-query the window server and update cached bounds."""
        return self.find_window()

    def get_retina_scale(self) -> float:
        """Cached main-screen backing scale factor (2.0 on Retina, 1.0 otherwise)."""
        if self._retina_scale is None:
            self._retina_scale = get_backing_scale_factor()
        return self._retina_scale

    @property
    def window_id(self) -> Optional[int]:
        """Cached CGWindowID, or None if :meth:`find_window` not yet called."""
        return self._window_id

    @property
    def bounds(self) -> Optional[WindowBounds]:
        """Cached WindowBounds, or None."""
        return self._bounds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_window(self) -> None:
        if self._window_id is None or self._bounds is None:
            raise MirroringWindowError(
                "iPhone Mirroring window has not been located yet. "
                "Make sure iPhone Mirroring is open and your iPhone is "
                "locked (screen off)."
            )

    def _capture_via_cg(self) -> Optional[Image.Image]:
        """Capture via CoreGraphics, re-acquiring the window if stale."""
        assert self._window_id is not None
        assert self._bounds is not None

        # Verify the cached window ID still exists; re-acquire if stale.
        if not window_id_is_valid(self._window_id):
            logger.warning(
                "Window %d no longer exists, re-acquiring.", self._window_id
            )
            try:
                self.find_window()
            except MirroringWindowError:
                return None

        assert self._window_id is not None
        assert self._bounds is not None
        return capture_via_cg(
            self._window_id,
            self._bounds.x,
            self._bounds.y,
            self._bounds.width,
            self._bounds.height,
        )

    def _detect_phone_screen_region(self) -> PhoneScreenRegion:
        """Heuristic phone-screen rectangle inside the window."""
        assert self._bounds is not None

        x = self._bezel_padding
        y = self._title_bar_height + self._bezel_padding
        width = self._bounds.width - 2 * self._bezel_padding
        height = self._bounds.height - self._title_bar_height - 2 * self._bezel_padding

        # Clamp to non-negative values to guard against pathological bounds.
        width = max(0.0, width)
        height = max(0.0, height)

        return PhoneScreenRegion(x=x, y=y, width=width, height=height)

    def __repr__(self) -> str:
        state = "connected" if self._window_id is not None else "disconnected"
        bounds_str = (
            f"{self._bounds.width}x{self._bounds.height}"
            if self._bounds
            else "unknown"
        )
        return (
            f"<MirroringWindowManager state={state} "
            f"window_id={self._window_id} bounds={bounds_str}>"
        )
