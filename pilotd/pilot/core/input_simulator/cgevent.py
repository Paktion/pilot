"""
Non-intrusive input backend using Quartz CGEvent APIs.

Same public surface as :class:`InputSimulator` but dispatches synthetic
events via ``CGEventPostToPid`` aimed at the iPhone Mirroring process --
no visible-cursor moves, no focus stealing. Requires
``pyobjc-framework-Quartz`` and macOS Accessibility permission.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventCreateMouseEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSetIntegerValueField,
    CGPointMake,
    CGWindowListCopyWindowInfo,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGMouseEventClickState,
    kCGNullWindowID,
    kCGWindowListOptionAll,
)
from pilot.core.input_simulator._cgevent_typing import (
    type_ascii_via_cgevent,
    type_via_clipboard_cgevent,
)
from pilot.core.input_simulator._coords import (
    InputError,
    bounds_check_with,
    get_bounds,
    refresh_bounds,
    to_absolute_with,
)
from pilot.core.input_simulator._keycodes import _KEY_NAME_TO_KEYCODE, _MODIFIER_MAP

if TYPE_CHECKING:
    from pilot.core.window_capture import MirroringWindowManager

logger = logging.getLogger("pilotd.input")

# Owner name used to locate the iPhone Mirroring PID.
_MIRRORING_OWNER = "iPhone Mirroring"

def _find_mirroring_pid() -> int | None:
    """Return the PID of the iPhone Mirroring process, or None."""
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionAll, kCGNullWindowID
    )
    if window_list is None:
        return None
    for win in window_list:
        owner = win.get("kCGWindowOwnerName", "")
        if owner == _MIRRORING_OWNER and win.get("kCGWindowIsOnscreen", False):
            pid = win.get("kCGWindowOwnerPID")
            if pid is not None:
                return int(pid)
    return None

# CGEventPostToPid availability check.
try:
    from Quartz import CGEventPostToPid as _cg_event_post_to_pid  # type: ignore[attr-defined]
    _HAS_POST_TO_PID = True
except ImportError:
    _HAS_POST_TO_PID = False
    _cg_event_post_to_pid = None

def _post_event(event: Any, pid: int | None) -> None:
    """Post *event* to iPhone Mirroring; prefers ``CGEventPostToPid`` so
    the visible cursor isn't moved, falling back to ``CGEventPost`` at
    the HID event tap when the PID-targeted variant is unavailable.
    """
    if _HAS_POST_TO_PID and pid is not None:
        _cg_event_post_to_pid(pid, event)
    else:
        CGEventPost(kCGHIDEventTap, event)

class CGEventInputSimulator:
    """Non-intrusive input simulator using Quartz CGEvent APIs.

    Same public surface as :class:`InputSimulator` but avoids moving the
    visible cursor or stealing keyboard focus. ``retina_scale`` defaults
    to 2.0 for standard Retina displays.
    """

    DEFAULT_ACTION_DELAY: float = 0.3

    def __init__(
        self,
        window_manager: "MirroringWindowManager",
        action_delay: float = DEFAULT_ACTION_DELAY,
        retina_scale: float = 2.0,
    ) -> None:
        self._wm = window_manager
        self._action_delay = action_delay
        self._retina_scale = retina_scale
        self._cached_pid: int | None = None

        logger.debug(
            "CGEventInputSimulator initialised  action_delay=%s  "
            "CGEventPostToPid available=%s",
            self._action_delay,
            _HAS_POST_TO_PID,
        )

    def _get_pid(self) -> int | None:
        """Return the cached PID of iPhone Mirroring, refreshing if needed."""
        if self._cached_pid is None:
            self._cached_pid = _find_mirroring_pid()
        return self._cached_pid

    def _refresh_pid(self) -> int | None:
        """Force-refresh the iPhone Mirroring PID."""
        self._cached_pid = _find_mirroring_pid()
        return self._cached_pid

    def _refresh_bounds(self) -> None:
        refresh_bounds(self._wm)

    def _get_bounds(self) -> Dict[str, Any]:
        return get_bounds(self._wm)

    def _to_absolute_with(self, x: float, y: float, bounds: Dict[str, Any]) -> tuple[int, int]:
        return to_absolute_with(x, y, bounds)

    def _to_absolute(self, x: float, y: float) -> tuple[int, int]:
        return to_absolute_with(x, y, get_bounds(self._wm))

    def _bounds_check_with(self, x: float, y: float, bounds: Dict[str, Any]) -> None:
        bounds_check_with(x, y, bounds)

    def _bounds_check(self, x: float, y: float) -> None:
        bounds_check_with(x, y, get_bounds(self._wm))

    def _post_action_delay(self) -> None:
        if self._action_delay > 0:
            time.sleep(self._action_delay)

    def _post(self, event: Any) -> None:
        _post_event(event, self._get_pid())

    def _post_hid(self, event: Any) -> None:
        """Post *event* to the system HID event tap.

        Keyboard events only translate into iOS input when iPhone Mirroring
        sees them through the same pipe a physical keyboard would use; the
        PID-targeted path delivers to Mirroring's local queue but drops on
        the floor before reaching iOS. Clicks stay on the PID path.
        """
        CGEventPost(kCGHIDEventTap, event)

    def _make_mouse_event(
        self, event_type: int, x: int, y: int, button: int = kCGMouseButtonLeft
    ) -> Any:
        return CGEventCreateMouseEvent(None, event_type, CGPointMake(float(x), float(y)), button)

    def _make_key_event(self, keycode: int, key_down: bool) -> Any:
        return CGEventCreateKeyboardEvent(None, keycode, key_down)

    def click(self, x: float, y: float, duration: float = 0.0) -> None:
        """Tap at phone-screen-relative *(x, y)*; ``duration > 0`` = long-press.

        Briefly activates Mirroring before posting so iOS actually receives
        the event. CGEventPostToPid targets the Mirroring process, but if
        Mirroring isn't the frontmost window, macOS can route the event
        outside the mirror pipe and iOS never sees it.
        """
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        bounds_check_with(x, y, bounds)
        abs_x, abs_y = to_absolute_with(x, y, bounds)
        self._activate_mirroring()

        logger.info(
            "CGEvent click  rel=(%s, %s)  abs=(%s, %s)  duration=%s",
            x, y, abs_x, abs_y, duration,
        )

        try:
            down = self._make_mouse_event(kCGEventLeftMouseDown, abs_x, abs_y)
            up = self._make_mouse_event(kCGEventLeftMouseUp, abs_x, abs_y)

            self._post(down)
            if duration > 0:
                time.sleep(duration)
            self._post(up)
        except Exception as exc:
            raise InputError(
                f"CGEvent click failed at ({abs_x}, {abs_y}): {exc}. Ensure Accessibility "
                "permission is granted in System Settings > Privacy & Security > Accessibility."
            ) from exc

        self._post_action_delay()

    def double_click(self, x: float, y: float) -> None:
        """Double-tap at phone-screen-relative *(x, y)*."""
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        bounds_check_with(x, y, bounds)
        abs_x, abs_y = to_absolute_with(x, y, bounds)

        logger.info(
            "CGEvent double_click  rel=(%s, %s)  abs=(%s, %s)",
            x, y, abs_x, abs_y,
        )

        try:
            point = CGPointMake(float(abs_x), float(abs_y))

            def _click_at(click_state: int) -> tuple[Any, Any]:
                dn = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
                CGEventSetIntegerValueField(dn, kCGMouseEventClickState, click_state)
                u = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
                CGEventSetIntegerValueField(u, kCGMouseEventClickState, click_state)
                return dn, u

            down1, up1 = _click_at(1)
            down2, up2 = _click_at(2)

            self._post(down1)
            self._post(up1)
            time.sleep(0.05)
            self._post(down2)
            self._post(up2)
        except Exception as exc:
            raise InputError(
                f"CGEvent double-click failed at ({abs_x}, {abs_y}): {exc}. "
                f"Ensure Accessibility permission is granted."
            ) from exc

        self._post_action_delay()

    def swipe(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: float = 0.5,
    ) -> None:
        """Perform a swipe (drag) gesture within the phone screen region."""
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        bounds_check_with(start_x, start_y, bounds)
        bounds_check_with(end_x, end_y, bounds)

        abs_sx, abs_sy = to_absolute_with(start_x, start_y, bounds)
        abs_ex, abs_ey = to_absolute_with(end_x, end_y, bounds)

        logger.info(
            "CGEvent swipe  from=(%s,%s) to=(%s,%s)  duration=%s",
            start_x, start_y, end_x, end_y, duration,
        )

        # Number of intermediate drag steps.  More steps produce smoother
        # swipes that are more reliably recognised by iOS.
        steps = max(int(duration / 0.016), 10)  # ~60 fps or at least 10 steps

        try:
            # Mouse down at start position
            down = self._make_mouse_event(
                kCGEventLeftMouseDown, abs_sx, abs_sy
            )
            self._post(down)

            # Interpolate intermediate drag events
            step_delay = duration / steps
            for i in range(1, steps + 1):
                t = i / steps
                cur_x = round(abs_sx + (abs_ex - abs_sx) * t)
                cur_y = round(abs_sy + (abs_ey - abs_sy) * t)
                drag = self._make_mouse_event(
                    kCGEventLeftMouseDragged, cur_x, cur_y
                )
                self._post(drag)
                if step_delay > 0:
                    time.sleep(step_delay)

            # Mouse up at end position
            up = self._make_mouse_event(kCGEventLeftMouseUp, abs_ex, abs_ey)
            self._post(up)
        except InputError:
            raise
        except Exception as exc:
            # Always attempt mouse-up to avoid stuck button state
            try:
                up = self._make_mouse_event(
                    kCGEventLeftMouseUp, abs_ex, abs_ey
                )
                self._post(up)
            except Exception:
                pass
            raise InputError(
                f"CGEvent swipe failed: {exc}. "
                f"Ensure Accessibility permission is granted."
            ) from exc

        self._post_action_delay()

    def scroll(
        self,
        x: float,
        y: float,
        direction: str = "down",
        amount: int = 3,
    ) -> None:
        """Scroll by synthesising a swipe from the screen centre.

        Natural-scrolling inversion: scroll-down = swipe-up, etc.
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

        distance = min(80 * amount, phone_h * 0.4, phone_w * 0.4)

        # Natural-scrolling inversion: finger moves opposite to the scroll.
        half = distance / 2
        deltas = {
            "down":  (cx,         cy + half,  cx,         cy - half),
            "up":    (cx,         cy - half,  cx,         cy + half),
            "left":  (cx + half,  cy,         cx - half,  cy),
            "right": (cx - half,  cy,         cx + half,  cy),
        }
        sx, sy, ex, ey = deltas[direction]

        logger.info(
            "CGEvent scroll (swipe)  direction=%s  amount=%s  from=(%s,%s) to=(%s,%s)",
            direction, amount, sx, sy, ex, ey,
        )

        self.swipe(sx, sy, ex, ey, duration=0.3)

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """Type *text* by sending CGEvent keyboard events.

        Briefly activates iPhone Mirroring so the key events reach iOS
        through the mirror pipe — without this, CGEvent keys post to the
        PID but get dropped if Mirroring isn't the frontmost window.
        """
        if not text:
            return

        refresh_bounds(self._wm)
        self._activate_mirroring()

        logger.info("CGEvent type_text  length=%d  text=%r", len(text), text[:80])

        try:
            if text.isascii():
                type_ascii_via_cgevent(text, interval, self._post_hid)
            else:
                type_via_clipboard_cgevent(text, self._post_hid)
        except InputError:
            raise
        except Exception as exc:
            raise InputError(
                f"CGEvent text input failed: {exc}. "
                f"Ensure Accessibility permission is granted."
            ) from exc

        self._post_action_delay()

    @staticmethod
    def _activate_mirroring() -> None:
        """Activate iPhone Mirroring just long enough for keyboard events to
        route through its mirror pipe. Small focus nudge; cheaper than the
        pyautogui approach that activates for every click."""
        from pilot.core.input_simulator._focus import activate_mirroring
        try:
            activate_mirroring()
        except Exception as exc:
            logger.debug("activate_mirroring failed: %s", exc)

    def press_key(
        self,
        key: str,
        modifiers: Optional[Sequence[str]] = None,
    ) -> None:
        """Press *key* with optional *modifiers* via ``CGEventPostToPid``.

        Briefly activates Mirroring first — same rationale as type_text.
        """
        refresh_bounds(self._wm)
        self._activate_mirroring()

        keycode = _KEY_NAME_TO_KEYCODE.get(key.lower())
        if keycode is None:
            raise InputError(
                f"Unknown key name {key!r}. "
                f"Supported keys: {', '.join(sorted(_KEY_NAME_TO_KEYCODE.keys()))}"
            )

        # Build combined modifier flags
        flags = 0
        mod_keycodes: list[int] = []
        for mod in modifiers or ():
            mod_lower = mod.lower()
            if mod_lower not in _MODIFIER_MAP:
                raise InputError(
                    f"Unknown modifier {mod!r}. "
                    f"Supported: {', '.join(sorted(_MODIFIER_MAP.keys()))}"
                )
            flag, mod_kc = _MODIFIER_MAP[mod_lower]
            flags |= flag
            mod_keycodes.append(mod_kc)

        logger.info(
            "CGEvent press_key  %s",
            f"combo={list(modifiers) + [key]}" if modifiers else f"key={key}",
        )

        try:
            # Press modifier keys down
            for mod_kc in mod_keycodes:
                self._post_hid(self._make_key_event(mod_kc, True))

            # Press the main key
            down = self._make_key_event(keycode, True)
            if flags:
                CGEventSetFlags(down, flags)
            self._post_hid(down)

            up = self._make_key_event(keycode, False)
            if flags:
                CGEventSetFlags(up, flags)
            self._post_hid(up)

            # Release modifier keys (reverse order)
            for mod_kc in reversed(mod_keycodes):
                self._post_hid(self._make_key_event(mod_kc, False))
        except InputError:
            raise
        except Exception as exc:
            raise InputError(
                f"CGEvent key press failed ({key}): {exc}. Ensure Accessibility permission is granted."
            ) from exc

        self._post_action_delay()

    def home(self) -> None:
        """Navigate to the iPhone home screen (Cmd+1)."""
        logger.info("CGEvent home (Cmd+1)")
        self.press_key("1", modifiers=["command"])

    def app_switcher(self) -> None:
        """Open the iPhone app switcher (Cmd+2)."""
        logger.info("CGEvent app_switcher (Cmd+2)")
        self.press_key("2", modifiers=["command"])

    def spotlight(self) -> None:
        """Open Spotlight / iPhone search (Cmd+3)."""
        logger.info("CGEvent spotlight (Cmd+3)")
        self.press_key("3", modifiers=["command"])

    def back(self) -> None:
        """Simulate an iOS back gesture (left-edge swipe right)."""
        refresh_bounds(self._wm)
        bounds = get_bounds(self._wm)
        phone_w, phone_h = bounds["phone_w"], bounds["phone_h"]

        start_x, start_y = 5, phone_h * 0.5
        end_x, end_y = phone_w * 0.35, start_y

        logger.info("CGEvent back  swipe from (%s,%s) to (%s,%s)", start_x, start_y, end_x, end_y)
        self.swipe(start_x, start_y, end_x, end_y, duration=0.3)

    def open_app(self, app_name: str) -> None:
        """Open *app_name* on the iPhone via Spotlight search."""
        if not app_name:
            raise ValueError("app_name must be a non-empty string.")

        logger.info("CGEvent open_app  app_name=%r", app_name)

        self.spotlight()
        time.sleep(0.5)
        self.type_text(app_name)
        time.sleep(0.8)
        self.press_key("enter")

    def long_press(self, x: float, y: float, duration: float = 1.0) -> None:
        """Long-press at phone-screen-relative *(x, y)*; wraps :meth:`click`."""
        self.click(x, y, duration=duration)

    def screenshot_to_window_coords(
        self, sx: float, sy: float
    ) -> tuple[float, float]:
        """Divide screenshot-pixel coords by ``retina_scale`` to get points."""
        return sx / self._retina_scale, sy / self._retina_scale

    def __repr__(self) -> str:
        return (
            f"<CGEventInputSimulator "
            f"action_delay={self._action_delay} "
            f"post_to_pid={'available' if _HAS_POST_TO_PID else 'unavailable'} "
            f"pid={self._cached_pid}>"
        )
