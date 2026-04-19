"""Prompts, plausibility checks, and single-element parsing helpers.

Extracted out of :mod:`pilot.core.element_detector.detector` so that the
detector module stays focused on orchestration and caching while the
prompt text and validation details live here.

Exports:

* :data:`DETECTION_PROMPT` -- the user-facing detection prompt with
  ``{width}`` / ``{height}`` placeholders.
* :data:`DETECTION_SYSTEM_PROMPT` -- the short system-message wrapper.
* :func:`validate_bounds_plausibility` -- reject obviously wrong boxes.
* :func:`parse_single_element` -- turn one dict from the model response
  into a validated :class:`UIElement`, or ``None`` if it is malformed.
"""

from __future__ import annotations

import logging
from typing import Any

from pilot.core.element_detector.ui_element import UIElement
from pilot.core.element_detector.vocab import (
    ELEMENT_TYPE_NORMALISATION,
    ELEMENT_TYPES,
    LARGE_BOX_ALLOWED_TYPES,
    SEMANTIC_ROLES,
    VALID_STATES,
)

logger = logging.getLogger("pilotd.elements")


# ---------------------------------------------------------------------------
# Detection prompt
# ---------------------------------------------------------------------------

DETECTION_PROMPT = """\
You are the UI element detection module of a mobile automation agent. You \
are looking at a screenshot of a mirrored phone screen.

Your job is to analyze this screenshot and return a **complete, structured \
inventory** of every visible UI element. This inventory is used to build a \
pseudo-accessibility tree for programmatic interaction.

## Instructions

1. **Identify the app and screen context** -- what app is this? What kind \
of screen (home screen, settings, chat view, browser, etc.)? How deep in \
the navigation stack are we?

2. **List EVERY visible UI element** -- buttons, text fields, labels, \
icons, toggles, sliders, tabs, navigation bars, table cells, images, \
links, search bars, keyboards, etc.

3. **For each element provide:**
   - ``id``: a short unique identifier (e.g. ``"btn_0"``, ``"text_3"``, \
``"cell_2"``)
   - ``type``: one of: button, text_field, label, icon, toggle, slider, \
tab, nav_bar, cell, image, link, search_bar, toolbar, status_bar, \
keyboard, section_header, switch, picker, segmented_control, \
progress_bar, container, alert, sheet
   - ``text``: the visible text content (null if no text, e.g. pure icon)
   - ``bounds``: ``{{"x": <int>, "y": <int>, "width": <int>, "height": \
<int>}}`` where (x,y) is the top-left corner in pixel coordinates relative \
to the screenshot
   - ``interactable``: true if the element can be tapped, typed into, \
toggled, or otherwise interacted with
   - ``state``: one of: "enabled", "disabled", "selected", "checked", \
"unchecked", "focused", null
   - ``parent_id``: the id of the containing element (null for top-level \
elements)
   - ``semantic_role``: a functional classification if applicable -- one \
of: back_button, close_button, submit_button, send_button, search_field, \
cancel_button, done_button, edit_button, delete_button, share_button, \
more_options, navigation_title, tab_selected, tab_unselected, \
message_input, compose_button, or null

4. **Determine element hierarchy** -- group elements under their visual \
containers (nav bars, cells, toolbars). Set ``parent_id`` to the \
containing element's id.

5. **Screen metadata:**
   - ``has_keyboard``: is a soft keyboard visible?
   - ``has_modal``: is a modal dialog, alert, or action sheet showing?
   - ``navigation_depth``: estimated depth in the nav stack (0 = root/home)
   - ``status_bar``: parse the status bar if visible: time, battery level, \
signal bars, wifi indicator

## Output Format

Respond with ONLY valid JSON, no markdown fences, no commentary:

{{
  "app_name": "<string or null>",
  "screen_type": "<string>",
  "navigation_depth": <int>,
  "has_keyboard": <bool>,
  "has_modal": <bool>,
  "status_bar": {{"time": "<str>", "battery": "<str>", "signal": "<str>", "wifi": "<str>"}} or null,
  "elements": [
    {{
      "id": "<string>",
      "type": "<string>",
      "text": "<string or null>",
      "bounds": {{"x": <int>, "y": <int>, "width": <int>, "height": <int>}},
      "interactable": <bool>,
      "state": "<string or null>",
      "parent_id": "<string or null>",
      "semantic_role": "<string or null>"
    }},
    ...
  ]
}}

## Important

- Be EXHAUSTIVE -- list every element you can see, even small icons.
- Bounding boxes must be as accurate as possible -- they drive click \
targeting.
- Prefer specific types over generic ones (use "toggle" not "button" for \
toggle switches).
- The screenshot dimensions are {width}x{height} pixels -- all coordinates \
must fall within this range.
- Do NOT include elements that are completely obscured or fully off-screen.
- If the keyboard is visible, include it as a single "keyboard" element -- \
do NOT enumerate individual keys.
"""


DETECTION_SYSTEM_PROMPT = (
    "You are the UI element detection module of a mobile automation "
    "agent. Your job is to analyze screenshots and produce structured "
    "JSON inventories of all visible UI elements. Respond with ONLY "
    "valid JSON -- no markdown fences, no commentary."
)


# ---------------------------------------------------------------------------
# Bounds plausibility
# ---------------------------------------------------------------------------

def validate_bounds_plausibility(
    bounds: dict[str, int],
    img_width: int,
    img_height: int,
    element_type: str,
) -> str | None:
    """Check whether a bounding box is plausible.

    Returns a human-readable rejection reason, or ``None`` if the bounds
    are acceptable. Rejection criteria:

    * Zero or negative dimensions.
    * Bounding box lies entirely outside the screen.
    * Area exceeds 80 % of the screen (unless the element type is
      allowed to span the screen, e.g. ``scroll_view``, ``keyboard``).
    * Width and height both smaller than 2 px (likely noise).
    """
    bx = bounds.get("x", 0)
    by = bounds.get("y", 0)
    bw = bounds.get("width", 0)
    bh = bounds.get("height", 0)

    if bw <= 0 or bh <= 0:
        return f"non-positive dimensions ({bw}x{bh})"

    if bx >= img_width or by >= img_height:
        return (
            f"top-left corner ({bx},{by}) is outside "
            f"screen bounds ({img_width}x{img_height})"
        )
    if bx + bw <= 0 or by + bh <= 0:
        return "bounding box ends before screen origin"

    if bw < 2 and bh < 2:
        return f"too small ({bw}x{bh})"

    screen_area = img_width * img_height
    box_area = bw * bh
    if screen_area > 0 and element_type not in LARGE_BOX_ALLOWED_TYPES:
        if box_area > 0.8 * screen_area:
            pct = 100.0 * box_area / screen_area
            return (
                f"area ({bw}x{bh} = {box_area}px) is {pct:.0f}% of screen "
                f"-- implausibly large for type {element_type!r}"
            )

    return None


# ---------------------------------------------------------------------------
# Single-element parsing
# ---------------------------------------------------------------------------

def parse_single_element(
    raw: dict[str, Any],
    index: int,
    img_width: int,
    img_height: int,
    seen_ids: set[str],
) -> UIElement | None:
    """Parse and validate one element dict from the model response.

    Returns ``None`` when the element is malformed beyond repair.

    Parameters
    ----------
    raw
        One entry from the ``"elements"`` list in the model's JSON
        response.
    index
        Positional index within the response, used to synthesise a
        fallback ID when the model omits one.
    img_width, img_height
        Screenshot dimensions in pixels, used to clamp bounding boxes
        and evaluate plausibility.
    seen_ids
        Set of IDs already claimed by other elements. Mutates nothing;
        the caller is responsible for adding the returned element's ID
        after a successful parse.
    """
    # -- ID -------------------------------------------------------------
    el_id = str(raw.get("id", f"el_{index}")).strip()
    if not el_id:
        el_id = f"el_{index}"
    if el_id in seen_ids:
        el_id = f"{el_id}_{index}"

    # -- Type -----------------------------------------------------------
    el_type = str(raw.get("type", "label")).lower().strip()
    if el_type not in ELEMENT_TYPES:
        el_type = ELEMENT_TYPE_NORMALISATION.get(el_type, "label")

    # -- Text -----------------------------------------------------------
    text = raw.get("text")
    if text is not None:
        text = str(text).strip()
        if not text:
            text = None

    # -- Bounds ---------------------------------------------------------
    bounds_raw = raw.get("bounds", {})
    if not isinstance(bounds_raw, dict):
        bounds_raw = {}
    try:
        bx = max(0, min(int(bounds_raw.get("x", 0)), img_width - 1))
        by = max(0, min(int(bounds_raw.get("y", 0)), img_height - 1))
        bw = max(1, int(bounds_raw.get("width", 50)))
        bh = max(1, int(bounds_raw.get("height", 30)))
    except (TypeError, ValueError):
        bx, by, bw, bh = 0, 0, 50, 30

    if bx + bw > img_width:
        bw = img_width - bx
    if by + bh > img_height:
        bh = img_height - by

    bounds = {"x": bx, "y": by, "width": bw, "height": bh}

    rejection = validate_bounds_plausibility(
        bounds, img_width, img_height, el_type
    )
    if rejection is not None:
        logger.debug(
            "Rejecting element %s (%s): %s", el_id, el_type, rejection
        )
        return None

    center = (bx + bw // 2, by + bh // 2)

    # -- Interactable ---------------------------------------------------
    interactable = bool(raw.get("interactable", False))

    # -- State ----------------------------------------------------------
    state = raw.get("state")
    if state is not None:
        state = str(state).lower().strip()
        if state not in VALID_STATES:
            state = "enabled" if interactable else None

    # -- Semantic role --------------------------------------------------
    role = raw.get("semantic_role")
    if role is not None:
        role = str(role).lower().strip().replace(" ", "_")
        if role not in SEMANTIC_ROLES:
            role_alt = role.replace("-", "_")
            role = role_alt if role_alt in SEMANTIC_ROLES else None

    # -- Parent ---------------------------------------------------------
    parent_id = raw.get("parent_id")
    if parent_id is not None:
        parent_id = str(parent_id).strip()
        if not parent_id:
            parent_id = None

    # -- Confidence (inferred from data quality) ------------------------
    confidence = 1.0
    if not bounds_raw:
        confidence *= 0.5
    if text is None and el_type == "label":
        confidence *= 0.7
    if bw < 5 or bh < 5:
        confidence *= 0.6

    return UIElement(
        id=el_id,
        element_type=el_type,
        text=text,
        bounds=bounds,
        center=center,
        confidence=confidence,
        interactable=interactable,
        state=state,
        parent_id=parent_id,
        children=[],
        semantic_role=role,
    )


__all__ = [
    "DETECTION_PROMPT",
    "DETECTION_SYSTEM_PROMPT",
    "validate_bounds_plausibility",
    "parse_single_element",
]
