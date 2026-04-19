"""
Session export helpers: HTML (self-contained), JSON (data dump), GIF
(animated replay).

Each function takes a :class:`SessionDetail` plus the session directory on
disk and writes the artefact into the same directory. Screenshots are
read from the session directory and embedded (HTML / GIF) or referenced
by relative path (JSON).
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import PIL.Image

from pilot.core.session._html_assets import CSS as _CSS
from pilot.core.session._html_assets import HTML_SHELL as _HTML_SHELL
from pilot.core.session._html_assets import JS as _JS

if TYPE_CHECKING:
    from pilot.core.session.manager import SessionDetail

logger = logging.getLogger("pilotd.session")


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def export_json(detail: "SessionDetail", session_dir: Path) -> str:
    """Export the session as a single JSON file and return its path."""
    output_path = session_dir / f"export_{detail.session_id}.json"

    export_data = {
        "session_id": detail.session_id,
        "task": detail.task,
        "status": detail.status,
        "model": detail.model,
        "steps_count": detail.steps,
        "duration": detail.duration,
        "created_at": detail.created_at,
        "metadata": detail.metadata,
        "steps": [asdict(s) for s in detail.steps_data],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, default=str)

    logger.info(
        "Exported session %s as JSON: %s", detail.session_id, output_path,
    )
    return str(output_path)


# ---------------------------------------------------------------------------
# GIF
# ---------------------------------------------------------------------------


def export_gif(detail: "SessionDetail", session_dir: Path) -> str:
    """Export the session screenshots as an animated GIF.

    Each frame is resized to a max width of 800 px (preserving aspect
    ratio) before assembly. Raises ``ValueError`` if no valid
    screenshots were found.
    """
    gif_max_width = 800
    frames: list[PIL.Image.Image] = []

    for step in detail.steps_data:
        img_path = session_dir / step.screenshot_path
        if not img_path.exists():
            continue
        try:
            img = PIL.Image.open(img_path).copy()
            # GIF does not support RGBA well — flatten against background.
            if img.mode == "RGBA":
                background = PIL.Image.new("RGB", img.size, (26, 26, 46))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            if img.width > gif_max_width:
                ratio = gif_max_width / img.width
                new_size = (gif_max_width, int(img.height * ratio))
                img = img.resize(new_size, PIL.Image.LANCZOS)
            frames.append(img)
        except Exception as exc:
            logger.warning(
                "Skipping screenshot %s for GIF: %s",
                step.screenshot_path,
                exc,
            )

    if not frames:
        raise ValueError(
            f"No valid screenshots found for session {detail.session_id}"
        )

    output_path = session_dir / f"export_{detail.session_id}.gif"

    # 1.5 seconds per frame, infinite loop.
    frames[0].save(
        str(output_path),
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=1500,
        loop=0,
        optimize=True,
    )

    logger.info(
        "Exported session %s as GIF: %s", detail.session_id, output_path,
    )
    return str(output_path)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def export_html(detail: "SessionDetail", session_dir: Path) -> str:
    """Export the session as a self-contained HTML file and return its path.

    Screenshots are embedded as base64 data URIs so the file is portable.
    """
    screenshots_b64 = _collect_screenshots_b64(detail, session_dir)
    steps_html = "\n".join(
        _render_step_card(step, screenshots_b64.get(step.step_num))
        for step in detail.steps_data
    )

    status_label = detail.status.upper()
    status_color = "#4ade80" if detail.status == "completed" else "#f87171"
    duration_str = f"{detail.duration:.1f}s"
    summary_text = _escape_html(detail.metadata.get("summary", ""))
    success_rate_meta = detail.metadata.get("success_rate", 0)
    avg_confidence_meta = detail.metadata.get("avg_confidence", 0)

    html = _HTML_SHELL.format(
        css=_CSS,
        js=_JS,
        title=_escape_html(detail.task),
        task=_escape_html(detail.task),
        session_id=detail.session_id,
        created_at=_escape_html(detail.created_at),
        model=_escape_html(detail.model),
        status_label=status_label,
        status_color=status_color,
        steps=detail.steps,
        duration_str=duration_str,
        avg_confidence_pct=round(avg_confidence_meta * 100),
        success_rate_pct=round(success_rate_meta * 100),
        summary_text=summary_text,
        steps_html=steps_html,
    )

    output_path = session_dir / f"export_{detail.session_id}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(
        "Exported session %s as HTML: %s", detail.session_id, output_path,
    )
    return str(output_path)


# ---------------------------------------------------------------------------
# HTML step-card rendering
# ---------------------------------------------------------------------------


def _collect_screenshots_b64(
    detail: "SessionDetail", session_dir: Path,
) -> dict[int, tuple[str, str]]:
    """Load each step's screenshot from disk as ``(base64, mime)``."""
    out: dict[int, tuple[str, str]] = {}
    for step in detail.steps_data:
        img_path = session_dir / step.screenshot_path
        if not img_path.exists():
            continue
        try:
            with open(img_path, "rb") as img_f:
                raw = img_f.read()
            mime = (
                "image/jpeg"
                if step.screenshot_path.lower().endswith((".jpg", ".jpeg"))
                else "image/png"
            )
            out[step.step_num] = (
                base64.b64encode(raw).decode("ascii"),
                mime,
            )
        except Exception as exc:
            logger.warning(
                "Could not embed screenshot %s: %s",
                step.screenshot_path,
                exc,
            )
    return out


def _render_step_card(step, b64_info: tuple[str, str] | None) -> str:
    """Return the HTML fragment for a single step card."""
    if b64_info is not None:
        b64, mime = b64_info
        img_tag = (
            f'<img src="data:{mime};base64,{b64}" '
            f'alt="Step {step.step_num}" />'
        )
    else:
        img_tag = '<div class="no-screenshot">No screenshot</div>'

    action_json = _escape_html(json.dumps(step.action, indent=2))
    badge_class = _action_badge_class(step.action_type)
    status_class = "success" if step.success else "failure"
    error_html = (
        f'<div class="error-msg">Error: {_escape_html(step.error)}</div>'
        if step.error
        else ""
    )

    confidence_pct = round(step.confidence * 100)
    if confidence_pct >= 80:
        confidence_class = "high"
    elif confidence_pct >= 50:
        confidence_class = "medium"
    else:
        confidence_class = "low"

    ts = datetime.fromtimestamp(step.timestamp, tz=timezone.utc).strftime(
        "%H:%M:%S"
    )
    ok_fail = "OK" if step.success else "FAIL"

    return (
        f'        <div class="step-card" data-step="{step.step_num}">\n'
        f'            <div class="step-header">\n'
        f'                <span class="step-number">Step {step.step_num}</span>\n'
        f'                <span class="badge {badge_class}">'
        f'{_escape_html(step.action_type)}</span>\n'
        f'                <span class="badge {status_class}">{ok_fail}</span>\n'
        f'                <span class="confidence {confidence_class}">'
        f'{confidence_pct}%</span>\n'
        f'                <span class="timestamp">{ts}</span>\n'
        f'            </div>\n'
        f'            <div class="step-body">\n'
        f'                <div class="screenshot-col">\n'
        f'                    {img_tag}\n'
        f'                </div>\n'
        f'                <div class="detail-col">\n'
        f'                    <div class="thought-bubble">\n'
        f'                        <div class="thought-label">Agent Thought</div>\n'
        f'                        <p>{_escape_html(step.thought)}</p>\n'
        f'                    </div>\n'
        f'                    <div class="action-block">\n'
        f'                        <div class="action-label">Action</div>\n'
        f'                        <pre><code>{action_json}</code></pre>\n'
        f'                    </div>\n'
        f'                    {error_html}\n'
        f'                </div>\n'
        f'            </div>\n'
        f'        </div>'
    )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """Escape characters that are special in HTML."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _action_badge_class(action_type: str) -> str:
    """Map an action type string to a CSS class for colour-coded badges."""
    known = {
        "tap", "swipe", "type", "scroll", "key", "wait",
        "done", "home", "back",
    }
    return action_type if action_type in known else "other"

