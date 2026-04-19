"""Compiled-skill snapshot format + freshness detection."""

from __future__ import annotations

import json
from pathlib import Path

from pilot.workflow_compiler import (
    RecordingBuffer,
    compile_snapshot,
    is_snapshot_fresh,
    load_snapshot,
    should_compile,
)


def _write_yaml(path: Path) -> str:
    text = "name: Test\nsteps:\n  - launch: A\n"
    path.write_text(text)
    return text


def test_compile_snapshot_round_trip(tmp_path: Path) -> None:
    yaml_path = tmp_path / "skill.yaml"
    yaml_text = _write_yaml(yaml_path)
    buf = RecordingBuffer(device_width=410, device_height=898)
    buf.record_tap(index=0, label="Reorder", x=205.5, y=342.0)
    buf.record_wait(index=1, label="Chipotle")
    buf.record_passthrough(index=2, step_type="type_text", label="hello")

    out = compile_snapshot(
        source_yaml_path=yaml_path,
        source_yaml_text=yaml_text,
        recording=buf,
    )
    loaded = load_snapshot(out)
    assert loaded is not None
    assert loaded["version"] == 2
    assert loaded["device"]["windowWidth"] == 410
    assert len(loaded["steps"]) == 3
    assert loaded["steps"][0]["hints"]["compiledAction"] == "tap"
    assert loaded["steps"][0]["hints"]["tapX"] == 205.5


def test_freshness_hash_mismatch(tmp_path: Path) -> None:
    yaml_path = tmp_path / "skill.yaml"
    yaml_text = _write_yaml(yaml_path)
    buf = RecordingBuffer(device_width=410, device_height=898)
    buf.record_tap(index=0, label="X", x=10.0, y=10.0)
    out = compile_snapshot(
        source_yaml_path=yaml_path,
        source_yaml_text=yaml_text,
        recording=buf,
    )
    snap = load_snapshot(out)
    assert snap is not None
    assert is_snapshot_fresh(snap, current_source=yaml_text, current_width=410, current_height=898)
    # Change source → stale.
    assert not is_snapshot_fresh(
        snap, current_source=yaml_text + "# edited\n", current_width=410, current_height=898
    )


def test_freshness_dimension_drift(tmp_path: Path) -> None:
    yaml_path = tmp_path / "skill.yaml"
    yaml_text = _write_yaml(yaml_path)
    buf = RecordingBuffer(device_width=410, device_height=898)
    buf.record_tap(index=0, label="X", x=10.0, y=10.0)
    out = compile_snapshot(
        source_yaml_path=yaml_path,
        source_yaml_text=yaml_text,
        recording=buf,
    )
    snap = load_snapshot(out)
    assert snap is not None
    # Large drift → stale.
    assert not is_snapshot_fresh(
        snap, current_source=yaml_text, current_width=300, current_height=700
    )


def test_should_compile_threshold() -> None:
    assert not should_compile(0)
    assert not should_compile(2)
    assert should_compile(3)
    assert should_compile(10)
