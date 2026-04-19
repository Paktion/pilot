"""Action dataclasses, ``AgentResponse``, and parse helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class ClickAction:
    """Tap a specific coordinate on the iPhone screen."""

    x: int
    y: int
    description: str
    type: str = "click"
    step_complete: bool = False


@dataclass
class TypeAction:
    """Type text into the currently focused field."""

    text: str
    type: str = "type"
    step_complete: bool = False


@dataclass
class SwipeAction:
    """Swipe from one point to another on the screen."""

    start_x: int
    start_y: int
    end_x: int
    end_y: int
    description: str
    type: str = "swipe"
    step_complete: bool = False


@dataclass
class KeyAction:
    """Press a keyboard key with optional modifiers."""

    key: str
    modifiers: list[str] | None = None
    type: str = "key"
    step_complete: bool = False


@dataclass
class WaitAction:
    """Wait for a specified duration before the next action."""

    seconds: float = 1.0
    type: str = "wait"
    step_complete: bool = False


@dataclass
class DoneAction:
    """Signal that the task has been completed."""

    summary: str
    type: str = "done"
    step_complete: bool = False


ActionType = Union[
    ClickAction, TypeAction, SwipeAction, KeyAction, WaitAction, DoneAction
]


@dataclass
class AgentResponse:
    """Full LLM response: reasoning, an action, and a confidence score."""

    thought: str
    action: ActionType
    confidence: float


class LowConfidenceError(Exception):
    """Raised when confidence falls below the configured threshold.

    The caller can inspect ``self.response`` to see the full ``AgentResponse``
    and decide how to proceed — ask for clarification, retry with a modified
    prompt, or execute the action anyway.
    """

    def __init__(self, message: str, response: AgentResponse) -> None:
        super().__init__(message)
        self.response = response


_ACTION_CONSTRUCTORS: dict[str, type] = {
    "click": ClickAction,
    "type": TypeAction,
    "swipe": SwipeAction,
    "key": KeyAction,
    "wait": WaitAction,
    "done": DoneAction,
}


def parse_action(data: dict) -> ActionType:
    """Instantiate the correct action dataclass from a raw dict.

    The ``type`` field selects the class; remaining keys are forwarded as
    kwargs. Unknown keys are silently dropped so the agent can include
    extra commentary without breaking parsing.
    """
    action_type = data.get("type")
    if action_type not in _ACTION_CONSTRUCTORS:
        raise ValueError(
            f"Unknown action type '{action_type}'. "
            f"Expected one of: {list(_ACTION_CONSTRUCTORS.keys())}"
        )
    cls = _ACTION_CONSTRUCTORS[action_type]
    valid_fields = {
        f.name for f in cls.__dataclass_fields__.values() if f.name != "type"
    }
    kwargs = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**kwargs)
