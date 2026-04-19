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

import anthropic
from PIL import Image

from pilot.core.input_simulator import InputSimulator
from pilot.core.vision import ClickAction, DoneAction, VisionAgent, WaitAction
from pilot.core.window_capture import MirroringWindowManager


class AnthropicAuthError(RuntimeError):
    """The Anthropic API rejected the key. Retrying won't help — abort fast."""


class MirroringLockedError(RuntimeError):
    """iPhone Mirroring is showing its lock/auth screen, not the iOS UI."""


_LOCKED_SIGNALS = (
    "mirroring is locked",
    "iphone mirroring is locked",
    "iphone is locked",
    "unlock your iphone",
    "face id",
    "authenticate",
    "passcode",
)


def _looks_locked(thought: str) -> bool:
    lowered = thought.lower()
    return any(s in lowered for s in _LOCKED_SIGNALS)


def _raise_if_auth(exc: Exception) -> None:
    """If ``exc`` is a 401/403 from Anthropic, convert to a friendly auth error."""
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code in (401, 403):
        raise AnthropicAuthError(
            "Anthropic API key is invalid or unauthorized "
            f"(HTTP {exc.status_code}). Update ANTHROPIC_API_KEY in .env "
            "at the repo root and try again."
        ) from exc

log = logging.getLogger("pilotd.controller")


_FIND_PROMPT = (
    "Find the target element. Targets (any match counts): {labels}.\n\n"
    "IMPORTANT — return ClickAction if ANY of these is on screen, even if "
    "only partially visible:\n"
    "  • Exact text (case-insensitive)\n"
    "  • PARTIAL overlap: target 'Dining' matches 'Dining Locations', 'Dining "
    "Hall', 'Campus Dining', 'Grab & Go Dining', etc.\n"
    "  • SYNONYM: 'Dining' matches 'Meal Swipes', 'Cafeteria', 'Food', 'Meal "
    "Plan'; 'Checkout' matches 'Proceed to Pay'; 'Reorder' matches 'Order Again'\n"
    "  • An ICON tile or row labeled with any of the above\n\n"
    "Decision rules:\n"
    "  1. If you see ANY visible text or icon that plausibly matches → return "
    "ClickAction with its center coords. Include what you matched in the "
    "description field.\n"
    "  2. ONLY return WaitAction if you can see a clear scroll indicator "
    "AND nothing on the current view resembles the target in any way.\n"
    "  3. Return DoneAction with summary='NOT_VISIBLE' if the target clearly "
    "isn't here and the page is not scrollable.\n\n"
    "STRONG BIAS: prefer ClickAction. Judges and users will see you scroll; "
    "they won't forgive you for scrolling past a button that was already "
    "visible. If unsure whether a partial match is valid, click it — one "
    "extra click is recoverable, a missed target is not."
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
        on_event: Callable[[dict[str, Any]], None] | None = None,
        lookup_hint: Callable[[str], dict | None] | None = None,
        save_hint: Callable[[str, int], None] | None = None,
    ) -> None:
        self._vision = vision
        self._inputs = inputs
        self._window = window
        self._on_screenshot = on_screenshot or (lambda *_: None)
        self._on_event = on_event or (lambda _event: None)
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
        """Exit whatever's in the foreground, go home, then launch via Spotlight.

        Pressing Home first ensures we don't start Spotlight inside a
        modal/overlay of the current app, and gives the phone a visual cue
        that we're transitioning. Settle times are generous — the phone
        takes 2-4s to fully render a freshly-launched app, and blasting
        inputs at a partially-loaded view misses the target half the time.
        """
        try:
            self._inputs.home()
        except Exception as exc:
            log.debug("home() failed before launch: %s", exc)
        time.sleep(0.9)
        self._inputs.open_app(app)
        # App-launch animations + first paint on an iPhone take ~3s.
        time.sleep(3.0)

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
                _raise_if_auth(exc)
                vision_errors += 1
                if vision_errors >= 3:
                    log.warning(
                        "wait_for %s: %d vision errors, bailing: %s",
                        keywords, vision_errors, exc,
                    )
                    return False
                time.sleep(1.0)
                continue

            vision_errors = 0

            thought_preview = (response.thought or "")[:80]
            action_kind = type(response.action).__name__
            log.info(
                "wait_for %s: claude=%s conf=%.2f thought=%r",
                keywords, action_kind, response.confidence, thought_preview,
            )
            self._emit_thought(action_kind, thought_preview, response.confidence)

            # Fail-fast: if Claude tells us the Mirroring window is on its
            # lock screen, no amount of scrolling fixes it.
            if _looks_locked(response.thought or ""):
                raise MirroringLockedError(
                    "iPhone Mirroring is showing its lock/authentication screen. "
                    "Pick up your iPhone, unlock it with Face ID or your passcode, "
                    "and wait for the Mirroring window to reconnect to the iOS UI."
                )

            if isinstance(response.action, ClickAction):
                if self._save_hint is not None and scrolls_applied != pre_scrolls:
                    try:
                        self._save_hint(canonical, scrolls_applied)
                    except Exception:
                        log.exception("save_hint failed")
                return True

            if isinstance(response.action, WaitAction):
                if scrolls_applied < max_scrolls:
                    self._try_swipe("up", gentle=True)
                    scrolls_applied += 1
                    polls_since_scroll = 0
                    time.sleep(0.8)
                    continue
                # Scroll budget exhausted but LLM still says 'scroll more'.
                # We may have scrolled past the target — try going back up.
                if pre_scrolls == 0:  # only reverse if we didn't start with a hint
                    log.info("wait_for %s: max_scrolls hit, reversing once", keywords)
                    self._try_swipe("down", gentle=True)
                    time.sleep(0.8)
                    pre_scrolls = -1  # sentinel: already reversed once
                    continue
                return False

            if isinstance(response.action, DoneAction):
                if scrolls_applied < max_scrolls:
                    self._try_swipe("up", gentle=True)
                    scrolls_applied += 1
                    polls_since_scroll = 0
                    time.sleep(0.8)
                    continue
                return False

            polls_since_scroll += 1
            time.sleep(0.8)

        return False

    def _emit_thought(self, action_kind: str, thought: str, confidence: float) -> None:
        """Forward Claude's reasoning to the live-run stream."""
        self._on_event({
            "event": "step",
            "step": -1,
            "kind": f"🧠 {action_kind}  conf={confidence:.2f}  — {thought[:80]}",
        })

    def _try_swipe(self, direction: str, *, gentle: bool = False) -> None:
        """Swipe without letting a geometry error abort the whole wait loop.

        ``gentle=True`` uses a ~quarter-screen stroke (vs the default third)
        so we don't over-scroll past a target that was about to appear.
        """
        try:
            if gentle:
                bounds = self._window.get_phone_screen_region()
                shorter = min(bounds["width"], bounds["height"])
                self.swipe(direction, distance=shorter // 4)
            else:
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
            try:
                response = self._vision.analyze_screen(ss, task=task_prompt)
            except Exception as exc:
                _raise_if_auth(exc)
                raise
            action = response.action

            if isinstance(action, ClickAction):
                px, py = self._to_phone_points(action.x, action.y, ss)
                self._inputs.click(px, py)
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

    def _to_phone_points(
        self, px: float, py: float, screenshot: Image.Image
    ) -> tuple[float, float]:
        """Map Claude's pixel coords from the screenshot space to phone-screen
        relative points.

        Claude sees the whole captured window image (including the 28pt
        title bar). We rescale the pixel coords to window-points using the
        actual image dimensions vs. window dimensions (accounts for the
        retina factor AND any client-side downscale), then subtract the
        title bar and bezel offsets to land in phone-screen-relative space.
        """
        img_w, img_h = screenshot.size
        bounds = self._window.get_window_bounds()
        win_w = float(bounds.get("width", img_w))
        win_h = float(bounds.get("height", img_h))
        if img_w <= 0 or img_h <= 0 or win_w <= 0 or win_h <= 0:
            return px, py
        wx = px * win_w / img_w
        wy = py * win_h / img_h
        region = self._window.get_phone_screen_region()
        rx = wx - float(region.get("x", 0))
        ry = wy - float(region.get("y", 0))
        # Clamp inside the phone screen so small drift from Claude's eyeballing
        # doesn't trigger OutOfBoundsError.
        rw = float(region.get("width", win_w))
        rh = float(region.get("height", win_h))
        rx = max(1.0, min(rx, rw - 1.0))
        ry = max(1.0, min(ry, rh - 1.0))
        return rx, ry

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
            _raise_if_auth(exc)
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
