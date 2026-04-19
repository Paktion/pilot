"""UsageTracker — token/cost accounting + budget enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from pilot.core.usage import UsageTracker


@pytest.fixture()
def tmp_usage(tmp_path: Path) -> Path:
    return tmp_path / "usage.json"


def test_record_call_and_cost(tmp_usage: Path) -> None:
    t = UsageTracker(storage_path=tmp_usage)
    rec = t.record_call(
        model="claude-sonnet-4-20250514",
        input_tokens=1000, output_tokens=500,
    )
    # 1000 input + 500 output at Sonnet pricing
    expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
    assert rec["cost"] == pytest.approx(round(expected, 6))
    assert t.get_daily_cost() == pytest.approx(round(expected, 6))


def test_budget_blocks_when_exceeded(tmp_usage: Path) -> None:
    t = UsageTracker(storage_path=tmp_usage, daily_budget=0.02)
    # Spend 0.018 (under budget).
    t.record_call(
        model="claude-sonnet-4-20250514",
        input_tokens=1000, output_tokens=1000,
    )
    # Next call of 0.01 would push us to 0.028 > 0.02.
    assert not t.check_budget(0.01)


def test_budget_allows_when_under(tmp_usage: Path) -> None:
    t = UsageTracker(storage_path=tmp_usage, daily_budget=100.0)
    assert t.check_budget(0.50)


def test_unknown_model_falls_back_to_sonnet(tmp_usage: Path) -> None:
    t = UsageTracker(storage_path=tmp_usage)
    rec = t.record_call(
        model="imaginary-model-2099",
        input_tokens=1000, output_tokens=1000,
    )
    assert rec["cost"] > 0


def test_per_task_budget_gates(tmp_usage: Path) -> None:
    t = UsageTracker(
        storage_path=tmp_usage, daily_budget=10.0, per_task_budget=0.01,
    )
    t.record_call(
        model="claude-sonnet-4-20250514",
        input_tokens=1000, output_tokens=0, task_id="alpha",
    )
    # Next call for task alpha above 0.01 should be rejected.
    assert not t.check_budget(0.05, task_id="alpha")
    # A fresh task within the per-task budget still succeeds.
    assert t.check_budget(0.005, task_id="beta")
    # And a fresh task OVER the per-task budget is blocked too.
    assert not t.check_budget(0.05, task_id="beta")


def test_round_trip_persistence(tmp_usage: Path) -> None:
    t = UsageTracker(storage_path=tmp_usage)
    t.record_call("claude-sonnet-4-20250514", 500, 200, task_id="t1")

    t2 = UsageTracker(storage_path=tmp_usage)
    assert t2.get_daily_cost() == t.get_daily_cost()
    assert t2.get_session_cost("t1") == t.get_session_cost("t1")
