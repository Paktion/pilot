"""
Direct device RPCs — one primitive per method.

Exposed mainly for MCP clients that want to test each gesture individually
while iterating on prompts or workflow authoring. The workflow engine does
NOT route through here; it owns its own per-run controller.

Every handler runs the (blocking) controller call on a worker thread so the
asyncio event loop stays responsive.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any, Awaitable, Callable

from pilot import service

log = logging.getLogger("pilotd.device")

Emit = Callable[[dict[str, Any]], Awaitable[None]]


def _ctrl():
    return service.container().device_controller()


async def _run_in_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def _require(params: dict[str, Any], keys: tuple[str, ...], emit: Emit) -> bool:
    missing = [k for k in keys if params.get(k) in (None, "")]
    if missing:
        await emit({"event": "error", "error": f"missing params: {missing}"})
        return False
    return True


async def tap(params: dict[str, Any], emit: Emit) -> None:
    if not await _require(params, ("x", "y"), emit):
        return
    x = int(params["x"])
    y = int(params["y"])
    await _run_in_thread(_ctrl().tap_xy, x, y)
    await emit({"event": "done", "status": "ok", "x": x, "y": y})


async def tap_text(params: dict[str, Any], emit: Emit) -> None:
    text = params.get("text")
    if not text:
        await emit({"event": "error", "error": "missing 'text'"})
        return
    prefer = params.get("prefer")
    try:
        await _run_in_thread(_ctrl().tap_text, text, prefer)
    except Exception as exc:
        await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    await emit({"event": "done", "status": "ok", "text": text})


async def swipe(params: dict[str, Any], emit: Emit) -> None:
    direction = params.get("direction")
    if direction not in ("up", "down", "left", "right"):
        await emit({"event": "error", "error": "direction must be up/down/left/right"})
        return
    distance = params.get("distance")
    if distance is not None:
        distance = int(distance)
    await _run_in_thread(_ctrl().swipe, direction, distance)
    await emit({"event": "done", "status": "ok", "direction": direction})


async def long_press(params: dict[str, Any], emit: Emit) -> None:
    if not await _require(params, ("x", "y"), emit):
        return
    x = int(params["x"])
    y = int(params["y"])
    duration = float(params.get("duration", 1.0))
    await _run_in_thread(_ctrl().long_press, x, y, duration)
    await emit({"event": "done", "status": "ok", "x": x, "y": y, "duration": duration})


async def type_text(params: dict[str, Any], emit: Emit) -> None:
    text = params.get("text")
    if text is None:
        await emit({"event": "error", "error": "missing 'text'"})
        return
    await _run_in_thread(_ctrl().type_text, str(text))
    await emit({"event": "done", "status": "ok", "length": len(text)})


async def press_key(params: dict[str, Any], emit: Emit) -> None:
    key = params.get("key")
    if not key:
        await emit({"event": "error", "error": "missing 'key'"})
        return
    modifiers = params.get("modifiers") or None
    await _run_in_thread(_ctrl().press_key, key, modifiers)
    await emit({"event": "done", "status": "ok", "key": key, "modifiers": modifiers})


async def press_home(_params: dict[str, Any], emit: Emit) -> None:
    await _run_in_thread(_ctrl().press_home)
    await emit({"event": "done", "status": "ok"})


async def launch_app(params: dict[str, Any], emit: Emit) -> None:
    app = params.get("app_name") or params.get("app")
    if not app:
        await emit({"event": "error", "error": "missing 'app_name'"})
        return
    await _run_in_thread(_ctrl().launch, app)
    await emit({"event": "done", "status": "ok", "app": app})


async def screenshot(_params: dict[str, Any], emit: Emit) -> None:
    """Capture the current screen; return a base64 JPEG thumbnail."""
    img = await _run_in_thread(_ctrl().screenshot)
    thumb = img.copy()
    thumb.thumbnail((640, 1280))
    if thumb.mode in ("RGBA", "LA", "P"):
        thumb = thumb.convert("RGB")
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=75)
    await emit({
        "event": "done",
        "status": "ok",
        "image_b64": base64.standard_b64encode(buf.getvalue()).decode("ascii"),
        "width": thumb.width,
        "height": thumb.height,
    })


async def extract(params: dict[str, Any], emit: Emit) -> None:
    """Vision-QA against the current screen — standalone device-level query."""
    question = params.get("question")
    if not question:
        await emit({"event": "error", "error": "missing 'question'"})
        return
    expected_type = str(params.get("type") or params.get("expected_type") or "string")
    hint = params.get("hint")

    ctrl = _ctrl()
    extractor = service.container().extractor()
    img = await _run_in_thread(ctrl.screenshot)
    try:
        value, confidence = await _run_in_thread(
            extractor.extract,
            question=question,
            screenshot=img,
            expected_type=expected_type,
            hint=hint,
            task_id="device-extract",
        )
    except Exception as exc:
        await emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    await emit({
        "event": "done",
        "status": "ok",
        "answer": value,
        "confidence": round(confidence, 3),
    })


async def reset(_params: dict[str, Any], emit: Emit) -> None:
    """Drop the cached device controller — rebuilds on next call."""
    service.container().reset_device_controller()
    await emit({"event": "done", "status": "ok"})


METHODS = {
    "tap": tap,
    "tap_text": tap_text,
    "swipe": swipe,
    "long_press": long_press,
    "type_text": type_text,
    "press_key": press_key,
    "press_home": press_home,
    "launch_app": launch_app,
    "screenshot": screenshot,
    "extract": extract,
    "reset": reset,
}
