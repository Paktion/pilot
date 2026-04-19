"""
Session browser, retainer, and export dispatcher.

Lists recorded sessions, loads their full step history, deletes stale
sessions, and hands off to the export helpers in
:mod:`pilot.core.session.exporter` to build shareable artefacts.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pilot.core import paths

logger = logging.getLogger("pilotd.session")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionStep:
    """One step in a recorded session."""

    step_num: int
    timestamp: float
    screenshot_path: str  # relative to session dir
    thought: str
    action: dict
    action_type: str
    success: bool
    confidence: float
    error: str | None = None


@dataclass
class SessionSummary:
    """Lightweight summary of a recorded session (no step data)."""

    session_id: str
    task: str
    status: str  # "completed", "failed", "cancelled"
    steps: int
    duration: float
    created_at: str  # ISO 8601
    model: str


@dataclass
class SessionDetail(SessionSummary):
    """Full session data including every recorded step."""

    steps_data: list[SessionStep] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """Manages all recorded sessions stored on disk.

    Parameters
    ----------
    base_dir : str | None
        Root directory where session folders live. Defaults to
        ``$PILOT_HOME/sessions/`` (resolved via
        :func:`pilot.core.paths.sessions_dir`).
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else paths.sessions_dir()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Listing and retrieval
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[SessionSummary]:
        """Return all recorded sessions, newest first.

        Session directories without a ``metadata.json`` are silently skipped.
        """
        summaries: list[SessionSummary] = []

        for entry in self._base_dir.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                summaries.append(
                    SessionSummary(
                        session_id=meta.get("session_id", entry.name),
                        task=meta.get("task", ""),
                        status=meta.get("status", "unknown"),
                        steps=meta.get("steps_count", 0),
                        duration=meta.get("duration", 0.0),
                        created_at=meta.get("created_at", ""),
                        model=meta.get("model", ""),
                    )
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping session dir %s: %s", entry.name, exc)

        # Sort newest first by created_at (ISO strings sort lexicographically).
        summaries.sort(key=lambda s: s.created_at, reverse=True)
        return summaries

    def get_session(self, session_id: str) -> SessionDetail:
        """Load full session data including all steps.

        Raises ``FileNotFoundError`` if the session does not exist.
        """
        session_dir = self._base_dir / session_id
        meta_path = session_dir / "metadata.json"
        steps_path = session_dir / "steps.json"

        if not meta_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        steps_data: list[SessionStep] = []
        # Prefer steps.json (written by finish()); fall back to
        # steps.jsonl (incremental log) for sessions that crashed.
        steps_jsonl_path = session_dir / "steps.jsonl"
        raw_steps: list[dict] = []
        if steps_path.exists():
            with open(steps_path, "r", encoding="utf-8") as f:
                raw_steps = json.load(f)
        elif steps_jsonl_path.exists():
            with open(steps_jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            raw_steps.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        # Preserve the original step order via the per-step ``step_num``
        # field; the on-disk order already matches but an explicit sort
        # means a malformed JSONL log cannot skew replays.
        raw_steps.sort(key=lambda s: s.get("step_num", 0))

        for s in raw_steps:
            steps_data.append(
                SessionStep(
                    step_num=s.get("step_num", 0),
                    timestamp=s.get("timestamp", 0.0),
                    screenshot_path=s.get("screenshot_path", ""),
                    thought=s.get("thought", ""),
                    action=s.get("action", {}),
                    action_type=s.get("action_type", ""),
                    success=s.get("success", False),
                    confidence=s.get("confidence", 0.0),
                    error=s.get("error"),
                )
            )

        return SessionDetail(
            session_id=meta.get("session_id", session_id),
            task=meta.get("task", ""),
            status=meta.get("status", "unknown"),
            steps=meta.get("steps_count", 0),
            duration=meta.get("duration", 0.0),
            created_at=meta.get("created_at", ""),
            model=meta.get("model", ""),
            steps_data=steps_data,
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # Deletion and cleanup
    # ------------------------------------------------------------------

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its files. Returns True on success."""
        session_dir = self._base_dir / session_id
        if not session_dir.exists():
            return False

        try:
            shutil.rmtree(session_dir)
            logger.info("Deleted session: %s", session_id)
            return True
        except OSError as exc:
            logger.error("Failed to delete session %s: %s", session_id, exc)
            return False

    def cleanup(
        self,
        max_age_days: int = 30,
        max_total_bytes: int = 1_073_741_824,
    ) -> int:
        """Delete sessions older than *max_age_days*, then trim the
        oldest until total disk usage is under *max_total_bytes*.

        Returns the number of sessions deleted.
        """
        cutoff = time.time() - (max_age_days * 86400)
        deleted = 0

        # ---- Phase 1: age-based cleanup ----
        for entry in list(self._base_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                created_str = meta.get("created_at", "")
                if not created_str:
                    continue
                created_dt = datetime.fromisoformat(created_str)
                created_ts = created_dt.timestamp()
                if created_ts < cutoff:
                    shutil.rmtree(entry)
                    deleted += 1
                    logger.info("Cleaned up old session: %s", entry.name)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logger.warning("Skipping cleanup for %s: %s", entry.name, exc)

        # ---- Phase 2: size-based cleanup ----
        # Build a list of (created_timestamp, dir_path, size_bytes) for
        # surviving sessions and delete oldest-first until within budget.
        session_info: list[tuple[float, Path, int]] = []
        for entry in list(self._base_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                created_str = meta.get("created_at", "")
                created_ts = (
                    datetime.fromisoformat(created_str).timestamp()
                    if created_str
                    else 0.0
                )
            except (json.JSONDecodeError, OSError, ValueError):
                created_ts = 0.0

            dir_size = sum(
                fp.stat().st_size for fp in entry.rglob("*") if fp.is_file()
            )
            session_info.append((created_ts, entry, dir_size))

        total_size = sum(s for _, _, s in session_info)
        if total_size > max_total_bytes:
            # Sort oldest first so we delete the oldest sessions first.
            session_info.sort(key=lambda t: t[0])
            for _created_ts, entry, dir_size in session_info:
                if total_size <= max_total_bytes:
                    break
                try:
                    shutil.rmtree(entry)
                    total_size -= dir_size
                    deleted += 1
                    logger.info(
                        "Cleaned up session for space: %s (freed %d bytes)",
                        entry.name,
                        dir_size,
                    )
                except OSError as exc:
                    logger.warning(
                        "Failed to delete session %s during size cleanup: %s",
                        entry.name,
                        exc,
                    )

        return deleted

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_session(self, session_id: str, format: str = "html") -> str:
        """Export a session as ``"html"``, ``"json"``, or ``"gif"``.

        Returns the absolute path to the exported file. Raises
        ``FileNotFoundError`` if the session does not exist, or
        ``ValueError`` if *format* is not recognised.
        """
        # Imported lazily so `SessionManager` does not drag PIL/base64
        # into callers that only want to list sessions.
        from pilot.core.session.exporter import (
            export_gif,
            export_html,
            export_json,
        )

        detail = self.get_session(session_id)
        session_dir = self._base_dir / session_id

        if format == "html":
            return export_html(detail, session_dir)
        elif format == "json":
            return export_json(detail, session_dir)
        elif format == "gif":
            return export_gif(detail, session_dir)
        else:
            raise ValueError(
                f"Unknown export format {format!r}. "
                "Expected 'html', 'json', or 'gif'."
            )

    # ------------------------------------------------------------------
    # Aggregate stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return aggregate statistics across all sessions."""
        sessions = self.list_sessions()
        total = len(sessions)

        if total == 0:
            return {
                "total_sessions": 0,
                "completed": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_steps": 0.0,
                "avg_duration": 0.0,
                "total_duration": 0.0,
            }

        completed = sum(1 for s in sessions if s.status == "completed")
        failed = sum(1 for s in sessions if s.status == "failed")
        total_steps = sum(s.steps for s in sessions)
        total_duration = sum(s.duration for s in sessions)

        return {
            "total_sessions": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / total, 3) if total else 0.0,
            "avg_steps": round(total_steps / total, 1),
            "avg_duration": round(total_duration / total, 1),
            "total_duration": round(total_duration, 1),
        }
