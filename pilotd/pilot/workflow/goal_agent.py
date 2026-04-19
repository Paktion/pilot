"""
GoalAgent — observe-think-act loop driven by a natural-language goal.

The engine invokes this for ``goal:`` steps. The agent:
  1. Captures a screenshot
  2. Asks Claude (tool-use mode) for the next action given goal + history
  3. Dispatches the action to the controller (tap / swipe / type / wait)
  4. Records stuck-loop heuristics (3-window, 20px) and home-recovers when pinned
  5. Stops on DoneAction, budget exhaustion, or lock-screen signal

Emits live events the UI can render: goal_thinking / goal_action / goal_observed.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from pilot.core.controller import AnthropicAuthError, MirroringLockedError, _looks_locked
from pilot.core.vision import (
    ActionType,
    ClickAction,
    DoneAction,
    KeyAction,
    SwipeAction,
    TypeAction,
    VisionAgent,
    WaitAction,
)

log = logging.getLogger("pilotd.goal_agent")

_STUCK_LOOKBACK = 3
_STUCK_COORD_THRESHOLD = 20.0
_DEFAULT_BUDGET = 15
_MAX_WAIT_SECONDS = 15.0


@dataclass
class GoalResult:
    status: str  # 'success' | 'failed' | 'aborted'
    summary: str
    captured: Any = None
    steps_taken: int = 0
    history: list[dict] = field(default_factory=list)


class GoalAgent:
    """Drives the phone toward a natural-language goal."""

    def __init__(
        self,
        *,
        controller: Any,  # AgentController — typed Any to avoid import cycle
        vision: VisionAgent,
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        self._controller = controller
        self._vision = vision
        self._emit = emit

    def pursue(
        self,
        *,
        goal: str,
        budget_steps: int = _DEFAULT_BUDGET,
        capture_var: str | None = None,
    ) -> GoalResult:
        """Run the observe-think-act loop until goal met or budget exhausted."""
        self._emit({
            "event": "goal_start",
            "goal": goal,
            "budget": budget_steps,
        })

        history: list[dict] = []
        recent_actions: deque[tuple[str, int, int]] = deque(maxlen=_STUCK_LOOKBACK)
        steps_taken = 0

        for step_idx in range(budget_steps):
            try:
                ss = self._controller.screenshot()
            except Exception as exc:
                log.warning("goal: screenshot failed: %s", exc)
                time.sleep(1.0)
                continue

            # Stream the screenshot to the live UI so the user sees what the
            # model sees. Emit as a low-res JPEG (~20KB) to avoid blasting
            # the socket with raw PNG on every tick.
            self._emit_screenshot(ss, step_idx)

            # Actions taken so far count — helps the prompt enforce navigation
            # discipline when the goal has explicit steps.
            actions_so_far = sum(
                1 for h in history if h.get("role") == "assistant"
            )
            task_prompt = (
                f"GOAL:\n{goal}\n\n"
                f"This is turn {step_idx + 1}. "
                f"Actions performed so far: {actions_so_far}.\n\n"
                "Emit exactly ONE tool call per turn.\n\n"
                "CRITICAL NAVIGATION RULES:\n"
                "- If the goal text contains explicit navigation steps "
                "('tap X', 'scroll until Y', 'open Z'), you MUST execute "
                "them in order. Reading a widget or summary card that "
                "looks like the answer does NOT satisfy a goal that asks "
                "you to navigate INTO an app. Home-screen widgets, lock-"
                "screen balances, and 'For You' favorites tiles may be "
                "stale or zeroed — they are NEVER an acceptable Done value "
                "when the goal asked you to navigate to a specific section.\n"
                "- Only call Done AFTER the navigation path was executed AND "
                "the target value is visible on the final destination screen. "
                "Include the captured value verbatim in the summary.\n"
                "- If the screen shows an auth/lock wall, call Done with "
                "summary='BLOCKED_BY_AUTH'.\n"
                "- If after several turns the path is clearly unreachable, "
                "call Done with summary='NOT_REACHABLE: <why>'."
            )

            try:
                response = self._vision.analyze_screen(
                    ss, task=task_prompt, history=history,
                )
            except Exception as exc:
                # Re-raise auth errors so the engine surfaces them clearly.
                from pilot.core.controller import _raise_if_auth
                _raise_if_auth(exc)
                log.warning("goal: vision call failed: %s", exc)
                time.sleep(1.0)
                continue

            action = response.action
            thought = (response.thought or "")[:120]
            action_kind = type(action).__name__
            self._emit({
                "event": "goal_thinking",
                "step": step_idx,
                "action": action_kind,
                "confidence": round(response.confidence, 2),
                "thought": thought,
            })

            # Short-circuit if Claude reports the lock screen.
            if _looks_locked(response.thought or ""):
                raise MirroringLockedError(
                    "iPhone Mirroring is showing its lock/authentication screen. "
                    "Unlock the iPhone and wait for Mirroring to reconnect."
                )

            # Terminal: Done
            if isinstance(action, DoneAction):
                summary = action.summary or thought
                captured = _parse_captured(summary) if capture_var else None
                steps_taken = step_idx + 1
                self._emit({
                    "event": "goal_observed",
                    "step": step_idx,
                    "summary": summary,
                    "captured": captured,
                })
                upper_summary = summary.strip().upper()
                if upper_summary.startswith("BLOCKED_BY_AUTH"):
                    return GoalResult(
                        status="failed",
                        summary="blocked by auth/lock screen",
                        steps_taken=steps_taken,
                        history=history,
                    )
                if upper_summary.startswith("NOT_REACHABLE"):
                    # The agent explicitly declared the path unreachable.
                    # That's a failure, not a success — don't let it poison
                    # downstream steps with a garbage captured value.
                    return GoalResult(
                        status="failed",
                        summary=summary,
                        steps_taken=steps_taken,
                        history=history,
                    )
                return GoalResult(
                    status="success",
                    summary=summary,
                    captured=captured,
                    steps_taken=steps_taken,
                    history=history,
                )

            # Stuck-loop detection for clickable actions.
            if isinstance(action, ClickAction):
                sig = ("click", int(action.x), int(action.y))
                if _is_stuck(recent_actions, sig):
                    self._emit({
                        "event": "goal_stuck",
                        "step": step_idx,
                        "recovery": "home",
                    })
                    try:
                        self._controller._inputs.home()
                        time.sleep(1.0)
                    except Exception:
                        pass
                    recent_actions.clear()
                    history.append({
                        "role": "user",
                        "content": (
                            "You seemed stuck tapping the same coordinates. "
                            "I pressed Home to reset; re-observe and try a different approach."
                        ),
                    })
                    continue
                recent_actions.append(sig)
            elif isinstance(action, SwipeAction):
                recent_actions.append(
                    ("swipe", int(action.start_x), int(action.start_y))
                )

            # Dispatch the action via the controller's low-level primitives.
            try:
                self._dispatch(action)
            except MirroringLockedError:
                raise
            except Exception as exc:
                log.warning("goal: action dispatch failed: %s", exc)
                self._emit({
                    "event": "goal_action_failed",
                    "step": step_idx,
                    "error": str(exc)[:160],
                })
                history.append({
                    "role": "user",
                    "content": f"The {action_kind} failed: {exc}. Try a different approach.",
                })
                continue

            self._emit({
                "event": "goal_action",
                "step": step_idx,
                "kind": action_kind,
                "detail": _describe_action(action),
            })

            # Feed the action back into history so the next turn sees context.
            history.append(VisionAgent.build_history_entry(
                role="assistant",
                thought=thought,
                action=action,
                confidence=response.confidence,
            ))

            steps_taken = step_idx + 1

        self._emit({"event": "goal_exhausted", "budget": budget_steps})
        return GoalResult(
            status="failed",
            summary=f"budget of {budget_steps} steps exhausted without reaching goal",
            steps_taken=steps_taken,
            history=history,
        )

    def _dispatch(self, action: ActionType) -> None:
        """Send the LLM's action to the right controller primitive."""
        if isinstance(action, ClickAction):
            # Convert pixel coords to phone-screen points, same path as tap_text.
            ss = self._controller.screenshot()
            px, py = self._controller._to_phone_points(action.x, action.y, ss)
            self._controller._inputs.click(px, py)
        elif isinstance(action, SwipeAction):
            ss = self._controller.screenshot()
            sx, sy = self._controller._to_phone_points(action.start_x, action.start_y, ss)
            ex, ey = self._controller._to_phone_points(action.end_x, action.end_y, ss)
            self._controller._inputs.swipe(sx, sy, ex, ey)
        elif isinstance(action, TypeAction):
            self._controller._inputs.type_text(action.text)
        elif isinstance(action, KeyAction):
            self._controller._inputs.press_key(action.key, modifiers=action.modifiers)
        elif isinstance(action, WaitAction):
            time.sleep(min(float(action.seconds), _MAX_WAIT_SECONDS))
        # DoneAction handled in the outer loop


    def _emit_screenshot(self, image, step_idx: int) -> None:
        """Stream a JPEG thumbnail of the current screen to the UI."""
        try:
            import base64, io
            img = image.copy()
            img.thumbnail((320, 640))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            self._emit({
                "event": "screenshot",
                "image_b64": base64.standard_b64encode(buf.getvalue()).decode("ascii"),
                "meta": {"kind": "goal", "step": step_idx},
            })
        except Exception:
            log.debug("goal: screenshot emit failed", exc_info=True)


def _is_stuck(recent: deque[tuple[str, int, int]], sig: tuple[str, int, int]) -> bool:
    if len(recent) < _STUCK_LOOKBACK - 1:
        return False
    kind, x, y = sig
    for prev_kind, px, py in recent:
        if prev_kind != kind:
            return False
        if abs(px - x) > _STUCK_COORD_THRESHOLD or abs(py - y) > _STUCK_COORD_THRESHOLD:
            return False
    return True


def _describe_action(action: ActionType) -> str:
    if isinstance(action, ClickAction):
        return f"tap ({action.x}, {action.y}) — {action.description}"
    if isinstance(action, SwipeAction):
        return f"swipe ({action.start_x},{action.start_y})→({action.end_x},{action.end_y})"
    if isinstance(action, TypeAction):
        return f"type {action.text[:40]!r}"
    if isinstance(action, KeyAction):
        mods = "+".join(action.modifiers or [])
        return f"key {mods + '+' if mods else ''}{action.key}"
    if isinstance(action, WaitAction):
        return f"wait {action.seconds}s"
    if isinstance(action, DoneAction):
        return f"done — {action.summary[:80]}"
    return type(action).__name__


def _parse_captured(summary: str) -> Any:
    """Attempt to pull a numeric answer from the Done summary."""
    import re
    m = re.search(r"[-+]?\d*\.?\d+", summary)
    if m:
        try:
            s = m.group(0)
            return float(s) if "." in s else int(s)
        except ValueError:
            return summary
    return summary


__all__ = ["GoalAgent", "GoalResult"]
