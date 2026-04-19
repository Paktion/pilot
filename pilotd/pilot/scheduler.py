"""
APScheduler + SQLAlchemyJobStore wrapper.

Schedules live in the same SQLite file as the memory store, with a distinct
prefix so APScheduler's tables don't collide with ours.

The pre-run gate verifies iPhone Mirroring is available. If not, the job
reschedules itself for +10 min, posts a macOS notification, and after 3
consecutive failures marks the run ``status=skipped``.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from pilot.core import paths
from pilot.core.utils.sys_checks import check_iphone_mirroring_window

log = logging.getLogger("pilotd.scheduler")

# Maximum consecutive pre-run gate failures before a job is skipped.
MAX_GATE_RETRIES = 3
RETRY_DELAY_MIN = 10


class Scheduler:
    """Persistent scheduler with a Mirroring-window pre-run gate."""

    def __init__(
        self,
        run_callable: Callable[[str, dict[str, Any]], Any],
        db_path: Path | None = None,
    ) -> None:
        self._db_path = db_path or paths.db_path()
        self._run = run_callable
        self._scheduler = self._build_scheduler()
        self._retry_counts: dict[str, int] = {}
        self._lock = threading.RLock()

    def _build_scheduler(self) -> BackgroundScheduler:
        jobstore = SQLAlchemyJobStore(url=f"sqlite:///{self._db_path}")
        executors = {"default": ThreadPoolExecutor(2)}
        return BackgroundScheduler(
            jobstores={"default": jobstore},
            executors=executors,
            timezone="UTC",
            job_defaults={"coalesce": True, "max_instances": 1},
        )

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            log.info("scheduler started, db=%s", self._db_path)

    def shutdown(self, wait: bool = False) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    # -----------------------------------------------------------------------
    # Job lifecycle
    # -----------------------------------------------------------------------

    def add_job(
        self,
        *,
        workflow_name: str,
        cron_expr: str,
        params: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> str:
        jid = job_id or str(uuid.uuid4())
        trigger = CronTrigger.from_crontab(cron_expr, timezone="UTC")
        self._scheduler.add_job(
            func=_gated_run_callable,
            trigger=trigger,
            id=jid,
            args=[workflow_name, params or {}],
            replace_existing=True,
            name=workflow_name,
        )
        log.info("scheduled %s (%s) id=%s", workflow_name, cron_expr, jid)
        return jid

    def run_now(self, workflow_name: str, params: dict[str, Any] | None = None) -> str:
        jid = f"adhoc-{uuid.uuid4()}"
        self._scheduler.add_job(
            func=_gated_run_callable,
            id=jid,
            args=[workflow_name, params or {}],
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
        return jid

    def list_jobs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for job in self._scheduler.get_jobs():
            out.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return out

    def pause_job(self, job_id: str) -> None:
        self._scheduler.pause_job(job_id)

    def resume_job(self, job_id: str) -> None:
        self._scheduler.resume_job(job_id)

    def remove_job(self, job_id: str) -> None:
        try:
            self._scheduler.remove_job(job_id)
        except Exception as exc:
            log.warning("remove_job(%s) failed: %s", job_id, exc)

    # -----------------------------------------------------------------------
    # Gate
    # -----------------------------------------------------------------------

    def _gate(self, workflow_name: str) -> bool:
        ok, desc = check_iphone_mirroring_window()
        if ok:
            self._retry_counts.pop(workflow_name, None)
            return True
        count = self._retry_counts.get(workflow_name, 0) + 1
        self._retry_counts[workflow_name] = count
        log.warning(
            "pre-run gate failed for %s (attempt %d): %s",
            workflow_name, count, desc,
        )
        _notify(
            title="Pilot — workflow skipped",
            message=(
                f"'{workflow_name}' could not run: iPhone Mirroring not available. "
                f"Retry {count}/{MAX_GATE_RETRIES}."
            ),
        )
        if count >= MAX_GATE_RETRIES:
            self._retry_counts.pop(workflow_name, None)
        return False

    def _reschedule_soon(self, workflow_name: str, params: dict[str, Any]) -> None:
        jid = f"retry-{uuid.uuid4()}"
        self._scheduler.add_job(
            func=_gated_run_callable,
            id=jid,
            args=[workflow_name, params],
            next_run_time=(
                datetime.now(timezone.utc) + timedelta(minutes=RETRY_DELAY_MIN)
            ),
        )


# A module-level callable that APScheduler can pickle + persist.
# APScheduler requires jobs to reference module-level callables.
_INSTANCE: Scheduler | None = None


def register(instance: Scheduler) -> None:
    """Register a singleton Scheduler so persisted jobs can reach it."""
    global _INSTANCE
    _INSTANCE = instance


def _gated_run_callable(workflow_name: str, params: dict[str, Any]) -> Any:
    inst = _INSTANCE
    if inst is None:
        log.error("scheduler fired but no Scheduler instance is registered")
        return None
    if not inst._gate(workflow_name):
        count = inst._retry_counts.get(workflow_name, MAX_GATE_RETRIES)
        if count < MAX_GATE_RETRIES:
            inst._reschedule_soon(workflow_name, params)
        return None
    try:
        return inst._run(workflow_name, params)
    except Exception as exc:
        log.exception("scheduled run of %s failed: %s", workflow_name, exc)
        return None


def _notify(*, title: str, message: str) -> None:
    """Post a macOS user notification via osascript — best-effort."""
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    try:
        subprocess.run(
            ["osascript", "-e", script], capture_output=True, timeout=5, check=False
        )
    except Exception:  # notifications are non-critical
        pass


def _escape(s: str) -> str:
    """Escape a string for safe embedding in an osascript double-quoted literal.

    Backslashes, quotes, and newlines all need to be neutralized —
    unescaped newlines would break out of the quoted string and let a
    workflow name inject additional AppleScript.
    """
    return (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
         .replace("\n", " ")
         .replace("\r", " ")
    )
