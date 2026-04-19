"""The ``UIElement`` dataclass and its geometry helpers.

A ``UIElement`` is a single typed node in the pseudo-accessibility tree the
detector builds from a screenshot. Each element carries:

* A stable ``id`` (unique within a ``ScreenGraph``).
* A classified ``element_type`` drawn from the vocabulary in
  :mod:`pilot.core.element_detector.vocab`.
* An optional visible ``text`` payload.
* A screenshot-pixel ``bounds`` rectangle and a precomputed ``center`` point.
* Flags describing interactability, state, and semantic role.
* Parent/child pointers that encode the tree's structure via IDs.

The class also exposes a few small geometry helpers (``contains_point``,
``distance_to``, ``overlaps``, ``area``) so downstream callers can write
local queries without a separate geometry library.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UIElement:
    """A detected UI element on a mirrored phone screen.

    Each element has a unique ID, a classified type, optional visible text,
    a bounding box in screenshot pixel coordinates, and metadata about its
    state and its position in the element hierarchy.

    The ``bounds`` dict uses the format
    ``{"x": int, "y": int, "width": int, "height": int}`` where ``(x, y)`` is
    the top-left corner in screenshot pixel coordinates.

    Attributes
    ----------
    id : str
        A short identifier, unique within its ``ScreenGraph``.
    element_type : str
        A token from ``ELEMENT_TYPES`` (button, text_field, label, ...).
    text : str | None
        The visible text content, or ``None`` for icon-only elements.
    bounds : dict[str, int]
        Top-left corner and dimensions in screenshot pixels.
    center : tuple[int, int]
        Precomputed centre of the bounding box (used as a tap target).
    confidence : float
        Detector's confidence in this element (0-1).
    interactable : bool
        True if the element accepts taps, typing, toggles, or the like.
    state : str | None
        One of ``"enabled"``, ``"disabled"``, ``"selected"``, ``"checked"``,
        ``"unchecked"``, ``"focused"``, or ``None``.
    parent_id : str | None
        ID of the element that visually contains this one, or ``None`` for
        top-level elements.
    children : list[str]
        IDs of direct children; kept in sync with ``parent_id``.
    semantic_role : str | None
        Functional classification from ``SEMANTIC_ROLES`` (e.g.
        ``back_button``, ``send_button``) if applicable.
    """

    id: str
    element_type: str
    text: str | None
    bounds: dict[str, int]
    center: tuple[int, int]
    confidence: float
    interactable: bool
    state: str | None = None
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)
    semantic_role: str | None = None

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def contains_point(self, x: int, y: int) -> bool:
        """Return True if the point ``(x, y)`` falls within this element's bounds."""
        bx = self.bounds.get("x", 0)
        by = self.bounds.get("y", 0)
        bw = self.bounds.get("width", 0)
        bh = self.bounds.get("height", 0)
        return bx <= x <= bx + bw and by <= y <= by + bh

    def distance_to(self, other: UIElement) -> float:
        """Return the Euclidean distance between this element's centre and *other*'s."""
        dx = self.center[0] - other.center[0]
        dy = self.center[1] - other.center[1]
        return math.sqrt(dx * dx + dy * dy)

    def distance_to_point(self, x: int, y: int) -> float:
        """Return the Euclidean distance from this element's centre to ``(x, y)``."""
        dx = self.center[0] - x
        dy = self.center[1] - y
        return math.sqrt(dx * dx + dy * dy)

    @property
    def area(self) -> int:
        """Return the bounding-box area in square pixels."""
        return self.bounds.get("width", 0) * self.bounds.get("height", 0)

    def overlaps(self, other: UIElement) -> bool:
        """Return True if this element's bounding box overlaps *other*'s."""
        ax = self.bounds["x"]
        ay = self.bounds["y"]
        aw = self.bounds["width"]
        ah = self.bounds["height"]
        bx = other.bounds["x"]
        by = other.bounds["y"]
        bw = other.bounds["width"]
        bh = other.bounds["height"]
        return not (
            ax + aw <= bx
            or bx + bw <= ax
            or ay + ah <= by
            or by + bh <= ay
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the element to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "element_type": self.element_type,
            "text": self.text,
            "bounds": self.bounds,
            "center": list(self.center),
            "confidence": self.confidence,
            "interactable": self.interactable,
            "state": self.state,
            "parent_id": self.parent_id,
            "children": self.children,
            "semantic_role": self.semantic_role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UIElement:
        """Reconstruct a ``UIElement`` from the dict produced by :meth:`to_dict`."""
        center_seq = data.get("center", (0, 0))
        center: tuple[int, int] = (int(center_seq[0]), int(center_seq[1]))
        return cls(
            id=str(data["id"]),
            element_type=str(data["element_type"]),
            text=data.get("text"),
            bounds=dict(data["bounds"]),
            center=center,
            confidence=float(data.get("confidence", 1.0)),
            interactable=bool(data.get("interactable", False)),
            state=data.get("state"),
            parent_id=data.get("parent_id"),
            children=list(data.get("children", [])),
            semantic_role=data.get("semantic_role"),
        )

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover - trivial
        text_preview = ""
        if self.text:
            display = self.text if len(self.text) <= 30 else self.text[:27] + "..."
            text_preview = f' "{display}"'
        role = f" role={self.semantic_role}" if self.semantic_role else ""
        return (
            f"<UIElement {self.id} type={self.element_type}{text_preview}"
            f" center={self.center}{role}>"
        )


__all__ = ["UIElement"]
