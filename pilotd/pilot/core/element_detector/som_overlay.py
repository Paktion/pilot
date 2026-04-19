"""Set-of-Mark (SoM) overlay rendering and compact text serialisation.

The Set-of-Mark technique draws small numbered, colour-coded badges on
every interactable element in a screenshot, and pairs that image with a
numbered text listing. When both are passed to a vision model, the model
sees the same indices in the pixels and in the prompt, which dramatically
improves grounding accuracy compared to asking for raw pixel coordinates.

This module provides:

* :func:`render_som_overlay` -- return a copy of the image with badges
  drawn on top of each interactable element.
* :func:`to_compact_string` -- produce a numbered-list text description
  whose indices line up 1-to-1 with the badge numbers.

Colours are chosen by element type (buttons blue, text fields green,
links purple, icons orange, and so on) to give the model redundant
categorical signal on top of the numeric index.
"""

from __future__ import annotations

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from pilot.core.element_detector.screen_graph import ScreenGraph


# ---------------------------------------------------------------------------
# Badge colours per element type (RGB)
# ---------------------------------------------------------------------------

_SOM_COLORS: dict[str, tuple[int, int, int]] = {
    "button": (41, 98, 255),       # blue
    "text_field": (56, 142, 60),   # green
    "search_bar": (56, 142, 60),   # green (input variant)
    "link": (142, 36, 170),        # purple
    "icon": (255, 143, 0),         # orange
    "toggle": (0, 151, 167),       # teal
    "switch": (0, 151, 167),       # teal
    "slider": (0, 151, 167),       # teal
    "tab": (233, 30, 99),          # pink
    "cell": (121, 85, 72),         # brown
    "picker": (63, 81, 181),       # indigo
    "segmented_control": (63, 81, 181),  # indigo
    "image": (158, 158, 158),      # grey
    "label": (117, 117, 117),      # dark grey
    "nav_bar": (96, 125, 139),     # blue-grey
    "toolbar": (96, 125, 139),     # blue-grey
    "keyboard": (189, 189, 189),   # light grey
    "alert": (244, 67, 54),        # red
    "sheet": (244, 67, 54),        # red
}

_SOM_DEFAULT_COLOR: tuple[int, int, int] = (69, 90, 100)  # dark blue-grey

_SOM_BADGE_PADDING = 3
_SOM_FONT_SIZE = 12


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_badge_font() -> ImageFont.ImageFont:
    """Load a small font for badge labels, falling back gracefully."""
    try:
        return ImageFont.truetype("Arial", _SOM_FONT_SIZE)
    except (IOError, OSError):
        pass
    try:
        return ImageFont.truetype(
            "/System/Library/Fonts/SFNSMono.ttf", _SOM_FONT_SIZE
        )
    except (IOError, OSError):
        pass
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_som_overlay(
    image: PILImage.Image,
    screen_graph: ScreenGraph,
) -> PILImage.Image:
    """Draw numbered Set-of-Mark badges on each interactable element.

    Returns a new image that is a copy of *image* with small coloured
    badges at the top-left corner of every interactable element's
    bounding box. Badge colour is determined by element type (buttons
    blue, text fields green, links purple, icons orange, etc.). A thin
    outline in the same colour is drawn around the element as well.

    When paired with :func:`to_compact_string`, the model sees numbered
    elements in both the image and the text prompt, which gives it a
    grounded mapping from badge number back to a concrete element.

    Parameters
    ----------
    image : PIL.Image.Image
        The original screenshot.
    screen_graph : ScreenGraph
        The detected element graph whose interactable elements will be
        annotated.

    Returns
    -------
    PIL.Image.Image
        A new image with badges drawn on top.
    """
    annotated = image.copy().convert("RGBA")
    overlay = PILImage.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _load_badge_font()

    interactables = [el for el in screen_graph.elements if el.interactable]

    for mark_num, el in enumerate(interactables, start=1):
        colour = _SOM_COLORS.get(el.element_type, _SOM_DEFAULT_COLOR)
        label = str(mark_num)

        # Measure the label so the badge can size itself
        bbox = font.getbbox(label)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        badge_w = text_w + 2 * _SOM_BADGE_PADDING + 4
        badge_h = text_h + 2 * _SOM_BADGE_PADDING + 2

        # Position badge at top-left of element bounding box
        bx = el.bounds.get("x", 0)
        by = el.bounds.get("y", 0)

        # Clamp badge into the image
        bx = max(0, min(bx, annotated.width - badge_w))
        by = max(0, min(by, annotated.height - badge_h))

        # Badge background (rounded rectangle)
        badge_rect = (bx, by, bx + badge_w, by + badge_h)
        draw.rounded_rectangle(
            badge_rect,
            radius=3,
            fill=colour + (220,),
            outline=(255, 255, 255, 200),
            width=1,
        )

        # Badge label
        text_x = bx + _SOM_BADGE_PADDING + 2
        text_y = by + _SOM_BADGE_PADDING
        draw.text((text_x, text_y), label, fill=(255, 255, 255, 255), font=font)

        # Thin outline around the element bounding box
        el_x = el.bounds.get("x", 0)
        el_y = el.bounds.get("y", 0)
        el_w = el.bounds.get("width", 0)
        el_h = el.bounds.get("height", 0)
        outline_rect = (el_x, el_y, el_x + el_w, el_y + el_h)
        draw.rectangle(outline_rect, outline=colour + (140,), width=2)

    annotated = PILImage.alpha_composite(annotated, overlay)
    return annotated.convert("RGB")


# ---------------------------------------------------------------------------
# Compact numbered listing
# ---------------------------------------------------------------------------

def to_compact_string(screen_graph: ScreenGraph) -> str:
    """Produce a numbered element listing that matches the SoM badges.

    Each interactable element gets a sequential number that lines up with
    the badge drawn by :func:`render_som_overlay`. Non-interactable
    elements are listed below without a number so the model has full
    context but knows they cannot be acted upon.

    Example output::

        Screen: Messages (chat, keyboard=true)
        [1] button "Send" (234, 567) 60x32
        [2] text_field "Search..." (100, 200) 300x44
        [3] icon role=back_button (40, 66) 44x32
        Other:
          - label "Messages" (200, 30) 120x24

    Parameters
    ----------
    screen_graph : ScreenGraph
        The detected element graph.

    Returns
    -------
    str
        Compact text representation indexed by SoM number.
    """
    parts: list[str] = []

    # Header
    kb = "keyboard=true" if screen_graph.has_keyboard else "keyboard=false"
    modal = ", modal=true" if screen_graph.has_modal else ""
    parts.append(
        f"Screen: {screen_graph.app_name or 'Unknown'} "
        f"({screen_graph.screen_type}, {kb}{modal})"
    )

    mark_num = 0
    non_interactive: list[str] = []

    for el in screen_graph.elements:
        text_part = ""
        if el.text:
            display = el.text if len(el.text) <= 40 else el.text[:37] + "..."
            text_part = f' "{display}"'

        role_part = f" role={el.semantic_role}" if el.semantic_role else ""

        cx, cy = el.center
        bw = el.bounds.get("width", 0)
        bh = el.bounds.get("height", 0)
        geom = f"({cx}, {cy}) {bw}x{bh}"

        if el.interactable:
            mark_num += 1
            parts.append(
                f"[{mark_num}] {el.element_type}{text_part}{role_part} {geom}"
            )
        else:
            non_interactive.append(
                f"  - {el.element_type}{text_part}{role_part} {geom}"
            )

    if non_interactive:
        parts.append("Other:")
        parts.extend(non_interactive)

    return "\n".join(parts)


__all__ = ["render_som_overlay", "to_compact_string"]
