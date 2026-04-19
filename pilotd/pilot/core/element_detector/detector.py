"""The ``ElementDetector`` that builds a :class:`ScreenGraph` from a screenshot.

The detector wraps a vision agent and issues a single structured call to
construct the full pseudo-accessibility tree for the current screen.
Results are cached in an LRU keyed on a perceptual (average) hash of the
screenshot; visually similar frames reuse the same graph without incurring
another vision call. Cache size defaults to 8 entries.

Prompt text, bounds plausibility checks, and per-element parsing live in
:mod:`pilot.core.element_detector.parsing`; the LRU cache and perceptual
image hashing live in :mod:`pilot.core.element_detector.cache`. This
module is responsible for orchestration only.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from PIL import Image as PILImage

from pilot.core.element_detector.cache import (
    DEFAULT_CACHE_SIZE,
    LRUCache,
    hash_image,
)
from pilot.core.element_detector.parsing import (
    DETECTION_PROMPT,
    DETECTION_SYSTEM_PROMPT,
    parse_single_element,
)
from pilot.core.element_detector.screen_graph import ScreenGraph
from pilot.core.element_detector.ui_element import UIElement
from pilot.core.element_detector.vocab import SCREEN_TYPES

if TYPE_CHECKING:
    # Forward reference: the vision agent module isn't ported yet. The
    # concrete class will live at ``pilot.core.vision`` once in place.
    from pilot.core.vision import VisionAgent

logger = logging.getLogger("pilotd.elements")


# ---------------------------------------------------------------------------
# ElementDetector
# ---------------------------------------------------------------------------

class ElementDetector:
    """Build a :class:`ScreenGraph` from a screenshot via a single vision call.

    The detector wraps a vision agent and sends a carefully crafted prompt
    that asks the model to enumerate every visible UI element. The
    response is parsed, validated, and normalised into a ``ScreenGraph``.

    An LRU cache (default capacity 8) keyed on a perceptual image hash
    makes repeated calls on visually similar frames free. Cache entries
    expire after ``cache_ttl`` seconds.

    Parameters
    ----------
    vision_agent : VisionAgent
        An initialised vision agent. The detector reuses the agent's
        underlying client and retry logic without going through the
        agent's action-parsing pipeline.
    cache_ttl : float
        How long (in seconds) a cached detection is considered valid.
        Set to 0 to disable caching entirely.
    max_elements : int
        Safety cap on elements parsed per response; prevents runaway
        token consumption if the model hallucinates an enormous list.
    cache_max_size : int
        Maximum entries in the LRU detection cache.
    hash_threshold : int
        Maximum Hamming distance for perceptual-hash similarity matches.
        Lower values require closer visual matches.
    """

    def __init__(
        self,
        vision_agent: "VisionAgent",
        cache_ttl: float = 2.0,
        max_elements: int = 200,
        cache_max_size: int = DEFAULT_CACHE_SIZE,
        hash_threshold: int = 5,
    ) -> None:
        self._agent = vision_agent
        self._cache_ttl = cache_ttl
        self._max_elements = max_elements
        self._hash_threshold = hash_threshold
        self._cache = LRUCache(max_size=cache_max_size)

        logger.info(
            "ElementDetector initialised (cache_ttl=%.1fs, max_elements=%d, "
            "cache_size=%d, hash_threshold=%d)",
            cache_ttl,
            max_elements,
            cache_max_size,
            hash_threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_elements(self, screenshot: PILImage.Image) -> ScreenGraph:
        """Analyse *screenshot* and return a :class:`ScreenGraph`.

        1. Hashes the screenshot and checks the cache.
        2. On hit, returns immediately (zero cost).
        3. Otherwise issues a single vision call with the detection prompt.
        4. Parses and validates the response into a ``ScreenGraph``.
        5. Inserts the result into the cache.
        """
        img_hash = hash_image(screenshot)

        cached = self._cache.get_by_similarity(
            img_hash, self._cache_ttl, self._hash_threshold
        )
        if cached is not None:
            logger.debug("Element detection cache hit (perceptual)")
            return cached

        logger.info(
            "Running element detection on %dx%d screenshot",
            *screenshot.size,
        )
        t0 = time.monotonic()

        prompt = self._build_detection_prompt(screenshot.size)
        raw_response = self._call_vision_llm(prompt, screenshot)
        graph = self._parse_detection_response(raw_response, screenshot.size)

        elapsed = time.monotonic() - t0
        logger.info(
            "Element detection complete: %d elements, screen_type=%s, "
            "app=%s (%.2fs)",
            len(graph.elements),
            graph.screen_type,
            graph.app_name,
            elapsed,
        )

        self._cache.put(img_hash, graph)
        return graph

    def invalidate_cache(self) -> None:
        """Clear the detection cache, forcing the next call to hit the model."""
        self._cache.clear()
        logger.debug("Element detection cache invalidated")

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_detection_prompt(self, screenshot_size: tuple[int, int]) -> str:
        width, height = screenshot_size
        return DETECTION_PROMPT.format(width=width, height=height)

    # ------------------------------------------------------------------
    # Vision call
    # ------------------------------------------------------------------

    def _call_vision_llm(
        self,
        prompt: str,
        screenshot: PILImage.Image,
    ) -> str:
        """Send *prompt* plus *screenshot* through the wrapped vision agent.

        Reuses the agent's underlying client, retry logic, and image
        encoder without going through the agent's action parser.
        """
        image_data = self._agent._encode_image(screenshot)

        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_data,
                },
            },
        ]
        messages = [{"role": "user", "content": content}]
        return self._agent._call_api(DETECTION_SYSTEM_PROMPT, messages)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_detection_response(
        self,
        response_text: str,
        screenshot_size: tuple[int, int],
    ) -> ScreenGraph:
        """Parse the model's JSON response into a validated :class:`ScreenGraph`."""
        data = _extract_json_object(response_text)

        screen_type = _normalise_screen_type(
            str(data.get("screen_type", "unknown")).lower()
        )

        app_name = data.get("app_name")
        if app_name is not None:
            app_name = str(app_name).strip() or None

        try:
            nav_depth = int(data.get("navigation_depth", 0))
        except (TypeError, ValueError):
            nav_depth = 0

        has_keyboard = bool(data.get("has_keyboard", False))
        has_modal = bool(data.get("has_modal", False))
        status_bar = data.get("status_bar")
        if status_bar is not None and not isinstance(status_bar, dict):
            status_bar = None

        raw_elements = data.get("elements", [])
        if not isinstance(raw_elements, list):
            raw_elements = []

        if len(raw_elements) > self._max_elements:
            logger.warning(
                "Model returned %d elements, capping at %d",
                len(raw_elements),
                self._max_elements,
            )
            raw_elements = raw_elements[: self._max_elements]

        width, height = screenshot_size
        seen_ids: set[str] = set()
        elements: list[UIElement] = []

        for i, raw in enumerate(raw_elements):
            if not isinstance(raw, dict):
                continue
            el = parse_single_element(raw, i, width, height, seen_ids)
            if el is not None:
                elements.append(el)
                seen_ids.add(el.id)

        _rewire_parent_child(elements)

        return ScreenGraph(
            elements=elements,
            screen_type=screen_type,
            app_name=app_name,
            navigation_depth=nav_depth,
            has_keyboard=has_keyboard,
            has_modal=has_modal,
            status_bar=status_bar,
        )


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

def _extract_json_object(response_text: str) -> dict[str, Any]:
    """Strip fences from *response_text* and parse the enclosed JSON object."""
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group()
        else:
            raise ValueError(
                "No JSON object found in detection response. "
                f"Raw text:\n{response_text[:500]}"
            )

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse detection response as JSON: {exc}\n"
            f"Raw text:\n{response_text[:500]}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    return data


def _normalise_screen_type(screen_type: str) -> str:
    if screen_type in SCREEN_TYPES:
        return screen_type
    for known in SCREEN_TYPES:
        if known in screen_type or screen_type in known:
            return known
    logger.warning(
        "Unknown screen_type %r, defaulting to 'unknown'", screen_type
    )
    return "unknown"


def _rewire_parent_child(elements: list[UIElement]) -> None:
    """Clear orphaned parent IDs and rebuild each element's children list."""
    element_ids = {el.id for el in elements}
    for el in elements:
        if el.parent_id is not None and el.parent_id not in element_ids:
            el.parent_id = None
        el.children = []
    for el in elements:
        if el.parent_id is not None:
            parent = next(
                (p for p in elements if p.id == el.parent_id),
                None,
            )
            if parent is not None and el.id not in parent.children:
                parent.children.append(el.id)


__all__ = ["ElementDetector"]
