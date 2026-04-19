"""Internal helpers for window_capture.

Split out of window_capture.py to keep that file within the 400-line cap.
All functions are behavior-preserving copies of the originals.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import Quartz
from PIL import Image
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGNullWindowID,
    kCGWindowListOptionAll,
    kCGWindowListOptionIncludingWindow,
)

logger = logging.getLogger("pilotd.window")


def find_mirroring_window_info(owner_name: str, window_name: str) -> Optional[dict]:
    """Return the first matching window-info dict, or None.

    Matches on ``kCGWindowOwnerName == owner_name`` and layer ``0``; prefers
    an exact window-name match but accepts owner-only matches as a fallback.
    Skips off-screen (e.g. minimized) windows.
    """
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionAll, kCGNullWindowID
    )
    if window_list is None:
        logger.debug("CGWindowListCopyWindowInfo returned None.")
        return None

    for win in window_list:
        owner = win.get("kCGWindowOwnerName", "")
        name = win.get("kCGWindowName", "")
        layer = win.get("kCGWindowLayer", -1)

        if not win.get("kCGWindowIsOnscreen", False):
            continue

        if owner == owner_name and layer == 0:
            if name == window_name or not name:
                logger.debug(
                    "Matched window: owner=%r name=%r id=%s",
                    owner,
                    name,
                    win.get("kCGWindowNumber"),
                )
                return dict(win)

    return None


def window_id_is_valid(window_id: Optional[int]) -> bool:
    """Check whether the given window ID still exists in the window list."""
    if window_id is None:
        return False
    check = CGWindowListCopyWindowInfo(
        kCGWindowListOptionIncludingWindow, window_id
    )
    return check is not None and len(check) > 0


def capture_via_cg(
    window_id: int,
    bounds_x: float,
    bounds_y: float,
    bounds_width: float,
    bounds_height: float,
) -> Optional[Image.Image]:
    """Capture the given window via CoreGraphics.

    Returns a PIL Image, or None on any failure. Does not attempt recovery
    or fallback; the caller handles those.
    """
    cg_rect = Quartz.CGRectMake(bounds_x, bounds_y, bounds_width, bounds_height)

    cg_image = Quartz.CGWindowListCreateImage(
        cg_rect,
        kCGWindowListOptionIncludingWindow,
        window_id,
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )

    if cg_image is None:
        logger.debug("CGWindowListCreateImage returned None.")
        return None

    width = Quartz.CGImageGetWidth(cg_image)
    height = Quartz.CGImageGetHeight(cg_image)

    if width == 0 or height == 0:
        logger.debug("CGImage has zero dimensions (%dx%d).", width, height)
        return None

    # Extract raw pixel data directly, bypassing the expensive PNG
    # encode/decode round-trip via NSBitmapImageRep.
    data_provider = Quartz.CGImageGetDataProvider(cg_image)
    raw_data = Quartz.CGDataProviderCopyData(data_provider)

    if raw_data is None:
        logger.debug("CGDataProviderCopyData returned None.")
        return None

    bytes_per_row = Quartz.CGImageGetBytesPerRow(cg_image)

    # CGImage on macOS is typically BGRA with premultiplied alpha.
    pil_image = Image.frombuffer(
        "RGBA", (width, height), raw_data, "raw", "BGRA", bytes_per_row, 1
    )
    # .copy() detaches from the CoreFoundation buffer so it can be released.
    pil_image = pil_image.copy()
    logger.debug("Captured %dx%d image via CoreGraphics.", width, height)
    return pil_image


def capture_via_screencapture(window_id: int, error_cls: type) -> Image.Image:
    """Fallback capture via the macOS ``screencapture`` CLI.

    Raises *error_cls* (the caller's ``MirroringWindowError``) on failure so
    callers retain their exception hierarchy.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "screencapture",
                "-l",
                str(window_id),
                "-o",  # No shadow.
                "-x",  # No sound.
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            stderr_msg = result.stderr.strip()
            raise error_cls(
                f"screencapture failed (exit code {result.returncode})"
                f"{': ' + stderr_msg if stderr_msg else ''}. "
                "This may be a Screen Recording permission issue. "
                "Go to System Settings > Privacy & Security > Screen Recording "
                "and enable your terminal app, then restart it."
            )

        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise error_cls(
                "screencapture produced an empty file. The iPhone Mirroring "
                "window may have been minimized or closed during capture. "
                "Make sure the window is visible and your iPhone is locked."
            )

        try:
            image = Image.open(tmp_path)
            image.load()
        except Exception as exc:
            raise error_cls(
                f"Failed to decode screencapture output: {exc}"
            ) from exc

        logger.debug(
            "Captured %dx%d image via screencapture.", image.width, image.height
        )
        return image
    except subprocess.TimeoutExpired as exc:
        raise error_cls(
            "screencapture timed out after 10 seconds. Your system may be "
            "under heavy load, or a macOS dialog may be blocking the capture. "
            "Try again, and if the problem persists, restart iPhone Mirroring."
        ) from exc
    except Exception:
        raise
    finally:
        tmp_path.unlink(missing_ok=True)


def get_backing_scale_factor() -> float:
    """Query the main-screen backing scale factor; default to 2.0 on failure."""
    try:
        from AppKit import NSScreen

        main_screen = NSScreen.mainScreen()
        if main_screen is not None:
            return float(main_screen.backingScaleFactor())
        logger.warning(
            "NSScreen.mainScreen() returned None; defaulting scale to 2.0."
        )
        return 2.0
    except Exception:
        logger.warning(
            "Failed to query backingScaleFactor; defaulting scale to 2.0.",
            exc_info=True,
        )
        return 2.0
