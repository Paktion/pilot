"""
Compiled-skill snapshots.

After N consecutive successful runs of a workflow (default 3), freeze the
tap coordinates + OCR anchor texts observed in the most recent run to a
sibling ``<slug>.compiled.json``. Scheduled runs prefer the compiled path;
fall back to full vision if any anchor text is missing at the expected
region.

Format (version 2):
    {
      "version": 2,
      "source": {"sha256": "...", "compiledAt": "..."},
      "device":  {"windowWidth": ..., "windowHeight": ..., "orientation": "portrait"},
      "steps":   [{"index": 0, "type": "tap", "label": "Reorder", "hints": {...}}, ...]
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pilot.core import paths

log = logging.getLogger("pilotd.compiler")

MIN_CONSECUTIVE_SUCCESSES = 3


@dataclass
class StepRecord:
    """Single step observation captured during a live run."""

    index: int
    type: str
    label: str
    compiled_action: str  # 'tap' | 'sleep' | 'scroll_sequence' | 'passthrough'
    tap_x: float | None = None
    tap_y: float | None = None
    observed_delay_ms: int | None = None
    scroll_count: int | None = None
    scroll_direction: str | None = None
    confidence: float = 1.0
    match_strategy: str = "exact"

    def to_dict(self) -> dict[str, Any]:
        hints: dict[str, Any] = {
            "compiledAction": self.compiled_action,
            "confidence": self.confidence,
            "matchStrategy": self.match_strategy,
        }
        if self.tap_x is not None:
            hints["tapX"] = self.tap_x
        if self.tap_y is not None:
            hints["tapY"] = self.tap_y
        if self.observed_delay_ms is not None:
            hints["observedDelayMs"] = self.observed_delay_ms
        if self.scroll_count is not None:
            hints["scrollCount"] = self.scroll_count
            hints["scrollDirection"] = self.scroll_direction
        return {
            "index": self.index,
            "type": self.type,
            "label": self.label,
            "hints": hints,
        }


@dataclass
class RecordingBuffer:
    """In-memory buffer for step observations during a run."""

    steps: list[StepRecord] = field(default_factory=list)
    device_width: int = 0
    device_height: int = 0
    orientation: str = "portrait"
    last_step_start: float = field(default_factory=time.monotonic)

    def record_tap(self, *, index: int, label: str, x: float, y: float) -> None:
        delay_ms = int((time.monotonic() - self.last_step_start) * 1000)
        self.steps.append(
            StepRecord(
                index=index, type="tap", label=label,
                compiled_action="tap", tap_x=x, tap_y=y,
                observed_delay_ms=delay_ms,
            )
        )
        self.last_step_start = time.monotonic()

    def record_wait(self, *, index: int, label: str) -> None:
        delay_ms = int((time.monotonic() - self.last_step_start) * 1000)
        self.steps.append(
            StepRecord(
                index=index, type="wait_for", label=label,
                compiled_action="sleep", observed_delay_ms=delay_ms,
            )
        )
        self.last_step_start = time.monotonic()

    def record_passthrough(self, *, index: int, step_type: str, label: str) -> None:
        self.steps.append(
            StepRecord(
                index=index, type=step_type, label=label,
                compiled_action="passthrough",
            )
        )
        self.last_step_start = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        return {
            "device": {
                "windowWidth": self.device_width,
                "windowHeight": self.device_height,
                "orientation": self.orientation,
            },
            "steps": [s.to_dict() for s in self.steps],
        }


def compile_snapshot(
    *,
    source_yaml_path: Path,
    source_yaml_text: str,
    recording: RecordingBuffer,
) -> Path:
    """Write a compiled snapshot next to the source YAML. Returns its path."""
    out_path = paths.compiled_skill_path(source_yaml_path)
    payload = {
        "version": 2,
        "source": {
            "sha256": hashlib.sha256(source_yaml_text.encode()).hexdigest(),
            "compiledAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        **recording.snapshot(),
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("compiled snapshot written to %s (steps=%d)", out_path, len(recording.steps))
    return out_path


def load_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("compiled snapshot %s unreadable: %s", path, exc)
        return None


def is_snapshot_fresh(
    snapshot: dict[str, Any],
    *,
    current_source: str,
    current_width: int,
    current_height: int,
    max_width_drift: int = 10,
    max_height_drift: int = 10,
) -> bool:
    """Detect whether a compiled snapshot is stale vs. live conditions."""
    if snapshot.get("version") != 2:
        return False
    expected_hash = snapshot.get("source", {}).get("sha256")
    if expected_hash != hashlib.sha256(current_source.encode()).hexdigest():
        return False
    device = snapshot.get("device") or {}
    if abs(device.get("windowWidth", 0) - current_width) > max_width_drift:
        return False
    if abs(device.get("windowHeight", 0) - current_height) > max_height_drift:
        return False
    return True


def should_compile(consecutive_successes: int) -> bool:
    return consecutive_successes >= MIN_CONSECUTIVE_SUCCESSES
