"""Transactional local traces; JSONL interchange; optional DuckDB/Parquet analytics."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .schema import Run, canonical


class Store:
    def __init__(self, path: str | Path = "artifacts/traces.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, agent TEXT NOT NULL, task TEXT NOT NULL, started TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS runs_agent ON runs(agent, started)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, run: Run) -> None:
        # Validate again: callers may have mutated the dataclass since construction.
        value = Run.from_dict(run.to_dict())
        with self._connect() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET agent=excluded.agent, task=excluded.task, started=excluded.started, data=excluded.data",
                       (value.run_id, value.agent, value.task_id, value.started_at, canonical(value.to_dict())))

    def get(self, run_id: str) -> Run:
        with self._connect() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown run: {run_id}")
        return Run.from_dict(json.loads(row[0]))

    def list(self, agent: str | None = None) -> list[Run]:
        with self._connect() as db:
            if agent is None:
                rows = db.execute("SELECT data FROM runs ORDER BY started,id").fetchall()
            else:
                rows = db.execute("SELECT data FROM runs WHERE agent=? ORDER BY started,id", (agent,)).fetchall()
        return [Run.from_dict(json.loads(row[0])) for row in rows]

    def export_jsonl(self, path: str | Path, agent: str | None = None) -> int:
        runs = self.list(agent)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for run in runs:
                stream.write(canonical(run.to_dict()) + "\n")
        return len(runs)

    def import_jsonl(self, path: str | Path) -> int:
        # Validate the entire file before mutating the database.
        runs = [Run.from_dict(json.loads(line)) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        with self._connect() as db:
            db.executemany("INSERT INTO runs VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET agent=excluded.agent, task=excluded.task, started=excluded.started, data=excluded.data",
                           [(r.run_id, r.agent, r.task_id, r.started_at, canonical(r.to_dict())) for r in runs])
        return len(runs)

    def export_parquet(self, path: str | Path) -> int:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("Install pruefstand[analytics] for Parquet export") from exc
        import tempfile
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp, duckdb.connect() as db:
            source = Path(tmp) / "runs.jsonl"
            count = self.export_jsonl(source)
            if not count:
                raise ValueError("Cannot export an empty trace store")
            db.execute("CREATE TABLE traces AS SELECT * FROM read_json_auto(?, format='newline_delimited', maximum_depth=-1)", [str(source)])
            db.execute("COPY traces TO ? (FORMAT PARQUET)", [str(path.resolve())])
        return count
