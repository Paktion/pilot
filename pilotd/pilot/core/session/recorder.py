"""
Live agent session recorder.

Records per-step screenshot + thought + action + success + confidence +
timing to ``$PILOT_HOME/sessions/<session_id>/``. Step metadata is
appended to a ``steps.jsonl`` file immediately after each
:meth:`SessionRecorder.record_step` call so that partial data survives a
crash. When :meth:`SessionRecorder.finish` is called, a consolidated
``steps.json`` and ``metadata.json`` are written.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import PIL.Image

from pilot.core import paths

logger = logging.getLogger("pilotd.session")


class SessionRecorder:
    """Records a live agent session to disk.

    Each session gets its own directory under ``$PILOT_HOME/sessions/``
    by default. Screenshots are saved as numbered JPEGs (quality 80).
    Step metadata is flushed to ``steps.jsonl`` after each step so data
    survives crashes; :meth:`finish` consolidates them into
    ``steps.json`` alongside ``metadata.json``.

    Config keys: ``session_recording`` (bool, default True),
    ``session_redact_screenshots`` (bool, default False),
    ``session_retention_days`` (int, default 30).
    """

    def __init__(
        self,
        task: str,
        session_dir: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        config: dict[str, Any] | None = None,
    ) -> None:
        self._session_id = uuid.uuid4().hex[:12]
        self._task = task
        self._model = model
        self._start_time = time.time()
        self._steps: list[dict[str, Any]] = []
        self._errors: list[dict[str, Any]] = []
        self._finished = False

        _config = config or {}

        # Privacy controls --------------------------------------------------
        # When session_recording is False, recording is completely disabled:
        # record_step() becomes a no-op and no files are written.
        self._recording_enabled: bool = _config.get("session_recording", True)

        # When True, screenshots are replaced with a metadata-only placeholder
        # (a small gray image with "REDACTED" text) before saving.
        self._redact_screenshots: bool = _config.get(
            "session_redact_screenshots", False,
        )

        # Retention period in days — used by cleanup() at session start.
        self._retention_days: int = _config.get("session_retention_days", 30)

        if not self._recording_enabled:
            logger.info(
                "SessionRecorder created with recording disabled "
                "(session_recording=False)"
            )
            # Set a minimal session dir so the object is still valid, but
            # nothing will be written to it.
            self._session_dir = paths.sessions_dir() / self._session_id
            self._steps_log_path = self._session_dir / "steps.jsonl"
            return

        if session_dir is not None:
            self._session_dir = Path(session_dir)
        else:
            self._session_dir = paths.sessions_dir() / self._session_id

        self._session_dir.mkdir(parents=True, exist_ok=True)

        # Incremental step log — append-mode so data survives crashes.
        self._steps_log_path = self._session_dir / "steps.jsonl"

        # Run disk-space cleanup before starting a new session.
        try:
            # Imported locally to avoid a circular import between
            # recorder and manager at module load time.
            from pilot.core.session.manager import SessionManager

            mgr = SessionManager(base_dir=str(self._session_dir.parent))
            mgr.cleanup(max_age_days=self._retention_days)
        except Exception as exc:
            logger.debug("Cleanup at session start skipped: %s", exc)

        logger.info(
            "SessionRecorder initialised: id=%s  dir=%s",
            self._session_id,
            self._session_dir,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """Unique identifier for this session."""
        return self._session_id

    @property
    def session_path(self) -> str:
        """Absolute path to the session directory."""
        return str(self._session_dir)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_step(
        self,
        step_num: int,
        screenshot: PIL.Image.Image,
        thought: str,
        action: dict,
        action_type: str,
        success: bool,
        confidence: float,
    ) -> None:
        """Record a single agent step.

        No-op when recording is disabled. When
        ``session_redact_screenshots`` is True, the screenshot is
        replaced with a metadata-only placeholder before saving. The
        screenshot is saved as ``step_NNNN.jpg`` (quality 80) and step
        metadata is appended to ``steps.jsonl`` immediately.

        Parameters
        ----------
        step_num : int
            Sequential step number (1-based).
        screenshot : PIL.Image.Image
            The screenshot captured at this step.
        thought : str
            The agent's chain-of-thought reasoning.
        action : dict
            The action dict returned by the LLM.
        action_type : str
            Short label for the action type (``"tap"``, ``"swipe"``, ...).
        success : bool
            Whether the action executed successfully.
        confidence : float
            The agent's self-reported confidence (0.0 — 1.0).
        """
        if not self._recording_enabled:
            return

        filename = f"step_{step_num:04d}.jpg"
        filepath = self._session_dir / filename

        try:
            img = screenshot

            # Redact screenshot: replace with a metadata-only placeholder.
            if self._redact_screenshots:
                img = _make_redacted_placeholder(img.size)
            else:
                # Convert RGBA to RGB first since JPEG does not support alpha.
                if img.mode == "RGBA":
                    bg = PIL.Image.new("RGB", img.size, (26, 26, 46))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")

            img.save(str(filepath), "JPEG", quality=80)
        except Exception as exc:
            logger.warning(
                "Failed to save screenshot for step %d: %s", step_num, exc,
            )

        step_data: dict[str, Any] = {
            "step_num": step_num,
            "timestamp": time.time(),
            "screenshot_path": filename,
            "thought": thought,
            "action": action,
            "action_type": action_type,
            "success": success,
            "confidence": confidence,
            "error": None,
        }
        self._steps.append(step_data)

        # Incremental flush — append this step to the JSONL log so data
        # is not lost if the process crashes before finish().
        try:
            with open(self._steps_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(step_data, default=str) + "\n")
        except OSError as exc:
            logger.warning(
                "Failed to flush step %d to disk: %s", step_num, exc,
            )

        logger.debug(
            "Recorded step %d: action=%s  success=%s  confidence=%.2f",
            step_num,
            action_type,
            success,
            confidence,
        )

    def record_error(self, step_num: int, error: str) -> None:
        """Record an error that occurred during a step.

        No-op when recording is disabled. If an existing step entry for
        *step_num* exists, the error is attached to it; otherwise a
        standalone error entry is created.
        """
        if not self._recording_enabled:
            return

        error_entry = {
            "step_num": step_num,
            "timestamp": time.time(),
            "error": error,
        }
        self._errors.append(error_entry)

        # Attach to the matching step if it exists.
        for step in self._steps:
            if step["step_num"] == step_num:
                step["error"] = error
                break

        logger.warning("Recorded error at step %d: %s", step_num, error)

    def finish(self, success: bool, summary: str) -> None:
        """Finalise the session and write metadata + steps to disk.

        No-op when recording is disabled.
        """
        if not self._recording_enabled:
            return

        if self._finished:
            logger.warning(
                "finish() called on already-finished session %s",
                self._session_id,
            )
            return

        end_time = time.time()
        duration = end_time - self._start_time

        status = "completed" if success else "failed"

        metadata: dict[str, Any] = {
            "session_id": self._session_id,
            "task": self._task,
            "model": self._model,
            "status": status,
            "success": success,
            "summary": summary,
            "steps_count": len(self._steps),
            "errors_count": len(self._errors),
            "duration": round(duration, 2),
            "created_at": datetime.fromtimestamp(
                self._start_time, tz=timezone.utc,
            ).isoformat(),
            "finished_at": datetime.fromtimestamp(
                end_time, tz=timezone.utc,
            ).isoformat(),
            "avg_confidence": self._calc_avg_confidence(),
            "success_rate": self._calc_success_rate(),
        }

        metadata_path = self._session_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)

        steps_path = self._session_dir / "steps.json"
        with open(steps_path, "w", encoding="utf-8") as f:
            json.dump(self._steps, f, indent=2, default=str)

        self._finished = True

        logger.info(
            "Session %s finished: status=%s  steps=%d  duration=%.1fs",
            self._session_id,
            status,
            len(self._steps),
            duration,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calc_avg_confidence(self) -> float:
        """Return average confidence across all recorded steps."""
        if not self._steps:
            return 0.0
        total = sum(s.get("confidence", 0.0) for s in self._steps)
        return round(total / len(self._steps), 3)

    def _calc_success_rate(self) -> float:
        """Return fraction of steps that succeeded."""
        if not self._steps:
            return 0.0
        ok = sum(1 for s in self._steps if s.get("success"))
        return round(ok / len(self._steps), 3)


# ---------------------------------------------------------------------------
# Screenshot redaction helper
# ---------------------------------------------------------------------------


def _make_redacted_placeholder(size: tuple[int, int]) -> PIL.Image.Image:
    """Return a solid-gray placeholder image with "REDACTED" text.

    The placeholder preserves the original dimensions but replaces all
    visual content so no sensitive information leaks.
    """
    img = PIL.Image.new("RGB", size, color=(80, 80, 80))
    try:
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        text = "REDACTED"
        bbox = draw.textbbox((0, 0), text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (size[0] - tw) // 2
        y = (size[1] - th) // 2
        draw.text((x, y), text, fill=(255, 255, 255))
    except Exception:
        # If drawing fails, just return the solid gray image.
        pass
    return img
