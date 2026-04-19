"""Vocabularies used by the element detector.

This module centralises the constant lists that describe the universe of UI
element types, semantic roles, and screen types the detector expects to see
in a screenshot. They are consumed by:

* The detection prompt (enumerated in the system message so the model knows
  the exact vocabulary).
* The response parser (used to validate, normalise, and map unknown tokens
  back into the supported set).
* Downstream lookup helpers on ``ScreenGraph``.

Centralising the vocabulary here means the prompt, the parser, and the
queries can never drift out of sync.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Element type vocabulary
# ---------------------------------------------------------------------------

ELEMENT_TYPES: set[str] = {
    "button",
    "text_field",
    "label",
    "icon",
    "toggle",
    "slider",
    "tab",
    "nav_bar",
    "cell",
    "image",
    "link",
    "search_bar",
    "toolbar",
    "status_bar",
    "keyboard",
    "section_header",
    "switch",
    "picker",
    "segmented_control",
    "progress_bar",
    "map",
    "web_view",
    "scroll_view",
    "alert",
    "sheet",
    "container",
}


# ---------------------------------------------------------------------------
# Semantic role vocabulary
# ---------------------------------------------------------------------------

SEMANTIC_ROLES: set[str] = {
    "back_button",
    "close_button",
    "submit_button",
    "send_button",
    "search_field",
    "cancel_button",
    "done_button",
    "edit_button",
    "delete_button",
    "share_button",
    "more_options",
    "navigation_title",
    "tab_selected",
    "tab_unselected",
    "message_input",
    "compose_button",
    "refresh_button",
    "settings_button",
    "profile_button",
    "home_indicator",
    "notification",
    "badge",
    "toggle_on",
    "toggle_off",
    "volume_slider",
    "brightness_slider",
    "media_play",
    "media_pause",
    "media_next",
    "media_prev",
}


# ---------------------------------------------------------------------------
# Screen-type vocabulary
# ---------------------------------------------------------------------------

SCREEN_TYPES: set[str] = {
    "home_screen",
    "app_list",
    "settings",
    "chat",
    "browser",
    "keyboard_visible",
    "dialog",
    "lock_screen",
    "notification_center",
    "control_center",
    "search",
    "media_player",
    "photo_gallery",
    "map",
    "email",
    "social_feed",
    "form",
    "onboarding",
    "loading",
    "error",
    "unknown",
}


# ---------------------------------------------------------------------------
# Natural-language aliases for semantic roles
# ---------------------------------------------------------------------------

# Human phrasings that a caller might use to describe a role. Used by the
# fuzzy element resolver to turn "the back arrow" into ``back_button``.
ROLE_ALIASES: dict[str, list[str]] = {
    "back_button": [
        "back",
        "go back",
        "previous",
        "return",
        "navigate back",
        "< back",
        "chevron left",
    ],
    "close_button": [
        "close",
        "dismiss",
        "x button",
        "close button",
    ],
    "submit_button": [
        "submit",
        "ok",
        "confirm",
        "apply",
        "save",
    ],
    "send_button": [
        "send",
        "send message",
        "send button",
        "arrow up",
        "paper plane",
    ],
    "search_field": [
        "search",
        "search bar",
        "search field",
        "search box",
        "find",
    ],
    "cancel_button": [
        "cancel",
        "nevermind",
        "abort",
    ],
    "done_button": [
        "done",
        "finish",
        "complete",
    ],
    "edit_button": [
        "edit",
        "modify",
        "change",
    ],
    "delete_button": [
        "delete",
        "remove",
        "trash",
        "bin",
    ],
    "share_button": [
        "share",
        "share button",
        "export",
    ],
    "more_options": [
        "more",
        "options",
        "menu",
        "three dots",
        "ellipsis",
        "...",
    ],
    "navigation_title": [
        "title",
        "header",
        "page title",
        "screen title",
    ],
    "message_input": [
        "message field",
        "text input",
        "compose",
        "type here",
        "message box",
        "imessage",
    ],
    "compose_button": [
        "compose",
        "new message",
        "write",
        "create",
        "new",
    ],
    "tab_selected": [
        "active tab",
        "selected tab",
        "current tab",
    ],
    "tab_unselected": [
        "tab",
        "inactive tab",
    ],
}


# ---------------------------------------------------------------------------
# Natural-language aliases for element types
# ---------------------------------------------------------------------------

TYPE_ALIASES: dict[str, list[str]] = {
    "button": ["button", "btn", "tap target"],
    "text_field": [
        "text field",
        "input",
        "text input",
        "field",
        "text box",
        "input field",
    ],
    "label": ["label", "text", "static text"],
    "icon": ["icon", "glyph", "symbol"],
    "toggle": ["toggle", "switch"],
    "slider": ["slider", "range", "scrubber"],
    "tab": ["tab", "tab item"],
    "nav_bar": [
        "navigation bar",
        "nav bar",
        "navbar",
        "header bar",
        "top bar",
    ],
    "cell": ["cell", "row", "list item", "table cell"],
    "image": ["image", "photo", "picture", "thumbnail"],
    "link": ["link", "hyperlink", "url"],
    "search_bar": ["search bar", "search"],
    "keyboard": ["keyboard", "keypad"],
}


# ---------------------------------------------------------------------------
# Types allowed to span most of the screen
# ---------------------------------------------------------------------------

# Element types whose bounding boxes may legitimately cover a large fraction
# of the display. The plausibility check uses this set to avoid rejecting
# full-screen containers, sheets, or the soft keyboard.
LARGE_BOX_ALLOWED_TYPES: set[str] = {
    "scroll_view",
    "container",
    "keyboard",
    "web_view",
    "map",
    "nav_bar",
    "toolbar",
    "status_bar",
    "sheet",
    "alert",
}


# ---------------------------------------------------------------------------
# Common element-type aliases from the model
# ---------------------------------------------------------------------------

# Maps common variations that the model might emit back to the canonical
# ``ELEMENT_TYPES`` vocabulary.
ELEMENT_TYPE_NORMALISATION: dict[str, str] = {
    "textfield": "text_field",
    "text": "label",
    "searchbar": "search_bar",
    "navbar": "nav_bar",
    "navbutton": "button",
    "tabbar": "toolbar",
    "tableviewcell": "cell",
    "collectionviewcell": "cell",
    "statictext": "label",
    "securetext": "text_field",
    "input": "text_field",
}


# ---------------------------------------------------------------------------
# Valid element states
# ---------------------------------------------------------------------------

VALID_STATES: set[str] = {
    "enabled",
    "disabled",
    "selected",
    "checked",
    "unchecked",
    "focused",
}


__all__ = [
    "ELEMENT_TYPES",
    "SEMANTIC_ROLES",
    "SCREEN_TYPES",
    "ROLE_ALIASES",
    "TYPE_ALIASES",
    "LARGE_BOX_ALLOWED_TYPES",
    "ELEMENT_TYPE_NORMALISATION",
    "VALID_STATES",
]
