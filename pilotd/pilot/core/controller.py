"""
AgentController — bridges the workflow engine's ``Controller`` protocol to
the live perception-action stack (window capture + input simulator + vision).

Intelligence upgrades over the v0 bridge:

* ``wait_for`` and ``tap_text`` accept a keyword list (``str`` or ``list[str]``).
  The vision prompt invites the LLM to match ANY of the keywords or a close
  synonym — "Dining" also accepts "Meal Swipes" or "Cafeteria".
* If the target isn't visible, ``wait_for`` tells the LLM to return a
  ``WaitAction`` as a signal to scroll; the controller then swipes up and
  retries. Capped by ``max_scrolls``.
* Learned scroll counts per (app, keyword) are persisted via the injectable
  ``save_hint`` callback and pre-applied on the next run via ``lookup_hint``.
  The controller emits a ``learned`` event so the UI can render the discovery.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

from PIL import Image

from pilot.core.input_simulator import InputSimulator
from pilot.core.vision import ClickAction, DoneAction, VisionAgent, WaitAction
from pilot.core.window_capture import MirroringWindowManager

log = logging.getLogger("pilotd.controller")


_FIND_PROMPT = (
    "Find the element that best matches ANY of these target labels or a close "
    "synonym: {labels}.\n\n"
    "- If CLEARLY VISIBLE on screen, return ClickAction with the center coords.\n"
    "- If NOT visible but the screen looks scrollable (more content below the "
    "fold), return WaitAction(seconds=0.5) as a signal to scroll and retry.\n"
    "- If NOT visible and the screen is not scrollable, return DoneAction with "
    "summary='NOT_VISIBLE'.\n\n"
    "Prefer close-match synonyms over an imperfect coordinate. Example: if the "
    "target is 'Dining' and you see 'Meal Swipes' or 'Dining Hall', click it."
)


class AgentController:
    """Live controller that drives a real iPhone via the reference primitives."""

    def __init__(
        self,
        *,
        vision: VisionAgent,
        inputs: InputSimulator,
        window: MirroringWindowManager,
        on_screenshot: Callable[[Image.Image, dict[str, Any]], None] | None = None,
        lookup_hint: Callable[[str], dict | None] | None = None,
        save_hint: Callable[[str, int], None] | None = None,
    ) -> None:
        self._vision = vision
        self._inputs = inputs
        self._window = window
        self._on_screenshot = on_screenshot or (lambda *_: None)
        self._lookup_hint = lookup_hint
        self._save_hint = save_hint

    # ---- perception --------------------------------------------------------

    def _current_screenshot(self) -> Image.Image:
        return self._window.capture_screenshot()

    @staticmethod
    def _normalize_keywords(labels: str | list[str]) -> list[str]:
        if isinstance(labels, str):
            return [labels]
        return [str(x) for x in labels if str(x).strip()]

    @staticmethod
    def _format_labels(keywords: list[str]) -> str:
        return ", ".join(f"{k!r}" for k in keywords)

    @staticmethod
    def _hint_key(keywords: list[str]) -> str:
        # First keyword is canonical — saved hint uses it as the key so
        # lookup next run matches the same primary target.
        return keywords[0]

    # ---- control -----------------------------------------------------------

    def launch(self, app: str) -> None:
        self._inputs.open_app(app)
        time.sleep(1.2)

    def wait_for(
        self,
        text: str | list[str],
        timeout_s: float = 20.0,
        max_scrolls: int = 4,
    ) -> bool:
        """Poll until any of ``text`` (keyword(s)) is visible, scrolling if needed.

        Applies a previously-learned pre-scroll from memory. Saves new
        discoveries via ``save_hint`` so later runs skip the learning cost.
        """
        keywords = self._normalize_keywords(text)
        if not keywords:
            return False
        canonical = self._hint_key(keywords)

        # 1. Apply learned pre-scroll so the happy path is fast.
        hint = self._lookup_hint(canonical) if self._lookup_hint else None
        pre_scrolls = int((hint or {}).get("scrolls", 0))
        pre_scrolls = max(0, min(pre_scrolls, max_scrolls))
        for _ in range(pre_scrolls):
            self._try_swipe("up")
            time.sleep(0.4)

        # 2. Poll + scroll until found or timeout.
        deadline = time.monotonic() + timeout_s
        polls_since_scroll = 0
        scrolls_applied = pre_scrolls
        vision_errors = 0
        task_prompt = _FIND_PROMPT.format(labels=self._format_labels(keywords))

        while time.monotonic() < deadline:
            try:
                ss = self._current_screenshot()
                self._on_screenshot(ss, {
                    "kind": "wait_for",
                    "keywords": keywords,
                    "scrolls": scrolls_applied,
                })
                response = self._vision.analyze_screen(ss, task=task_prompt)
            except Exception as exc:
                vision_errors += 1
                if vision_errors >= 3:
                    log.warning(
                        "wait_for %s: %d vision errors, bailing", keywords, vision_errors,
                    )
                    return False
                time.sleep(1.0)
                continue

            vision_errors = 0

            if isinstance(response.action, ClickAction):
                # Found. Record if this was a learning moment.
                if self._save_hint is not None and scrolls_applied != pre_scrolls:
                    try:
                        self._save_hint(canonical, scrolls_applied)
                    except Exception:
                        log.exception("save_hint failed")
                return True

            # LLM signaled "not visible but scrollable" via WaitAction.
            if isinstance(response.action, WaitAction):
                if scrolls_applied < max_scrolls:
                    self._try_swipe("up")
                    scrolls_applied += 1
                    polls_since_scroll = 0
                    time.sleep(0.6)
                    continue

            # DoneAction(NOT_VISIBLE) or we've exhausted scrolls.
            if isinstance(response.action, DoneAction):
                # Still try one opportunistic scroll if we haven't maxed out.
                if scrolls_applied < max_scrolls:
                    self._try_swipe("up")
                    scrolls_applied += 1
                    polls_since_scroll = 0
                    time.sleep(0.6)
                    continue
                return False

            polls_since_scroll += 1
            time.sleep(0.8)

        return False

    def _try_swipe(self, direction: str) -> None:
        """Swipe without letting a geometry error abort the whole wait loop."""
        try:
            self.swipe(direction)
        except Exception as exc:
            log.debug("swipe %s failed: %s", direction, exc)

    def tap_text(
        self,
        text: str | list[str],
        prefer: str | None = None,
        max_scrolls: int = 2,
    ) -> None:
        """Find ``text`` (keyword(s)) on screen and tap it.

        If not visible, scroll up to ``max_scrolls`` times before failing.
        """
        keywords = self._normalize_keywords(text)
        if not keywords:
            raise RuntimeError("tap_text: empty keyword list")
        canonical = self._hint_key(keywords)
        task_prompt = _FIND_PROMPT.format(labels=self._format_labels(keywords))

        scrolls = 0
        while True:
            ss = self._current_screenshot()
            self._on_screenshot(ss, {
                "kind": "tap",
                "keywords": keywords,
                "prefer": prefer,
                "scrolls": scrolls,
            })
            response = self._vision.analyze_screen(ss, task=task_prompt)
            action = response.action

            if isinstance(action, ClickAction):
                self._inputs.click(action.x, action.y)
                if self._save_hint is not None and scrolls > 0:
                    try:
                        self._save_hint(canonical, scrolls)
                    except Exception:
                        log.exception("save_hint failed")
                return

            # WaitAction or DoneAction: not visible. Try to scroll.
            if scrolls < max_scrolls:
                self._try_swipe("up")
                scrolls += 1
                time.sleep(0.6)
                continue

            raise RuntimeError(
                f"tap_text({keywords}): not visible after {scrolls} scrolls; "
                f"vision returned {type(action).__name__}"
            )

    def tap_xy(self, x: int, y: int) -> None:
        self._inputs.click(x, y)

    def swipe(self, direction: str, distance: int | None = None) -> None:
        bounds = self._window.get_phone_screen_region()
        cx = bounds["width"] // 2
        cy = bounds["height"] // 2
        mag = (
            distance if distance is not None
            else min(bounds["width"], bounds["height"]) // 3
        )
        if direction == "up":
            self._inputs.swipe(cx, cy + mag // 2, cx, cy - mag // 2)
        elif direction == "down":
            self._inputs.swipe(cx, cy - mag // 2, cx, cy + mag // 2)
        elif direction == "left":
            self._inputs.swipe(cx + mag // 2, cy, cx - mag // 2, cy)
        elif direction == "right":
            self._inputs.swipe(cx - mag // 2, cy, cx + mag // 2, cy)
        else:
            raise ValueError(f"unknown swipe direction: {direction!r}")

    def type_text(self, text: str) -> None:
        self._inputs.type_text(text)

    def press_key(self, key: str, modifiers: list[str] | None = None) -> None:
        self._inputs.press_key(key, modifiers=modifiers)

    def screenshot_label(self, label: str) -> None:
        ss = self._current_screenshot()
        self._on_screenshot(ss, {"kind": "label", "label": label})

    def read_regex(self, pattern: str) -> str | None:
        """Extract text matching ``pattern`` from the current screen."""
        ss = self._current_screenshot()
        self._on_screenshot(ss, {"kind": "read_regex", "pattern": pattern})
        ocr_task = (
            "Extract ALL visible text from this iPhone screenshot as plain text, "
            "line by line. Return DoneAction with summary=<all extracted text>."
        )
        try:
            response = self._vision.analyze_screen(ss, task=ocr_task)
        except Exception as exc:
            log.warning("read_regex vision call failed: %s", exc)
            return None
        text = getattr(response.action, "summary", None) or response.thought
        if not text:
            return None
        # Cap input to guard against ReDoS from malicious patterns × long OCR.
        match = re.search(pattern, text[:4096])
        if match is None:
            return None
        if match.groups():
            return match.group(1)
        return match.group(0)


__all__ = ["AgentController"]
