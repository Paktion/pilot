"""Coordinate-math helpers."""

from __future__ import annotations


def clamp_coords(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    """Clamp (x, y) into ``[0, width-1] × [0, height-1]``."""
    return (max(0, min(x, width - 1)), max(0, min(y, height - 1)))


def scale_coords(
    x: int,
    y: int,
    from_size: tuple[int, int],
    to_size: tuple[int, int],
) -> tuple[int, int]:
    from_w, from_h = from_size
    to_w, to_h = to_size
    if from_w == 0 or from_h == 0:
        return (0, 0)
    return (round(x * to_w / from_w), round(y * to_h / from_h))
