"""The ``ScreenGraph`` dataclass and its lookup helpers.

A ``ScreenGraph`` is the top-level output of the element detector: a flat
list of :class:`~pilot.core.element_detector.ui_element.UIElement` nodes
with parent/child relationships encoded via IDs, plus screen-level metadata
that describes the overall context (app, screen type, nav depth, keyboard
and modal flags, status bar).

The graph is designed to support fast *local* queries that resolve
natural-language element references without a second vision call:

``find_by_text`` / ``find_by_type`` / ``find_by_role`` / ``find_interactable``
    Narrow down candidates by text, classification, semantic role, or
    interactability.

``find_nearest``
    Pixel-proximity search, preferring the smallest containing element.

``find_by_id`` / ``get_root_elements`` / ``get_children``
    Tree navigation helpers.

``to_text_description``
    A compact, indented text form of the entire screen suitable for
    injecting into downstream prompts in place of raw pixels.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from pilot.core.element_detector.ui_element import UIElement


@dataclass
class ScreenGraph:
    """Structured representation of an entire mirrored phone screen.

    This is the pseudo-accessibility tree: a flat list of ``UIElement``
    objects with parent/child relationships encoded via IDs, plus
    screen-level metadata that describes the overall context.

    Attributes
    ----------
    elements : list[UIElement]
        Every element the detector identified.
    screen_type : str
        A token from ``SCREEN_TYPES`` (``home_screen``, ``chat``,
        ``settings``, ``keyboard_visible``, ``dialog``, ...).
    app_name : str | None
        The foreground app, if the detector was able to identify it.
    navigation_depth : int
        Estimated depth in the navigation stack (0 = root/home).
    has_keyboard : bool
        Whether a soft keyboard is currently visible.
    has_modal : bool
        Whether a modal dialog, alert, or sheet is showing.
    status_bar : dict[str, Any] | None
        Parsed status-bar info (time, battery, signal, wifi), if present.
    timestamp : float
        Unix timestamp when the graph was constructed.
    """

    elements: list[UIElement]
    screen_type: str
    app_name: str | None = None
    navigation_depth: int = 0
    has_keyboard: bool = False
    has_modal: bool = False
    status_bar: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Element lookup
    # ------------------------------------------------------------------

    def find_by_text(self, text: str, fuzzy: bool = True) -> list[UIElement]:
        """Find elements whose visible text matches *text*.

        When *fuzzy* is True (the default), elements are returned if the
        query appears as a substring (case-insensitive) or if the fuzzy
        similarity ratio exceeds 0.6. Results are sorted by match quality
        (best first).
        """
        if not text:
            return []

        text_lower = text.lower().strip()
        scored: list[tuple[float, UIElement]] = []

        for el in self.elements:
            if el.text is None:
                continue

            el_text = el.text.lower().strip()

            # Exact match (case-insensitive)
            if el_text == text_lower:
                scored.append((1.0, el))
                continue

            if fuzzy:
                # Substring containment
                if text_lower in el_text or el_text in text_lower:
                    overlap = min(len(text_lower), len(el_text)) / max(
                        len(text_lower), len(el_text), 1
                    )
                    scored.append((0.7 + 0.2 * overlap, el))
                    continue

                # Fuzzy similarity
                ratio = SequenceMatcher(None, text_lower, el_text).ratio()
                if ratio >= 0.6:
                    scored.append((ratio, el))
            else:
                # Strict substring match only
                if text_lower in el_text:
                    scored.append((0.8, el))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [el for _, el in scored]

    def find_by_type(self, element_type: str) -> list[UIElement]:
        """Return every element whose classified type matches *element_type*."""
        return [el for el in self.elements if el.element_type == element_type]

    def find_by_role(self, role: str) -> list[UIElement]:
        """Return every element whose semantic role matches *role*."""
        return [el for el in self.elements if el.semantic_role == role]

    def find_interactable(self) -> list[UIElement]:
        """Return every element that can be tapped or typed into."""
        return [el for el in self.elements if el.interactable]

    def find_nearest(self, x: int, y: int) -> UIElement | None:
        """Return the element whose centre is closest to ``(x, y)``.

        Prefers elements that contain the point; among those, prefers the
        smallest (most specific) one. Falls back to pure centre-distance
        when no element covers the point.
        """
        if not self.elements:
            return None

        containing = [el for el in self.elements if el.contains_point(x, y)]
        if containing:
            containing.sort(key=lambda el: el.area)
            return containing[0]

        return min(self.elements, key=lambda el: el.distance_to_point(x, y))

    def find_by_id(self, element_id: str) -> UIElement | None:
        """Look up an element by its unique ID."""
        for el in self.elements:
            if el.id == element_id:
                return el
        return None

    def get_root_elements(self) -> list[UIElement]:
        """Return elements that have no parent (top-level containers)."""
        return [el for el in self.elements if el.parent_id is None]

    def get_children(self, parent_id: str) -> list[UIElement]:
        """Return the direct children of the element with *parent_id*."""
        return [el for el in self.elements if el.parent_id == parent_id]

    # ------------------------------------------------------------------
    # Text serialisation
    # ------------------------------------------------------------------

    def to_text_description(self) -> str:
        """Convert the graph to a compact, human-readable text format.

        The output is designed to be injected into downstream prompts as a
        replacement for (or supplement to) raw screenshots. It is far
        cheaper in tokens than an image while preserving the structural
        information needed to reason about available actions.

        Example output::

            Screen: Messages (chat, depth=2, keyboard=true)
            Elements:
            [nav_bar#nav_0] "John Doe" (enabled) @(200,30,300x44)
              [button#btn_back] "< Back" role=back_button (enabled, interactable) @(20,30,60x44)
              [button#btn_video] role=more_options (enabled, interactable) @(370,30,40x44)
            [scroll_view#list_0] @(0,74,400x600)
              [cell#cell_0] "Hey, are you free tonight?" (enabled) @(20,100,360x60)
              [cell#cell_1] "Sure! What time?" (enabled) @(20,170,360x60)
            [text_field#input_0] role=message_input (focused, interactable) @(100,700,300x44)
            [keyboard#kb_0] @(0,760,400x264)
        """
        parts: list[str] = []

        # Header line
        kb = "keyboard=true" if self.has_keyboard else "keyboard=false"
        modal = ", modal=true" if self.has_modal else ""
        parts.append(
            f"Screen: {self.app_name or 'Unknown'} "
            f"({self.screen_type}, depth={self.navigation_depth}, {kb}{modal})"
        )

        if self.status_bar:
            sb_items = ", ".join(f"{k}={v}" for k, v in self.status_bar.items())
            parts.append(f"Status bar: {sb_items}")

        parts.append("Elements:")

        # Build a parent -> children index
        children_of: dict[str | None, list[UIElement]] = {}
        for el in self.elements:
            children_of.setdefault(el.parent_id, []).append(el)

        def _render_element(el: UIElement, indent: int = 0) -> None:
            prefix = "  " * indent
            line = f"{prefix}[{el.element_type}#{el.id}]"

            if el.text:
                text_display = (
                    el.text if len(el.text) <= 50 else el.text[:47] + "..."
                )
                line += f' "{text_display}"'

            if el.semantic_role:
                line += f" role={el.semantic_role}"

            state_parts: list[str] = []
            if el.state:
                state_parts.append(el.state)
            if el.interactable:
                state_parts.append("interactable")
            if state_parts:
                line += f" ({', '.join(state_parts)})"

            cx, cy = el.center
            bw = el.bounds.get("width", 0)
            bh = el.bounds.get("height", 0)
            line += f" @({cx},{cy},{bw}x{bh})"

            parts.append(line)

            for child in children_of.get(el.id, []):
                _render_element(child, indent + 1)

        # Render from roots
        roots = children_of.get(None, [])
        for root_el in roots:
            _render_element(root_el)

        # Any orphaned elements (parent_id set but parent not in graph)
        reachable: set[str] = set()

        def _collect_reachable(eid: str) -> None:
            reachable.add(eid)
            for child in children_of.get(eid, []):
                _collect_reachable(child.id)

        for root_el in roots:
            _collect_reachable(root_el.id)

        for orph in self.elements:
            if orph.id not in reachable:
                _render_element(orph, indent=0)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Dict serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the entire graph to a JSON-compatible dictionary."""
        return {
            "screen_type": self.screen_type,
            "app_name": self.app_name,
            "navigation_depth": self.navigation_depth,
            "has_keyboard": self.has_keyboard,
            "has_modal": self.has_modal,
            "status_bar": self.status_bar,
            "timestamp": self.timestamp,
            "elements": [el.to_dict() for el in self.elements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenGraph:
        """Reconstruct a ``ScreenGraph`` from the dict produced by :meth:`to_dict`."""
        elements = [UIElement.from_dict(e) for e in data.get("elements", [])]
        return cls(
            elements=elements,
            screen_type=data.get("screen_type", "unknown"),
            app_name=data.get("app_name"),
            navigation_depth=data.get("navigation_depth", 0),
            has_keyboard=data.get("has_keyboard", False),
            has_modal=data.get("has_modal", False),
            status_bar=data.get("status_bar"),
            timestamp=data.get("timestamp", time.time()),
        )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<ScreenGraph app={self.app_name!r} type={self.screen_type} "
            f"elements={len(self.elements)} depth={self.navigation_depth} "
            f"keyboard={self.has_keyboard} modal={self.has_modal}>"
        )


__all__ = ["ScreenGraph"]
