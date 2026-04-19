"""Pseudo-accessibility tree construction for mirrored phone screens.

This package builds a typed, structured description of every visible UI
element on the current screen via a single vision call. The resulting
``ScreenGraph`` supports fast local queries -- lookup by text, type,
semantic role, interactability, or pixel proximity -- without further
model calls.

Two ergonomic helpers sit alongside the detector:

* :func:`render_som_overlay` draws numbered, colour-coded badges on each
  interactable element (the Set-of-Mark technique); pairing the
  annotated image with :func:`to_compact_string` gives downstream models
  a grounded index into the screen's structure.

* :func:`to_compact_string` produces a numbered listing whose indices
  line up 1-to-1 with the badges, suitable for injecting into prompts
  as a cheap, token-efficient substitute for raw pixels.

Public surface:

* :class:`UIElement` -- a single element node.
* :class:`ScreenGraph` -- the full tree plus screen metadata.
* :class:`ElementDetector` -- the engine that builds the graph from a
  screenshot, with an LRU cache keyed on a perceptual image hash.
* :func:`render_som_overlay`, :func:`to_compact_string` -- badge
  rendering and compact serialisation.
"""

from __future__ import annotations

from pilot.core.element_detector.detector import ElementDetector
from pilot.core.element_detector.screen_graph import ScreenGraph
from pilot.core.element_detector.som_overlay import (
    render_som_overlay,
    to_compact_string,
)
from pilot.core.element_detector.ui_element import UIElement

__all__ = [
    "ElementDetector",
    "ScreenGraph",
    "UIElement",
    "render_som_overlay",
    "to_compact_string",
]
