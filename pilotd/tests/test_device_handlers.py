"""Device RPC handlers — verify dispatch with a stubbed controller."""

from __future__ import annotations

import asyncio

import pytest

from pilot import service
from pilot.handlers import device_handlers


class _FakeInputs:
    def __init__(self):
        self.calls: list[tuple] = []

    def home(self):
        self.calls.append(("home",))

    def long_press(self, x, y, duration=1.0):
        self.calls.append(("long_press", x, y, duration))


class _FakeController:
    """Mimics AgentController's surface — tracks which method was invoked."""

    def __init__(self):
        self._inputs = _FakeInputs()
        self.calls: list[tuple] = []

    def tap_xy(self, x, y):
        self.calls.append(("tap_xy", x, y))

    def tap_text(self, text, prefer=None, max_scrolls=2):
        self.calls.append(("tap_text", text, prefer))

    def swipe(self, direction, distance=None):
        self.calls.append(("swipe", direction, distance))

    def long_press(self, x, y, duration=1.0):
        self.calls.append(("long_press", x, y, duration))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def press_key(self, key, modifiers=None):
        self.calls.append(("press_key", key, modifiers))

    def press_home(self):
        self.calls.append(("press_home",))

    def launch(self, app):
        self.calls.append(("launch", app))


@pytest.fixture
def fake_ctrl(monkeypatch):
    ctrl = _FakeController()
    # Patch the container's device_controller getter so the handler sees our stub.
    monkeypatch.setattr(service.container(), "device_controller", lambda: ctrl)
    yield ctrl
    service.reset_container_for_tests()


async def _emit_collect():
    frames: list[dict] = []

    async def emit(frame):
        frames.append(frame)

    return frames, emit


@pytest.mark.asyncio
async def test_device_tap(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.tap({"x": 100, "y": 200}, emit)
    assert fake_ctrl.calls == [("tap_xy", 100, 200)]
    assert frames[-1] == {"event": "done", "status": "ok", "x": 100, "y": 200}


@pytest.mark.asyncio
async def test_device_tap_text(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.tap_text({"text": "Checkout", "prefer": "last"}, emit)
    assert fake_ctrl.calls == [("tap_text", "Checkout", "last")]
    assert frames[-1]["status"] == "ok"


@pytest.mark.asyncio
async def test_device_swipe(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.swipe({"direction": "up", "distance": 150}, emit)
    assert fake_ctrl.calls == [("swipe", "up", 150)]


@pytest.mark.asyncio
async def test_device_swipe_rejects_bad_direction(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.swipe({"direction": "diagonal"}, emit)
    assert fake_ctrl.calls == []
    assert frames[-1]["event"] == "error"


@pytest.mark.asyncio
async def test_device_long_press(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.long_press({"x": 10, "y": 20, "duration": 2.5}, emit)
    assert fake_ctrl.calls == [("long_press", 10, 20, 2.5)]


@pytest.mark.asyncio
async def test_device_press_home(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.press_home({}, emit)
    assert fake_ctrl.calls == [("press_home",)]


@pytest.mark.asyncio
async def test_device_launch_app(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.launch_app({"app_name": "Weather"}, emit)
    assert fake_ctrl.calls == [("launch", "Weather")]


@pytest.mark.asyncio
async def test_device_type_and_key(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.type_text({"text": "hello"}, emit)
    await device_handlers.press_key({"key": "enter", "modifiers": ["command"]}, emit)
    assert fake_ctrl.calls == [
        ("type_text", "hello"),
        ("press_key", "enter", ["command"]),
    ]


@pytest.mark.asyncio
async def test_device_tap_missing_params(fake_ctrl):
    frames, emit = await _emit_collect()
    await device_handlers.tap({}, emit)
    assert fake_ctrl.calls == []
    assert frames[-1]["event"] == "error"
