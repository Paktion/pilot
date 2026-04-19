"""
Shared utilities for the Pilot daemon — system checks, image processing,
coordinate math, timing/retry helpers.

Split into submodules so no individual file crosses the 400-line soft cap.
"""

from pilot.core.utils.coords import clamp_coords, scale_coords
from pilot.core.utils.images import (
    compare_images,
    image_to_base64,
    resize_for_api,
    save_debug_screenshot,
)
from pilot.core.utils.logs import setup_logging
from pilot.core.utils.sys_checks import (
    check_accessibility_permission,
    check_api_key,
    check_dependencies,
    check_disk_space,
    check_iphone_mirroring_available,
    check_iphone_mirroring_window,
    check_macos_version,
    check_screen_recording_permission,
    run_system_check,
)
from pilot.core.utils.timing import adaptive_wait, retry

__all__ = [
    "adaptive_wait",
    "check_accessibility_permission",
    "check_api_key",
    "check_dependencies",
    "check_disk_space",
    "check_iphone_mirroring_available",
    "check_iphone_mirroring_window",
    "check_macos_version",
    "check_screen_recording_permission",
    "clamp_coords",
    "compare_images",
    "image_to_base64",
    "resize_for_api",
    "retry",
    "run_system_check",
    "save_debug_screenshot",
    "scale_coords",
    "setup_logging",
]
