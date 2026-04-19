"""
Semantic memory over SQLite + sqlite-vec.

Replaces the JSON-file memory from the reference implementation with a single
local DB that holds workflows, runs, schedules, freeform memory rows, and
384-dim embeddings via the ``vec0`` virtual table.

Tables
------
* ``workflows``       — persisted workflow metadata and YAML source
* ``runs``            — execution history per workflow
* ``schedules``       — APScheduler-adjacent persisted schedule entries
* ``memory``          — key/value/kind facts scoped to workflow or global
* ``memory_vec``      — vector index (vec0 virtual table), joined by id
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlite_vec

from pilot.core import paths
from pilot.embedding import EMBED_DIM, Embedder, pack_vector

log = logging.getLogger("pilotd.memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    app TEXT,
    yaml TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_run_at TEXT,
    run_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    compiled_path TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    summary TEXT,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    session_path TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id),
    cron_expr TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_fired_at TEXT
);

CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY,
    workflow_id TEXT,
    run_id TEXT,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_memory_workflow ON memory(workflow_id);
CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(workflow_id, key);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore:
    """Thread-safe SQLite wrapper with vec0 vector search."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or paths.db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._embedder: Embedder | None = None
        self._init_db()

    @contextlib.contextmanager
    def _conn(self):
        with self._lock:
            conn = sqlite3.connect(str(self._path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec
                USING vec0(id TEXT PRIMARY KEY, embedding float[{EMBED_DIM}]);
                """
            )

    def _lazy_embedder(self) -> "Embedder":
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    # ---- workflows ---------------------------------------------------------

    def upsert_workflow(
        self,
        *,
        id: str | None = None,
        name: str,
        app: str | None,
        yaml_text: str,
    ) -> str:
        wf_id = id or str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM workflows WHERE id=? OR name=?",
                (wf_id, name),
            ).fetchone()
            if existing:
                wf_id = existing["id"]
                conn.execute(
                    """UPDATE workflows
                       SET name=?, app=?, yaml=?, updated_at=?
                       WHERE id=?""",
                    (name, app, yaml_text, now, wf_id),
                )
            else:
                conn.execute(
                    """INSERT INTO workflows
                       (id, name, app, yaml, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (wf_id, name, app, yaml_text, now, now),
                )
        # Embed outside the write lock window.
        self._embed_workflow_descriptor(wf_id, name, app, yaml_text)
        return wf_id

    def _embed_workflow_descriptor(
        self, wf_id: str, name: str, app: str | None, yaml_text: str
    ) -> None:
        text = f"{name} — {app or ''}\n{yaml_text[:2000]}"
        emb = self._lazy_embedder().encode(text)
        with self._conn() as conn:
            conn.execute("DELETE FROM memory WHERE id=?", (f"wf:{wf_id}",))
            conn.execute(
                """INSERT INTO memory
                   (id, workflow_id, run_id, kind, key, value_json, created_at)
                   VALUES (?, ?, NULL, 'workflow_descriptor', 'descriptor', ?, ?)""",
                (f"wf:{wf_id}", wf_id, json.dumps({"text": text}), _now()),
            )
            conn.execute("DELETE FROM memory_vec WHERE id=?", (f"wf:{wf_id}",))
            conn.execute(
                "INSERT INTO memory_vec(id, embedding) VALUES (?, ?)",
                (f"wf:{wf_id}", pack_vector(emb)),
            )

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, name, app, created_at, updated_at, last_run_at,
                          run_count, success_count, compiled_path
                   FROM workflows ORDER BY updated_at DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_workflow_by_name(self, name: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE name=?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def delete_workflow(self, workflow_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
            conn.execute("DELETE FROM memory WHERE workflow_id=?", (workflow_id,))
            conn.execute(
                "DELETE FROM memory_vec WHERE id IN ("
                "  SELECT id FROM memory WHERE workflow_id=?)",
                (workflow_id,),
            )

    # ---- runs --------------------------------------------------------------

    def start_run(self, workflow_id: str, run_id: str | None = None) -> str:
        rid = run_id or str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO runs (id, workflow_id, started_at, status)
                   VALUES (?, ?, ?, 'running')""",
                (rid, workflow_id, _now()),
            )
        return rid

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        summary: str = "",
        cost_usd: float = 0.0,
        session_path: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE runs
                   SET ended_at=?, status=?, summary=?, cost_usd=?, session_path=?
                   WHERE id=?""",
                (_now(), status, summary, cost_usd, session_path, run_id),
            )
            row = conn.execute(
                "SELECT workflow_id FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            if row:
                if status == "success":
                    conn.execute(
                        """UPDATE workflows
                           SET run_count=run_count+1, success_count=success_count+1,
                               last_run_at=?
                           WHERE id=?""",
                        (_now(), row["workflow_id"]),
                    )
                else:
                    conn.execute(
                        """UPDATE workflows
                           SET run_count=run_count+1, last_run_at=?
                           WHERE id=?""",
                        (_now(), row["workflow_id"]),
                    )

    def list_runs(self, workflow_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if workflow_id:
                rows = conn.execute(
                    """SELECT * FROM runs WHERE workflow_id=?
                       ORDER BY started_at DESC LIMIT ?""",
                    (workflow_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def recent_successes(self, workflow_id: str, n: int = 3) -> int:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT status FROM runs WHERE workflow_id=?
                   ORDER BY started_at DESC LIMIT ?""",
                (workflow_id, n),
            ).fetchall()
            return sum(1 for r in rows if r["status"] == "success")

    # ---- memory / facts ----------------------------------------------------

    def remember(
        self,
        *,
        workflow_id: str | None,
        run_id: str | None,
        kind: str,
        key: str,
        value: Any,
    ) -> str:
        entry_id = str(uuid.uuid4())
        text = f"{kind}:{key} {json.dumps(value)[:500]}"
        emb = self._lazy_embedder().encode(text)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO memory
                   (id, workflow_id, run_id, kind, key, value_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    workflow_id,
                    run_id,
                    kind,
                    key,
                    json.dumps(value),
                    _now(),
                ),
            )
            conn.execute(
                "INSERT INTO memory_vec(id, embedding) VALUES (?, ?)",
                (entry_id, pack_vector(emb)),
            )
        return entry_id

    def recall(
        self, *, workflow_id: str | None, key: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if workflow_id is None:
                rows = conn.execute(
                    """SELECT * FROM memory WHERE key=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (key, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM memory
                       WHERE (workflow_id=? OR workflow_id IS NULL) AND key=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (workflow_id, key, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    def search_similar(
        self, *, query_text: str, workflow_id: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        emb = self._lazy_embedder().encode(query_text)
        with self._conn() as conn:
            if workflow_id:
                rows = conn.execute(
                    """SELECT m.id, m.workflow_id, m.run_id, m.kind, m.key,
                              m.value_json, m.created_at,
                              vec_distance_L2(v.embedding, ?) AS distance
                       FROM memory_vec v
                       JOIN memory m ON m.id = v.id
                       WHERE m.workflow_id=? OR m.workflow_id IS NULL
                       ORDER BY distance ASC
                       LIMIT ?""",
                    (pack_vector(emb), workflow_id, k),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT m.id, m.workflow_id, m.run_id, m.kind, m.key,
                              m.value_json, m.created_at,
                              vec_distance_L2(v.embedding, ?) AS distance
                       FROM memory_vec v
                       JOIN memory m ON m.id = v.id
                       ORDER BY distance ASC
                       LIMIT ?""",
                    (pack_vector(emb), k),
                ).fetchall()
            return [dict(r) for r in rows]

    # ---- navigation hints --------------------------------------------------

    def remember_navigation(
        self,
        *,
        app: str,
        target: str,
        scrolls: int,
        workflow_id: str | None = None,
    ) -> None:
        """Persist 'to reach ``target`` in ``app``, scroll N times'.

        Always last-write-wins — we want the most recent observed count, not
        the average, so the happy path on the next run is fast.
        """
        key = f"nav:{app}:{target}"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id FROM memory WHERE key=?", (key,)
            ).fetchall()
            for r in rows:
                conn.execute("DELETE FROM memory_vec WHERE id=?", (r["id"],))
                conn.execute("DELETE FROM memory WHERE id=?", (r["id"],))
        self.remember(
            workflow_id=workflow_id,
            run_id=None,
            kind="navigation",
            key=key,
            value={"app": app, "target": target, "scrolls": int(scrolls)},
        )

    def get_navigation_hint(self, *, app: str, target: str) -> dict | None:
        import json as _json
        key = f"nav:{app}:{target}"
        rows = self.recall(workflow_id=None, key=key, limit=1)
        if not rows:
            return None
        try:
            return _json.loads(rows[0]["value_json"])
        except (TypeError, _json.JSONDecodeError):
            return None

    def numeric_values(
        self, *, workflow_id: str | None, key: str, limit: int = 6
    ) -> list[float]:
        """Return the last ``limit`` numeric values stored for a key.

        Non-numeric rows are skipped silently.
        """
        rows = self.recall(workflow_id=workflow_id, key=key, limit=limit * 3)
        out: list[float] = []
        for r in rows:
            try:
                v = json.loads(r["value_json"])
                out.append(float(v))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if len(out) >= limit:
                break
        return out


