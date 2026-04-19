"""prompts.py — env-var loader invariants."""

from __future__ import annotations

import os

import pytest

from pilot import prompts


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in prompts.REQUIRED:
        monkeypatch.delenv(f"PILOT_PROMPT_{name}", raising=False)
    with pytest.raises(prompts.PromptConfigError):
        prompts.get("DRAFT_WORKFLOW")


def test_empty_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "   \n  ")
    with pytest.raises(prompts.PromptConfigError):
        prompts.get("DRAFT_WORKFLOW")


def test_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "hello")
    assert prompts.get("DRAFT_WORKFLOW") == "hello"
    assert prompts.get("PILOT_PROMPT_DRAFT_WORKFLOW") == "hello"


def test_snapshot_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "xyz")
    snap = prompts.snapshot()
    assert set(snap.keys()) == set(prompts.REQUIRED)
    assert snap["DRAFT_WORKFLOW"] == 3


def test_require_all_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in prompts.REQUIRED:
        monkeypatch.setenv(f"PILOT_PROMPT_{name}", "x")
    prompts.require_all()  # should not raise

    monkeypatch.delenv("PILOT_PROMPT_CRON_PARSE")
    with pytest.raises(prompts.PromptConfigError) as exc:
        prompts.require_all()
    assert "PILOT_PROMPT_CRON_PARSE" in str(exc.value)


def test_prompts_never_logged_in_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "this-should-never-leak"
    monkeypatch.setenv("PILOT_PROMPT_AGENT_SYSTEM", secret)
    snap = prompts.snapshot()
    assert secret not in repr(snap)
    assert all(isinstance(v, int) for v in snap.values())
    _ = os.environ  # quiet unused-import-ish linters
