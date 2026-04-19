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
            "Use this for pressing buttons, icons, links, or any tappable element. "
            "Prefer tap_text when the target has readable label text — "
            "it's more robust to layout shifts between runs."
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
        "name": "tap_text",
        "description": (
            "Tap the on-screen element that best matches a visible text label. "
            "Far more robust than raw tap when the target has readable text — "
            "Pilot will re-locate the label via vision before clicking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Visible label to tap (exact or close synonym).",
                },
                "prefer": {
                    "type": "string",
                    "enum": ["first", "last"],
                    "description": "When multiple matches exist, pick the first or last.",
                },
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["text", "thought", "confidence"],
        },
    },
    {
        "name": "swipe",
        "description": (
            "Swipe from one point to another. Use for scrolling, dismissing, "
            "or any drag gesture. To scroll, swipe in the direction opposite "
            "to the content motion you want (swipe up to scroll down)."
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
        "name": "long_press",
        "description": (
            "Press and hold at a coordinate for a duration. Triggers iOS "
            "context menus, drag handles, edit modes, haptic previews."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration": {
                    "type": "number",
                    "description": "Hold time in seconds (default 1.0).",
                    "default": 1.0,
                },
                "description": {"type": "string"},
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["x", "y", "thought", "confidence"],
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
            "Common: enter, escape, backspace, tab."
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
        "name": "press_home",
        "description": (
            "Return to the iPhone home screen. Useful when you need to leave "
            "an app, cancel a modal, or restart navigation from a known state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["thought", "confidence"],
        },
    },
    {
        "name": "launch_app",
        "description": (
            "Open an app by name via Spotlight. Use this instead of tapping a "
            "home-screen icon whose position you don't already know. Returns "
            "to the app's main screen after launch."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Exact app name as it appears in iOS (e.g. 'Weather', 'Starbucks').",
                },
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["app_name", "thought", "confidence"],
        },
    },
    {
        "name": "extract",
        "description": (
            "Ask a visual-QA question about the current screen. The answer is "
            "appended to the conversation history so subsequent turns can use "
            "it. Use for reading prices, balances, statuses, etc. without "
            "consuming the Done slot."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Specific question a vision model can answer from the screenshot.",
                },
                "expected_type": {
                    "type": "string",
                    "enum": ["int", "float", "string", "bool"],
                    "default": "string",
                },
                "hint": {
                    "type": "string",
                    "description": "Optional location hint ('near the top card', 'below Subtotal').",
                },
                "thought": {"type": "string"},
                "confidence": {"type": "number"},
                "step_complete": _STEP_COMPLETE_PROP,
            },
            "required": ["question", "thought", "confidence"],
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


# Tools usable for the "find + click by coords" locate path. Deliberately
# excludes tap_text, launch_app, long_press, press_home, extract — those are
# semantic-level tools that would recursively call the same locate path.
_LOCATE_TOOL_NAMES = {"tap", "swipe", "wait", "done"}

LOCATE_TOOL_DEFINITIONS: list[dict] = [
    t for t in TOOL_DEFINITIONS if t["name"] in _LOCATE_TOOL_NAMES
]


TOOL_NAME_TO_ACTION_TYPE: dict[str, str] = {
    "tap": "click",
    "tap_text": "tap_text",
    "swipe": "swipe",
    "long_press": "long_press",
    "type_text": "type",
    "press_key": "key",
    "press_home": "press_home",
    "launch_app": "launch_app",
    "extract": "extract",
    "wait": "wait",
    "done": "done",
}
