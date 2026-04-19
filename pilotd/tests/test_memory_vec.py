"""Memory store — sqlite + vec0 round-trip."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pilot.memory_vec import MemoryStore


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "memory.db"
    monkeypatch.setenv("PILOT_HOME", str(tmp_path))
    return db


def test_workflow_crud(tmp_db: Path) -> None:
    store = MemoryStore(db_path=tmp_db)
    wf_id = store.upsert_workflow(
        name="Test WF", app="App",
        yaml_text="name: Test WF\nsteps:\n  - launch: X\n",
    )
    rows = store.list_workflows()
    assert len(rows) == 1 and rows[0]["name"] == "Test WF"

    fetched = store.get_workflow(wf_id)
    assert fetched is not None and fetched["app"] == "App"

    # Idempotent upsert by name.
    wf_id2 = store.upsert_workflow(
        name="Test WF", app="App2",
        yaml_text="name: Test WF\nsteps:\n  - launch: Y\n",
    )
    assert wf_id == wf_id2
    fetched = store.get_workflow(wf_id)
    assert fetched["app"] == "App2"

    store.delete_workflow(wf_id)
    assert store.list_workflows() == []


def test_runs_lifecycle(tmp_db: Path) -> None:
    store = MemoryStore(db_path=tmp_db)
    wf_id = store.upsert_workflow(
        name="Runs", app=None,
        yaml_text="name: Runs\nsteps:\n  - launch: A\n",
    )
    rid = store.start_run(wf_id)
    store.finish_run(rid, status="success", summary="ok", cost_usd=0.015)
    runs = store.list_runs(workflow_id=wf_id)
    assert len(runs) == 1 and runs[0]["status"] == "success"

    wf = store.get_workflow(wf_id)
    assert wf is not None
    assert wf["run_count"] == 1
    assert wf["success_count"] == 1


def test_recent_successes(tmp_db: Path) -> None:
    store = MemoryStore(db_path=tmp_db)
    wf_id = store.upsert_workflow(
        name="Streak", app=None,
        yaml_text="name: Streak\nsteps:\n  - launch: A\n",
    )
    for _ in range(3):
        rid = store.start_run(wf_id)
        store.finish_run(rid, status="success", summary="", cost_usd=0)
    assert store.recent_successes(wf_id, n=3) == 3


def test_remember_and_recall(tmp_db: Path) -> None:
    store = MemoryStore(db_path=tmp_db)
    wf_id = store.upsert_workflow(
        name="WF", app=None,
        yaml_text="name: WF\nsteps:\n  - launch: A\n",
    )
    store.remember(
        workflow_id=wf_id, run_id=None, kind="observation",
        key="last_bill", value=42.50,
    )
    rows = store.recall(workflow_id=wf_id, key="last_bill")
    assert len(rows) == 1
    assert rows[0]["kind"] == "observation"


def test_numeric_values(tmp_db: Path) -> None:
    store = MemoryStore(db_path=tmp_db)
    store.upsert_workflow(
        name="Bill", app=None,
        yaml_text="name: Bill\nsteps:\n  - launch: A\n",
    )
    for val in [12.50, 15.00, 11.75, 13.20]:
        store.remember(
            workflow_id=None, run_id=None, kind="observation",
            key="last_bill", value=val,
        )
    vals = store.numeric_values(workflow_id=None, key="last_bill", limit=6)
    assert set(vals) == {12.50, 15.00, 11.75, 13.20}


def test_vector_search_returns_results(tmp_db: Path) -> None:
    store = MemoryStore(db_path=tmp_db)
    wf_id = store.upsert_workflow(
        name="Chipotle reorder", app="Grubhub",
        yaml_text="name: Chipotle reorder\nsteps:\n  - launch: Grubhub\n",
    )
    # Record semantic rows.
    store.remember(
        workflow_id=wf_id, run_id=None, kind="observation",
        key="last_total", value="$11.47",
    )
    hits = store.search_similar(query_text="burrito bowl total", workflow_id=wf_id, k=3)
    # Both the workflow descriptor and the observation row should surface.
    assert len(hits) >= 1
    assert "distance" in hits[0]
