"""
Daemon-level service container.

Wires together the singleton instances the RPC handlers depend on. Accessing
the container triggers lazy construction of each component (memory store,
workflow loader, scheduler, planner, etc.) so ``health.check`` and other
cheap RPCs don't pay for the full stack.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable

from pilot.core import paths
from pilot.core.config import Config
from pilot.core.planner import Planner
from pilot.core.usage import UsageTracker
from pilot.memory_vec import MemoryStore
from pilot.workflow import WorkflowDef, parse_workflow_yaml

log = logging.getLogger("pilotd.service")

# The demo templates bundled with the Swift app are copied into
# `$PILOT_HOME/workflows/` on first daemon start so users have something to
# execute immediately.
_DEMO_TEMPLATES: tuple[tuple[str, str], ...] = (
    (
        "check_weather.skill.yaml",
        """version: 1
name: Check Today's Weather
app: Weather
tags: [demo, safe]
description: Opens Weather, reads today's high temp. Single-screen, deterministic.

steps:
  - launch: Weather
  - wait_for: ["Today", "H:", "L:", "°"]
    max_scrolls: 1
    timeout_s: 15
  - extract: today_high
    question: "What is today's high temperature as a number? Extract the numeric value only."
    type: int
    hint: "Usually shown as 'H: NN°' near the top card."
  - remember:
      key: last_weather_high
      value: "{{ today_high }}"
  - done: "High: {{ today_high }}°"
""",
    ),
    (
        "reorder_grubhub.skill.yaml",
        """version: 1
name: Reorder Chipotle Bowl
app: Grubhub
tags: [food, weekly]
description: Reorders my usual Chipotle bowl.

params:
  tip_percent:
    type: int
    default: 20

steps:
  - launch: Grubhub
  - wait_for: "Reorder"
  - tap: "Reorder"
  - wait_for: "Chipotle"
  - tap_near: "Chipotle"
    prefer: first
  - read_as: last_total
    pattern: "Total \\\\$([0-9.]+)"
  - tap: "Checkout"
  - tap: "Place order"
  - screenshot: order_confirmation
""",
    ),
    (
        "check_osu_swipes.skill.yaml",
        """version: 1
name: Check OSU Dining Swipes
app: Ohio State
tags: [campus, weekly]
description: Goal-directed — navigates the OSU app to read any dining balance on screen.

steps:
  - launch: Ohio State
  - goal: |
      Find and report a dining-related number visible on screen —
      remaining meal swipes OR Dining Dollars balance OR BuckID Cash.
      Navigate by tapping tabs/buttons as needed. Scroll if content
      extends below the fold. When a dining number is clearly visible,
      call Done with a summary like 'Dining Dollars: $12.34' or
      'Swipes remaining: 7'. Do NOT tap payment confirmations.
    budget: 12
    capture_as: dining_balance
  - remember:
      key: last_dining_balance
      value: "{{ dining_balance }}"
  - done: "Recorded dining balance: {{ dining_balance }}"
""",
    ),
    (
        "pay_spectrum_bill.skill.yaml",
        """version: 1
name: Pay Spectrum Bill
app: Spectrum
tags: [bills, monthly]
description: Reads current bill. Aborts if above median of recent runs.

steps:
  - launch: Spectrum
  - wait_for: "Pay"
  - read_as: bill_amount
    pattern: "\\\\$([0-9]+\\\\.[0-9]{2})"
  - abort_if: "{{ bill_amount | float > (memory.median_spectrum_last6 | default(0) | float * 1.5) }}"
  - tap: "Pay"
  - tap: "Confirm"
  - screenshot: payment_confirmation
  - remember:
      key: last_spectrum_bill
      value: "{{ bill_amount }}"
""",
    ),
)


class _Container:
    """Lazy singleton container. Access as ``pilot.service.container()``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config: Config | None = None
        self._memory: MemoryStore | None = None
        self._usage: UsageTracker | None = None
        self._planner: Planner | None = None
        self._workflow_cache: dict[str, WorkflowDef] = {}
        self._workflow_runs: dict[str, threading.Thread] = {}
        self._templates_seeded = False

    def config(self) -> Config:
        with self._lock:
            if self._config is None:
                self._config = Config()
            return self._config

    def memory(self) -> MemoryStore:
        with self._lock:
            if self._memory is None:
                self._memory = MemoryStore()
                self._seed_templates_if_needed()
            return self._memory

    def usage(self) -> UsageTracker:
        with self._lock:
            if self._usage is None:
                cfg = self.config()
                self._usage = UsageTracker(
                    daily_budget=float(cfg.get("max_daily_budget", 5.0)),
                    per_task_budget=float(cfg.get("per_task_budget", 1.0)),
                )
            return self._usage

    def planner(self) -> Planner:
        with self._lock:
            if self._planner is None:
                cfg = self.config()
                self._planner = Planner(
                    sonnet_model=cfg.get("model", "claude-sonnet-4-20250514"),
                    haiku_model=cfg.get("model_light", "claude-haiku-4-5-20251001"),
                    usage=self.usage(),
                )
            return self._planner

    def extractor(self):
        """Vision-based extractor for the EXTRACT workflow step."""
        with self._lock:
            from pilot.workflow.extractor import VisionExtractor
            existing = getattr(self, "_extractor", None)
            if existing is None:
                cfg = self.config()
                self._extractor = VisionExtractor(
                    client=self.planner()._client,
                    fast_model=cfg.get("model_light", "claude-haiku-4-5-20251001"),
                    strong_model=cfg.get("model", "claude-sonnet-4-20250514"),
                    usage=self.usage(),
                )
                existing = self._extractor
            return existing

    def device_controller(self):
        """Singleton AgentController for direct device RPCs (device.* / MCP).

        Unlike the one built per-run in workflow_handlers, this controller has
        no event emitter, no screenshot streamer, and no hint lookup — it's a
        thin shim for testing individual gestures.
        """
        with self._lock:
            existing = getattr(self, "_device_controller", None)
            if existing is not None:
                return existing
            from pilot.core.controller import AgentController
            from pilot.core.input_simulator import CGEventInputSimulator, InputSimulator
            from pilot.core.vision import VisionAgent
            from pilot.core.window_capture import MirroringWindowManager

            window = MirroringWindowManager()
            # Locate the Mirroring window now so the first RPC doesn't hit
            # the lazy-init error path. The workflow path sidesteps this
            # because its first input call runs refresh_bounds(); direct
            # device.screenshot() has no such side effect.
            from pilot.core.window_capture import MirroringWindowError
            try:
                window.find_window()
            except MirroringWindowError as exc:
                log.warning("device controller: %s", exc)
            cfg = self.config()
            use_cgevent = bool(cfg.get("use_cgevent", True))
            if use_cgevent:
                try:
                    inputs = CGEventInputSimulator(window_manager=window)
                except Exception as exc:
                    log.warning(
                        "device controller: CGEvent unavailable (%s) — using pyautogui",
                        exc,
                    )
                    inputs = InputSimulator(window_manager=window)
            else:
                inputs = InputSimulator(window_manager=window)
            vision = VisionAgent(model=cfg.get("model"))
            self._device_controller = AgentController(
                vision=vision, inputs=inputs, window=window,
            )
            return self._device_controller

    def reset_device_controller(self) -> None:
        """Drop the cached device controller (e.g. after Mirroring reconnect)."""
        with self._lock:
            self._device_controller = None

    def replanner(self):
        """Claude-backed replanner for ``on_failure: replan`` step modifier."""
        with self._lock:
            from pilot.workflow.replanner import Replanner
            existing = getattr(self, "_replanner", None)
            if existing is None:
                cfg = self.config()
                self._replanner = Replanner(
                    client=self.planner()._client,
                    model=cfg.get("model", "claude-sonnet-4-20250514"),
                    usage=self.usage(),
                )
                existing = self._replanner
            return existing

    # ---- workflow loader ---------------------------------------------------

    def load_workflow(self, name: str) -> WorkflowDef | None:
        mem = self.memory()
        row = mem.get_workflow_by_name(name) or mem.get_workflow(name)
        if row is None:
            return None
        cached = self._workflow_cache.get(row["id"])
        if cached and cached.name == row["name"]:
            return cached
        defn = parse_workflow_yaml(row["yaml"])
        self._workflow_cache[row["id"]] = defn
        return defn

    def save_workflow(
        self, *, name: str, app: str | None, yaml_text: str, id: str | None = None
    ) -> str:
        parse_workflow_yaml(yaml_text)  # validate first
        wf_id = self.memory().upsert_workflow(
            id=id, name=name, app=app, yaml_text=yaml_text
        )
        self._workflow_cache.pop(wf_id, None)
        return wf_id

    def delete_workflow(self, workflow_id: str) -> None:
        self.memory().delete_workflow(workflow_id)
        self._workflow_cache.pop(workflow_id, None)

    def track_run_thread(self, run_id: str, thread: threading.Thread) -> None:
        self._workflow_runs[run_id] = thread

    def release_run_thread(self, run_id: str) -> None:
        self._workflow_runs.pop(run_id, None)

    # ---- template seeding --------------------------------------------------

    def _seed_templates_if_needed(self) -> None:
        if self._templates_seeded:
            return
        self._templates_seeded = True
        mem = self._memory
        if mem is None:
            return
        existing = {w["name"] for w in mem.list_workflows()}
        out_dir = paths.workflows_dir()
        for filename, content in _DEMO_TEMPLATES:
            yaml_path = out_dir / filename
            if not yaml_path.exists():
                yaml_path.write_text(content)
            try:
                defn = parse_workflow_yaml(content)
            except Exception as exc:
                log.warning("skipping broken template %s: %s", filename, exc)
                continue
            if defn.name in existing:
                continue
            mem.upsert_workflow(name=defn.name, app=defn.app, yaml_text=content)
            log.info("seeded workflow template: %s", defn.name)


_CONTAINER: _Container | None = None


def container() -> _Container:
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = _Container()
    return _CONTAINER


def reset_container_for_tests() -> None:
    """Clear the singleton. Test-only hook."""
    global _CONTAINER
    _CONTAINER = None
