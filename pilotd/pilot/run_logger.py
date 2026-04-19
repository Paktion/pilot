"""
Per-run disk logger for the goal-directed agent.

For every workflow run, writes:

    $PILOT_HOME/sessions/<run_id>/
        meta.json           — run summary (workflow, started_at, ended_at, status)
        events.jsonl        — one JSON line per emitted event (image_b64 stripped)
        step-000.jpg        — screenshot at goal_thinking step 0
        step-001.jpg        — ...
        summary.txt         — human-readable action trace

This is the canonical debug artifact when a run silently fails. The Swift
app doesn't see disk artifacts, but developers can open the folder and
replay the exact sequence of (screen, thought, action) the agent saw.

The logger wraps an existing ``emit`` callable so the engine + goal agent
keep streaming to the UI as before.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pilot.core import paths

log = logging.getLogger("pilotd.run_logger")


class RunLogger:
    """Wraps an emit callable with per-run disk persistence."""

    def __init__(
        self,
        *,
        run_id: str,
        workflow: str,
        downstream_emit: Callable[[dict[str, Any]], None],
    ) -> None:
        self._run_id = run_id
        self._workflow = workflow
        self._downstream = downstream_emit
        self._dir = paths.sessions_dir() / run_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._dir / "events.jsonl"
        self._summary_path = self._dir / "summary.txt"
        self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._step_counter = 0
        self._lock = threading.Lock()
        self._write_meta(status="running")
        self._summary_lines: list[str] = [
            f"# Run {run_id}  workflow={workflow}",
            f"# started: {self._started_at}",
            "",
        ]

    @property
    def directory(self) -> Path:
        return self._dir

    def emit(self, event: dict[str, Any]) -> None:
        """Persist the event + forward to the downstream UI stream."""
        with self._lock:
            persisted = self._persist(event)
        # Forward downstream regardless of persistence success.
        try:
            self._downstream(event)
        except Exception:
            log.exception("downstream emit failed")
        if event.get("event") in ("done", "error", "failed", "aborted"):
            self._finalize(event)

    def _persist(self, event: dict[str, Any]) -> dict[str, Any]:
        try:
            # Screenshots: decode b64 to disk, strip the huge field from the
            # JSONL so the file stays readable.
            persisted = dict(event)
            img_b64 = persisted.pop("image_b64", None)
            if img_b64:
                idx = self._step_counter
                self._step_counter += 1
                jpg_path = self._dir / f"step-{idx:03d}.jpg"
                try:
                    jpg_path.write_bytes(base64.b64decode(img_b64))
                    persisted["image_path"] = jpg_path.name
                except Exception as exc:
                    log.warning("run_logger: screenshot decode failed: %s", exc)

            with self._events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(persisted, default=str) + "\n")

            self._append_summary(persisted)
            return persisted
        except Exception as exc:
            log.warning("run_logger: persist failed: %s", exc)
            return event

    def _append_summary(self, event: dict[str, Any]) -> None:
        ev = event.get("event", "?")
        if ev == "goal_thinking":
            line = (
                f"  [{event.get('step','?'):>2}] think "
                f"{event.get('action','?'):<15} "
                f"conf={event.get('confidence',0):.2f}  "
                f"{(event.get('thought','') or '')[:120]}"
            )
        elif ev == "goal_action":
            line = (
                f"  [{event.get('step','?'):>2}] act   "
                f"{event.get('kind','?'):<15} "
                f"{(event.get('detail','') or '')[:120]}"
            )
        elif ev == "goal_stuck":
            line = f"  [{event.get('step','?'):>2}] STUCK -> recovery={event.get('recovery','?')}"
        elif ev == "goal_observed":
            line = (
                f"  [{event.get('step','?'):>2}] OBSERVED "
                f"summary={(event.get('summary','') or '')[:120]}"
            )
        elif ev == "goal_start":
            line = f"--- goal_start: {(event.get('goal','') or '')[:200]}"
        elif ev == "goal_exhausted":
            line = f"--- goal_exhausted (budget={event.get('budget','?')})"
        elif ev == "screenshot":
            line = (
                f"  screenshot -> {event.get('image_path','?')} "
                f"kind={event.get('meta',{}).get('kind','?')}"
            )
        elif ev == "step":
            line = f"==  step {event.get('step','?'):>2}  {event.get('kind','?')}"
        elif ev in ("done", "failed", "aborted", "error"):
            line = (
                f"*** {ev.upper()} status={event.get('status','?')}  "
                f"{(event.get('summary', event.get('error','')) or '')[:200]}"
            )
        elif ev == "replan_start":
            line = f"  replan_start step={event.get('step','?')} error={event.get('error','')[:80]}"
        elif ev == "replan_accepted":
            line = f"  replan_accepted new_steps={event.get('new_steps')}"
        elif ev == "extract_ask":
            line = (
                f"  extract_ask var={event.get('variable')} "
                f"q={(event.get('question','') or '')[:120]}"
            )
        elif ev == "extract_answer":
            line = (
                f"  extract_answer var={event.get('variable')} "
                f"val={event.get('value')!r} conf={event.get('confidence')}"
            )
        else:
            line = f"  [{ev}] {json.dumps(event, default=str)[:180]}"
        self._summary_lines.append(line)

    def _write_meta(self, *, status: str, summary: str = "") -> None:
        meta = {
            "run_id": self._run_id,
            "workflow": self._workflow,
            "started_at": self._started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
                         if status != "running" else None,
            "status": status,
            "summary": summary,
            "screenshot_count": self._step_counter,
        }
        try:
            (self._dir / "meta.json").write_text(
                json.dumps(meta, indent=2, default=str) + "\n"
            )
        except Exception:
            log.exception("run_logger: meta write failed")

    def _finalize(self, terminal_event: dict[str, Any]) -> None:
        status = terminal_event.get("status") or terminal_event.get("event", "ended")
        summary = terminal_event.get("summary") or terminal_event.get("error", "")
        self._write_meta(status=status, summary=summary)
        try:
            self._summary_lines.append("")
            self._summary_lines.append(
                f"# ended {datetime.now(timezone.utc).isoformat(timespec='seconds')}  "
                f"status={status}  summary={summary[:200]}"
            )
            self._summary_path.write_text("\n".join(self._summary_lines) + "\n")
        except Exception:
            log.exception("run_logger: summary write failed")


__all__ = ["RunLogger"]
