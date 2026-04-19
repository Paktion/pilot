"""Image helpers — resize for Claude API, base64, perceptual diff."""

from __future__ import annotations

import base64
import io
import os
from datetime import datetime

import PIL.Image


def resize_for_api(image: PIL.Image.Image, max_size: int = 1568) -> PIL.Image.Image:
    """Resize to longest-side ``max_size``, preserving aspect.

    1568 is Anthropic's internal rescale ceiling — resizing client-side saves
    bandwidth without losing information.
    """
    width, height = image.size
    if width <= max_size and height <= max_size:
        return image.copy()
    scale = max_size / width if width >= height else max_size / height
    return image.resize(
        (int(width * scale), int(height * scale)), PIL.Image.LANCZOS
    )


def image_to_base64(image: PIL.Image.Image, format: str = "PNG") -> str:
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def compare_images(
    img1: PIL.Image.Image,
    img2: PIL.Image.Image,
    threshold: float = 0.95,
    pixel_tolerance: int = 5,
) -> bool:
    """Pixel-level similarity with tolerance.

    Numpy-backed for speed on screenshot-sized images. Returns True when the
    fraction of matching pixels meets or exceeds ``threshold``.
    """
    import numpy as np

    if img1.size != img2.size:
        img2 = img2.resize(img1.size, PIL.Image.LANCZOS)
    if img1.mode != img2.mode:
        img2 = img2.convert(img1.mode)

    arr1 = np.asarray(img1, dtype=np.int16)
    arr2 = np.asarray(img2, dtype=np.int16)
    if arr1.size == 0:
        return True

    if arr1.ndim == 3:
        pixel_match = np.all(np.abs(arr1 - arr2) <= pixel_tolerance, axis=-1)
    else:
        pixel_match = np.abs(arr1 - arr2) <= pixel_tolerance
    return float(np.mean(pixel_match)) >= threshold


def save_debug_screenshot(
    image: PIL.Image.Image, step: int, directory: str | None = None
) -> str:
    if directory is None:
        directory = os.path.join(os.getcwd(), "debug_screenshots")
    os.makedirs(directory, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(directory, f"step_{step:04d}_{ts}.png")
    image.save(path, "PNG")
    return path
