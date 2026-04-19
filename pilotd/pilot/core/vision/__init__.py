"""
Vision agent — Anthropic Claude multimodal client with tool-use action parsing.

The module is split so no file crosses the 400-line soft cap:

* ``actions``       — the action dataclasses + ``AgentResponse`` container
* ``json_extract``  — JSON-extraction fallbacks used by the legacy JSON path
* ``tools``         — Anthropic tool-use schema definitions
* ``agent``         — the ``VisionAgent`` class
"""

from pilot.core.vision.actions import (
    ActionType,
    AgentResponse,
    ClickAction,
    DoneAction,
    KeyAction,
    LowConfidenceError,
    SwipeAction,
    TypeAction,
    WaitAction,
)
from pilot.core.vision.agent import VisionAgent

__all__ = [
    "ActionType",
    "AgentResponse",
    "ClickAction",
    "DoneAction",
    "KeyAction",
    "LowConfidenceError",
    "SwipeAction",
    "TypeAction",
    "VisionAgent",
    "WaitAction",
]
