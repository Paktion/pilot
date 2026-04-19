"""Anthropic tool-use definitions + name→action mapping."""

from __future__ import annotations


_STEP_COMPLETE_PROP = {
    "type": "boolean",
    "description": (
        "Set to true when the current sub-task is finished "
        "and you are ready for the next step"
    ),
    "default": False,
}


TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "tap",
        "description": (
            "Tap at a specific coordinate on the iPhone screen. "
            "Use this for pressing buttons, icons, links, or any tappable element."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate in pixels"},
                "y": {"type": "integer", "description": "Y coordinate in pixels"},
                "thought": {
                    "type": "string",
                    "description": "Chain-of-thought reasoning for this action",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence (0.0-1.0)",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what is being tapped",
                },
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["x", "y", "thought", "confidence", "description"],
        },
    },
    {
        "name": "swipe",
        "description": (
            "Swipe from one point to another. Use for scrolling, dismissing, "
            "or any drag gesture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "description": {"type": "string"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": [
                "start_x", "start_y", "end_x", "end_y",
                "thought", "confidence", "description",
            ],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Type text into the focused input field. Ensure a text field is "
            "focused before calling."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["text", "thought", "confidence"],
        },
    },
    {
        "name": "press_key",
        "description": (
            "Press a keyboard key, optionally with modifiers. "
            "Common: enter, escape, backspace, tab, home."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "modifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "command, shift, option, control",
                },
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["key", "thought", "confidence"],
        },
    },
    {
        "name": "wait",
        "description": (
            "Pause before the next step. Use after actions that trigger "
            "animations or loading."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "default": 1.0},
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["thought", "confidence"],
        },
    },
    {
        "name": "done",
        "description": "Signal that the task has been fully completed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["summary", "thought", "confidence"],
        },
    },
]


TOOL_NAME_TO_ACTION_TYPE: dict[str, str] = {
    "tap": "click",
    "swipe": "swipe",
    "type_text": "type",
    "press_key": "key",
    "wait": "wait",
    "done": "done",
}
