"""prompts.py — file-first loader with env fallback."""

from __future__ import annotations

import os

import pytest

from pilot import prompts


@pytest.fixture
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Redirect PILOT_HOME to a tmp dir so file lookups don't leak across tests."""
    monkeypatch.setenv("PILOT_HOME", str(tmp_path))
    return tmp_path


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch, isolated_home) -> None:
    for name in prompts.REQUIRED:
        monkeypatch.delenv(f"PILOT_PROMPT_{name}", raising=False)
    with pytest.raises(prompts.PromptConfigError):
        prompts.get("DRAFT_WORKFLOW")


def test_empty_value_raises(monkeypatch: pytest.MonkeyPatch, isolated_home) -> None:
    for name in prompts.REQUIRED:
        monkeypatch.delenv(f"PILOT_PROMPT_{name}", raising=False)
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "   \n  ")
    with pytest.raises(prompts.PromptConfigError):
        prompts.get("DRAFT_WORKFLOW")


def test_round_trip_env(monkeypatch: pytest.MonkeyPatch, isolated_home) -> None:
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "hello")
    assert prompts.get("DRAFT_WORKFLOW") == "hello"
    assert prompts.get("PILOT_PROMPT_DRAFT_WORKFLOW") == "hello"


def test_round_trip_file(monkeypatch: pytest.MonkeyPatch, isolated_home) -> None:
    monkeypatch.delenv("PILOT_PROMPT_DRAFT_WORKFLOW", raising=False)
    prompts_dir = isolated_home / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "draft_workflow.md").write_text("file-wins\n")
    assert prompts.get("DRAFT_WORKFLOW") == "file-wins"


def test_file_beats_env(monkeypatch: pytest.MonkeyPatch, isolated_home) -> None:
    """File takes precedence — lets you iterate without restarting the daemon."""
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "from-env")
    prompts_dir = isolated_home / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "draft_workflow.md").write_text("from-file\n")
    assert prompts.get("DRAFT_WORKFLOW") == "from-file"


def test_snapshot_shape(monkeypatch: pytest.MonkeyPatch, isolated_home) -> None:
    monkeypatch.setenv("PILOT_PROMPT_DRAFT_WORKFLOW", "xyz")
    snap = prompts.snapshot()
    assert set(snap.keys()) == set(prompts.REQUIRED)
    assert snap["DRAFT_WORKFLOW"] == 3


def test_require_all_reports_missing(
    monkeypatch: pytest.MonkeyPatch, isolated_home
) -> None:
    for name in prompts.REQUIRED:
        monkeypatch.setenv(f"PILOT_PROMPT_{name}", "x")
    prompts.require_all()

    monkeypatch.delenv("PILOT_PROMPT_CRON_PARSE")
    with pytest.raises(prompts.PromptConfigError) as exc:
        prompts.require_all()
    assert "CRON_PARSE" in str(exc.value)


def test_prompts_never_logged_in_snapshot(
    monkeypatch: pytest.MonkeyPatch, isolated_home
) -> None:
    secret = "this-should-never-leak"
    monkeypatch.setenv("PILOT_PROMPT_AGENT_SYSTEM", secret)
    snap = prompts.snapshot()
    assert secret not in repr(snap)
    assert all(isinstance(v, int) for v in snap.values())
    _ = os.environ
