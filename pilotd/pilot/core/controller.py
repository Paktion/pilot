"""
AgentController — bridges the workflow engine's ``Controller`` protocol to
the live perception-action stack (window capture + input simulator + vision).

Responsibilities
----------------
* ``launch`` — invoke Spotlight via the input simulator
* ``wait_for`` — poll the Mirroring window until target text appears (vision)
* ``tap_text`` — locate target text on the current screenshot via the vision
  agent, then tap at the returned coordinates
* ``tap_xy`` — raw coordinate tap (used by compiled skills)
* ``swipe``, ``type_text``, ``press_key`` — forwarded to the input simulator
* ``read_regex`` — pull text off the current screenshot and match a regex
* ``screenshot_label`` — tag the session recording
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

from PIL import Image

from pilot.core.input_simulator import InputSimulator
from pilot.core.vision import AgentResponse, ClickAction, VisionAgent
from pilot.core.window_capture import MirroringWindowManager

log = logging.getLogger("pilotd.controller")


_TAP_PROMPT_TEMPLATE = (
    "Your only job for this single turn is to return a ClickAction at the "
    "center of the element labeled {label!r}. If the element is not visible, "
    "return a DoneAction with summary='NOT_VISIBLE'."
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
    ) -> None:
        self._vision = vision
        self._inputs = inputs
        self._window = window
        self._on_screenshot = on_screenshot or (lambda *_: None)

    # ---- perception --------------------------------------------------------

    def _current_screenshot(self) -> Image.Image:
        return self._window.capture_screenshot()

    # ---- control -----------------------------------------------------------

    def launch(self, app: str) -> None:
        self._inputs.open_app(app)
        time.sleep(1.2)

    def wait_for(self, text: str, timeout_s: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            ss = self._current_screenshot()
            self._on_screenshot(ss, {"kind": "wait_for", "target": text})
            try:
                response = self._vision.analyze_screen(
                    ss,
                    task=_TAP_PROMPT_TEMPLATE.format(label=text),
                )
            except Exception as exc:
                log.warning("wait_for vision call failed: %s", exc)
                time.sleep(1.0)
                continue
            if isinstance(response.action, ClickAction):
                return True
            time.sleep(0.8)
        return False

    def tap_text(self, text: str, prefer: str | None = None) -> None:
        ss = self._current_screenshot()
        self._on_screenshot(ss, {"kind": "tap", "target": text, "prefer": prefer})
        response = self._vision.analyze_screen(
            ss,
            task=_TAP_PROMPT_TEMPLATE.format(label=text),
        )
        action = response.action
        if not isinstance(action, ClickAction):
            raise RuntimeError(
                f"tap_text({text!r}): vision returned {type(action).__name__}, not a ClickAction"
            )
        self._inputs.click(action.x, action.y)

    def tap_xy(self, x: int, y: int) -> None:
        self._inputs.click(x, y)

    def swipe(self, direction: str, distance: int | None = None) -> None:
        # Center-of-screen gesture of configurable length.
        bounds = self._window.get_phone_screen_region()
        cx = bounds["width"] // 2
        cy = bounds["height"] // 2
        mag = distance if distance is not None else min(bounds["width"], bounds["height"]) // 3
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
        """Extract text matching ``pattern`` from the current screen.

        Implementation: ask Claude to OCR the current screen, then regex-match
        the returned text. Falls back to ``None`` if no match.
        """
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
        match = re.search(pattern, text)
        if match is None:
            return None
        # If the pattern captures a group, return it; else the whole match.
        if match.groups():
            return match.group(1)
        return match.group(0)


__all__ = ["AgentController"]
