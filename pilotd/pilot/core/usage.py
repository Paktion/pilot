"""
Claude API usage tracking and budget enforcement.

Persists every call to ``$PILOT_HOME/usage.json`` with token counts + cost,
enforces per-day and per-task budgets, trims the call log when it grows
beyond ``_MAX_CALLS``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pilot.core import paths

log = logging.getLogger("pilotd.usage")


class UsageTracker:
    """Tracks API usage, costs, and provides estimates."""

    PRICING: dict[str, dict[str, float]] = {
        "claude-sonnet-4-20250514":   {"input": 3.0, "output": 15.0},
        "claude-sonnet-4-5-20250514": {"input": 3.0, "output": 15.0},
        "claude-opus-4-20250514":     {"input": 15.0, "output": 75.0},
        "claude-haiku-4-5-20251001":  {"input": 0.80, "output": 4.0},
        "claude-haiku-3-20240307":    {"input": 0.25, "output": 1.25},
    }

    _MAX_CALLS = 10_000
    _DEFAULT_INPUT_TOKENS_PER_STEP = 5000
    _DEFAULT_OUTPUT_TOKENS_PER_STEP = 500

    def __init__(
        self,
        storage_path: str | Path | None = None,
        daily_budget: float = 5.0,
        per_task_budget: float = 1.0,
    ) -> None:
        self._storage_path = (
            Path(storage_path).expanduser() if storage_path else paths.usage_path()
        )
        self._daily_budget = daily_budget
        self._per_task_budget = per_task_budget
        self._data: dict[str, Any] = {"calls": [], "daily_totals": {}}
        self._load()

    def record_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        cost = self._compute_cost(model, input_tokens, output_tokens)
        now = datetime.now(timezone.utc)
        record = {
            "timestamp": now.isoformat(timespec="seconds"),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 6),
            "task_id": task_id or str(uuid.uuid4())[:8],
        }
        self._data["calls"].append(record)
        day_key = now.strftime("%Y-%m-%d")
        day = self._data["daily_totals"].setdefault(
            day_key,
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        day["calls"] += 1
        day["input_tokens"] += input_tokens
        day["output_tokens"] += output_tokens
        day["cost"] = round(day["cost"] + cost, 6)
        self._trim_calls()
        self._save()
        return record

    def check_budget(self, estimated_cost: float, task_id: str | None = None) -> bool:
        daily_cost = self.get_daily_cost()
        if daily_cost + estimated_cost > self._daily_budget:
            log.warning(
                "Daily budget would be exceeded: $%.4f + $%.4f > $%.2f",
                daily_cost, estimated_cost, self._daily_budget,
            )
            return False
        if task_id is not None:
            task_cost = self.get_session_cost(task_id)
            if task_cost + estimated_cost > self._per_task_budget:
                log.warning(
                    "Per-task budget exceeded for %s: $%.4f + $%.4f > $%.2f",
                    task_id, task_cost, estimated_cost, self._per_task_budget,
                )
                return False
        return True

    def get_session_cost(self, task_id: str | None = None) -> float:
        calls = self._data["calls"]
        if task_id is not None:
            calls = [c for c in calls if c.get("task_id") == task_id]
        return round(sum(c.get("cost", 0.0) for c in calls), 6)

    def get_daily_cost(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day = self._data["daily_totals"].get(today)
        return round(day.get("cost", 0.0) if day else 0.0, 6)

    def get_monthly_cost(self) -> float:
        prefix = datetime.now(timezone.utc).strftime("%Y-%m")
        total = sum(
            day.get("cost", 0.0)
            for key, day in self._data["daily_totals"].items()
            if key.startswith(prefix)
        )
        return round(total, 6)

    def get_total_cost(self) -> float:
        return round(
            sum(d.get("cost", 0.0) for d in self._data["daily_totals"].values()), 6
        )

    def estimate_task_cost(self, model: str, estimated_steps: int = 10) -> float:
        model_calls = [c for c in self._data["calls"] if c.get("model") == model]
        if model_calls:
            avg_in = sum(c["input_tokens"] for c in model_calls) / len(model_calls)
            avg_out = sum(c["output_tokens"] for c in model_calls) / len(model_calls)
        else:
            avg_in = self._DEFAULT_INPUT_TOKENS_PER_STEP
            avg_out = self._DEFAULT_OUTPUT_TOKENS_PER_STEP
        per_step = self._compute_cost(model, int(avg_in), int(avg_out))
        return round(per_step * estimated_steps, 6)

    def get_usage_summary(self) -> dict[str, Any]:
        calls = self._data["calls"]
        tasks = {c.get("task_id") for c in calls if c.get("task_id")}
        total_cost = self.get_total_cost()
        return {
            "total_calls": len(calls),
            "total_input_tokens": sum(c.get("input_tokens", 0) for c in calls),
            "total_output_tokens": sum(c.get("output_tokens", 0) for c in calls),
            "total_cost": round(total_cost, 6),
            "avg_cost_per_task": round(total_cost / len(tasks), 6) if tasks else 0.0,
        }

    def get_usage_report(self, days: int = 30) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        report: list[dict[str, Any]] = []
        for offset in range(days):
            day_key = (today - timedelta(days=offset)).isoformat()
            totals = self._data["daily_totals"].get(day_key)
            if totals:
                report.append({"date": day_key, **totals})
            else:
                report.append({
                    "date": day_key, "calls": 0, "input_tokens": 0,
                    "output_tokens": 0, "cost": 0.0,
                })
        return report

    def _compute_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = self.PRICING.get(model)
        if pricing is None:
            log.warning("Unknown model %r — falling back to Sonnet pricing", model)
            pricing = self.PRICING["claude-sonnet-4-20250514"]
        return (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

    def _trim_calls(self) -> None:
        calls = self._data["calls"]
        if len(calls) <= self._MAX_CALLS:
            return
        calls.sort(key=lambda c: c.get("timestamp", ""))
        trim = len(calls) - (self._MAX_CALLS // 2)
        self._data["calls"] = calls[trim:]
        log.info("Trimmed %d old call records", trim)

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            self._data["calls"] = stored.get("calls", [])
            self._data["daily_totals"] = stored.get("daily_totals", {})
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._storage_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, default=str)
                fh.write("\n")
            tmp.replace(self._storage_path)
        except OSError:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def __repr__(self) -> str:
        return f"UsageTracker(path={self._storage_path!s}, calls={len(self._data['calls'])})"
