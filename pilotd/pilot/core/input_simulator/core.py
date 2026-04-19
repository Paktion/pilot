"""
Default input simulation backend: pyautogui with a cliclick fallback.

Dispatches mouse, keyboard, and gesture events at the macOS iPhone
Mirroring window. All public coordinates are phone-screen-relative and
are converted to screen-absolute pixels inside each method.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import TYPE_CHECKING, List, Optional, Sequence

import pyautogui

from pilot.core.input_simulator._coords import (
    InputError,
    OutOfBoundsError,
    bounds_check_with,
    get_bounds,
    refresh_bounds,
    to_absolute_with,
)
from pilot.core.input_simulator._focus import (
    activate_app,
    activate_mirroring,
    get_frontmost_app,
)
from pilot.core.input_simulator.unicode_input import (
    _ClipboardError,
    paste_via_pyautogui,
)

if TYPE_CHECKING:
    from pilot.core.window_capture import MirroringWindowManager

logger = logging.getLogger("pilotd.input")

# Safety configuration: keep failsafe enabled, disable pyautogui's own
# per-call pause (we handle inter-action delays ourselves).
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

__all__ = [
    "InputError",
    "InputSimulator",
    "OutOfBoundsError",
]

class InputSimulator:
    """Send synthetic HID events to the iPhone Mirroring window.

    ``window_manager`` is a ``MirroringWindowManager`` that resolves the
    iPhone Mirroring window position. ``action_delay`` is the seconds
    inserted after every public action. When ``use_cliclick_fallback`` is
    ``True`` (default), a ``cliclick`` subprocess is tried if ``pyautogui``
    fails for a click/move.
    """

    # Default delay (seconds) inserted after every public action.
    DEFAULT_ACTION_DELAY: float = 0.3

    def __init__(
        self,
        window_manager: "MirroringWindowManager",
        action_delay: float = DEFAULT_ACTION_DELAY,
        use_cliclick_fallback: bool = True,
        retina_scale: float = 2.0,
    ) -> None:
        self._wm = window_manager
        self._action_delay = action_delay
        self._use_cliclick_fallback = use_cliclick_fallback
        self._retina_scale = retina_scale
        self._cliclick_path: Optional[str] = shutil.which("cliclick")

        if self._use_cliclick_fallback and self._cliclick_path is None:
            logger.warning(
                "cliclick not found -- fallback clicking will be unavailable. "
                "Install it for more reliable input simulation: brew install cliclick"
            )

        logger.debug(
            "InputSimulator initialised  action_delay=%s  cliclick=%s",
            self._action_delay, self._cliclick_path,
        )

    def _refresh_bounds(self) -> None:  # noqa: D401
        refresh_bounds(self._wm)

    def _get_bounds(self) -> dict:  # noqa: D401
        return get_bounds(self._wm)

    def _to_absolute_with(self, x, y, bounds):  # noqa: D401
        return to_absolute_with(x, y, bounds)

    def _bounds_check_with(self, x, y, bounds):  # noqa: D401
        bounds_check_with(x, y, bounds)

    def _to_absolute(self, x: float, y: float) -> tuple[int, int]:
        return to_absolute_with(x, y, get_bounds(self._wm))

    def _bounds_check(self, x: float, y: float) -> None:
        bounds_check_with(x, y, get_bounds(self._wm))

    def _post_action_delay(self) -> None:
        if self._action_delay > 0:
            time.sleep(self._action_delay)

    def _ensure_focus(self) -> None:
        """Briefly focus iPhone Mirroring for keyboard input; remember the
        caller's app so :meth:`_restore_focus` can put it back.

        Only needed for keyboard actions because those events go to the
        focused window. Click/swipe use absolute coordinates.
        """
        self._previous_app = get_frontmost_app()
        activate_mirroring()

    def _restore_focus(self) -> None:
        """Restore focus to whatever app the user was working in before."""
        prev = getattr(self, "_previous_app", None)
        if prev and prev != "iPhone Mirroring":
            activate_app(prev)

    @staticmethod
    def _save_mouse_position() -> tuple[int, int]:
        pos = pyautogui.position()
        return (pos[0], pos[1])

    @staticmethod
    def _restore_mouse_position(pos: tuple[int, int]) -> None:
        try:
            pyautogui.moveTo(pos[0], pos[1], duration=0, _pause=False)
        except Exception:
            pass  # Best effort

    def _pyautogui_click(
        self,
        abs_x: int,
        abs_y: int,
        *,
        clicks: int = 1,
        button: str = "left",
        interval: float = 0.0,
    ) -> None:
        """Perform a click via pyautogui, restoring cursor position after."""
        saved = self._save_mouse_position()
        pyautogui.click(abs_x, abs_y, clicks=clicks, button=button, interval=interval)
        self._restore_mouse_position(saved)

    def _run_cliclick(self, op: str, abs_x: int, abs_y: int) -> None:
        """Run the cliclick subprocess for *op* (``c``, ``dc``, or ``m``)."""
        if self._cliclick_path is None:
            raise InputError(
                "cliclick is not installed. Install it for more reliable "
                "click simulation: brew install cliclick"
            )
        cmd = [self._cliclick_path, f"{op}:{abs_x},{abs_y}"]
        logger.debug("cliclick command: %s", cmd)
        subprocess.run(cmd, check=True, capture_output=True, timeout=5)

    def _cliclick_click(self, abs_x: int, abs_y: int) -> None:
        """Perform a click via cliclick (subprocess fallback)."""
        self._run_cliclick("c", abs_x, abs_y)

    def _cliclick_double_click(self, abs_x: int, abs_y: int) -> None:
        """Perform a double-click via cliclick."""
        self._run_cliclick("dc", abs_x, abs_y)

    def _cliclick_move(self, abs_x: int, abs_y: int) -> None:
        """Move the mouse cursor via cliclick."""
        self._run_cliclick("m", abs_x, abs_y)

    def click(self, x: float, y: float, duration: float = 0.0) -> None:
        """Tap at phone-screen-relative *(x, y)*.

        ``duration > 0`` produces a long-press. Raises :class:`OutOfBoundsError`
        if outside the phone screen; :class:`InputError` if no backend succeeds.
        """
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        bounds_check_with(x, y, bounds)
        abs_x, abs_y = to_absolute_with(x, y, bounds)
        # Mirroring must be frontmost when the click fires, otherwise the
        # synthetic event lands on whichever window is actually at that
        # absolute coord (Pilot.app, the Finder, etc.) and iOS sees nothing.
        activate_mirroring()
        logger.info(
            "click  rel=(%s, %s)  abs=(%s, %s)  duration=%s",
            x, y, abs_x, abs_y, duration,
        )

        if duration > 0:
            # Long press: move to position, press, hold, release.
            try:
                pyautogui.moveTo(abs_x, abs_y)
                pyautogui.mouseDown()
                time.sleep(duration)
                pyautogui.mouseUp()
            except Exception as exc:
                raise InputError(
                    f"Long-press failed: {exc}. Ensure Accessibility permission is granted "
                    "in System Settings > Privacy & Security > Accessibility."
                ) from exc
        else:
            self._click_with_fallback(
                label="Click",
                pyautogui_op=lambda: self._pyautogui_click(abs_x, abs_y),
                cliclick_op=lambda: self._cliclick_click(abs_x, abs_y),
            )

        self._post_action_delay()

    def double_click(self, x: float, y: float) -> None:
        """Double-tap at phone-screen-relative *(x, y)*."""
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        bounds_check_with(x, y, bounds)
        abs_x, abs_y = to_absolute_with(x, y, bounds)
        activate_mirroring()
        logger.info("double_click  rel=(%s, %s)  abs=(%s, %s)", x, y, abs_x, abs_y)

        self._click_with_fallback(
            label="Double-click",
            pyautogui_op=lambda: self._pyautogui_click(abs_x, abs_y, clicks=2, interval=0.05),
            cliclick_op=lambda: self._cliclick_double_click(abs_x, abs_y),
        )

        self._post_action_delay()

    def _click_with_fallback(self, *, label: str, pyautogui_op, cliclick_op) -> None:
        """Run *pyautogui_op*; on failure fall back to *cliclick_op* if enabled."""
        try:
            pyautogui_op()
        except Exception as primary_exc:
            if self._use_cliclick_fallback:
                logger.warning("pyautogui %s failed, trying cliclick fallback: %s", label, primary_exc)
                try:
                    cliclick_op()
                except Exception as fallback_exc:
                    raise InputError(
                        f"{label} failed on both backends (pyautogui and cliclick). "
                        "This is usually a macOS Accessibility permission issue. "
                        "Go to System Settings > Privacy & Security > Accessibility "
                        "and enable your terminal app, then restart it."
                    ) from fallback_exc
            else:
                raise InputError(
                    f"{label} failed: {primary_exc}. Ensure Accessibility permission is granted in "
                    "System Settings > Privacy & Security > Accessibility. "
                    "Installing cliclick (brew install cliclick) provides a fallback input method."
                ) from primary_exc

    def swipe(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: float = 0.5,
    ) -> None:
        """Drag gesture inside the phone screen region.

        ``mouseUp()`` is in a ``finally`` block so the button cannot be
        left depressed if ``moveTo`` raises.
        """
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        bounds_check_with(start_x, start_y, bounds)
        bounds_check_with(end_x, end_y, bounds)

        abs_sx, abs_sy = to_absolute_with(start_x, start_y, bounds)
        abs_ex, abs_ey = to_absolute_with(end_x, end_y, bounds)

        activate_mirroring()

        logger.info(
            "swipe  from=(%s,%s) to=(%s,%s)  duration=%s",
            start_x, start_y, end_x, end_y, duration,
        )

        saved = self._save_mouse_position()
        try:
            pyautogui.moveTo(abs_sx, abs_sy)
            time.sleep(0.05)
            pyautogui.mouseDown()
            try:
                pyautogui.moveTo(abs_ex, abs_ey, duration=duration)
            finally:
                pyautogui.mouseUp()
        except InputError:
            self._restore_mouse_position(saved)
            raise
        except Exception as exc:
            self._restore_mouse_position(saved)
            raise InputError(
                f"Swipe gesture failed: {exc}. Ensure Accessibility permission is granted "
                "in System Settings > Privacy & Security > Accessibility for your terminal app."
            ) from exc

        self._restore_mouse_position(saved)
        self._post_action_delay()

    def scroll(
        self,
        x: float,
        y: float,
        direction: str = "down",
        amount: int = 3,
    ) -> None:
        """Scroll by synthesising a swipe from the screen centre.

        Natural-scroll inversion: scroll-down = swipe-up. iPhone Mirroring
        ignores macOS scroll-wheel events, hence the swipe.
        """
        valid_directions = {"up", "down", "left", "right"}
        if direction not in valid_directions:
            raise ValueError(
                f"Invalid scroll direction {direction!r}. "
                f"Use one of: 'up', 'down', 'left', 'right'."
            )

        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        phone_w = bounds["phone_w"]
        phone_h = bounds["phone_h"]

        cx = phone_w / 2
        cy = phone_h / 2

        # ~80 pts per unit, clamped so the swipe stays inside the phone screen.
        distance = min(80 * amount, phone_h * 0.4, phone_w * 0.4)

        # Natural-scroll inversion: the finger moves opposite to the scroll.
        half = distance / 2
        deltas = {
            "down":  (cx,         cy + half,  cx,         cy - half),
            "up":    (cx,         cy - half,  cx,         cy + half),
            "left":  (cx + half,  cy,         cx - half,  cy),
            "right": (cx - half,  cy,         cx + half,  cy),
        }
        start_x, start_y, end_x, end_y = deltas[direction]

        logger.info(
            "scroll (swipe)  direction=%s  amount=%s  from=(%s,%s) to=(%s,%s)",
            direction, amount, start_x, start_y, end_x, end_y,
        )

        # Delegate to swipe() -- it handles bounds-checking, absolute
        # conversion, mouseDown/mouseUp safety, and the post-action delay.
        self.swipe(start_x, start_y, end_x, end_y, duration=0.3)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """Type *text* into the focused element.

        Focuses iPhone Mirroring first and restores the caller's app after.
        ASCII uses ``pyautogui.typewrite``; non-ASCII falls back to
        ``pbcopy`` + ``Cmd+V``.
        """
        if not text:
            return

        refresh_bounds(self._wm)
        self._ensure_focus()

        logger.info("type_text  length=%d  text=%r", len(text), text[:80])

        try:
            if text.isascii():
                pyautogui.typewrite(text, interval=interval)
            else:
                self._type_via_clipboard(text)
        except InputError:
            self._restore_focus()
            raise
        except Exception as exc:
            self._restore_focus()
            raise InputError(
                f"Text input failed: {exc}. Make sure the iPhone Mirroring window is "
                "in the foreground and a text field is focused on the iPhone screen. "
                "Also verify Accessibility permission is enabled in "
                "System Settings > Privacy & Security > Accessibility."
            ) from exc

        self._restore_focus()
        self._post_action_delay()

    @staticmethod
    def _type_via_clipboard(text: str) -> None:
        """Paste *text* by writing to the macOS clipboard, then Cmd+V."""
        try:
            paste_via_pyautogui(text)
        except _ClipboardError as exc:
            raise InputError(str(exc)) from exc

    def press_key(
        self,
        key: str,
        modifiers: Optional[Sequence[str]] = None,
    ) -> None:
        """Press *key* with optional *modifiers*.

        Focuses iPhone Mirroring first and restores the caller's app after.
        """
        refresh_bounds(self._wm)
        self._ensure_focus()

        if modifiers:
            combo: List[str] = list(modifiers) + [key]
            logger.info("press_key  combo=%s", combo)
            op = lambda: pyautogui.hotkey(*combo)
            descr = "+".join(combo)
        else:
            logger.info("press_key  key=%s", key)
            op = lambda: pyautogui.press(key)
            descr = key
        try:
            op()
        except Exception as exc:
            raise InputError(
                f"Key press failed ({descr}): {exc}. Ensure Accessibility permission is "
                "enabled in System Settings > Privacy & Security > Accessibility."
            ) from exc

        self._restore_focus()
        self._post_action_delay()

    def home(self) -> None:
        """Navigate to the iPhone home screen (Cmd+1)."""
        logger.info("home (Cmd+1)")
        self.press_key("1", modifiers=["command"])

    def app_switcher(self) -> None:
        """Open the iPhone app switcher (Cmd+2)."""
        logger.info("app_switcher (Cmd+2)")
        self.press_key("2", modifiers=["command"])

    def spotlight(self) -> None:
        """Open Spotlight / iPhone search (Cmd+3)."""
        logger.info("spotlight (Cmd+3)")
        self.press_key("3", modifiers=["command"])

    def back(self) -> None:
        """Simulate an iOS back gesture (swipe from the left edge right)."""
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        phone_w = bounds["phone_w"]
        phone_h = bounds["phone_h"]

        start_x = 5  # A few pixels inside the left edge.
        start_y = phone_h * 0.5
        end_x = phone_w * 0.35
        end_y = start_y

        logger.info("back  swipe from (%s,%s) to (%s,%s)", start_x, start_y, end_x, end_y)
        self.swipe(start_x, start_y, end_x, end_y, duration=0.3)

    def open_app(self, app_name: str) -> None:
        """Open *app_name* via Spotlight (Cmd+3 + type + Enter)."""
        if not app_name:
            raise ValueError("app_name must be a non-empty string.")

        logger.info("open_app  app_name=%r", app_name)

        self.spotlight()
        # Allow Spotlight animation to complete.
        time.sleep(0.5)
        self.type_text(app_name)
        # Brief pause so search results can populate.
        time.sleep(0.8)
        self.press_key("enter")

    def long_press(self, x: float, y: float, duration: float = 1.0) -> None:
        """Long-press at window-relative *(x, y)*; wraps :meth:`click`."""
        self.click(x, y, duration=duration)

    def screenshot_to_window_coords(
        self, sx: float, sy: float
    ) -> tuple[float, float]:
        """Divide screenshot-pixel coords by ``retina_scale`` to get points."""
        return sx / self._retina_scale, sy / self._retina_scale

    def __repr__(self) -> str:
        return (
            f"<InputSimulator "
            f"action_delay={self._action_delay} "
            f"cliclick={'available' if self._cliclick_path else 'unavailable'}>"
        )
