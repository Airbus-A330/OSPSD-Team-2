"""Durable run storage used by the agent service."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Protocol

from agent_service.contracts import StoredRun


class RunStore(Protocol):
    """Persistence operations required by the agent loop."""

    def save(self, run_id: str, run: StoredRun) -> None:
        """Create or replace one durable run record."""

    def load(self, run_id: str) -> StoredRun | None:
        """Return a run record when it exists."""

    def finish(self, run_id: str, run: StoredRun) -> bool:
        """Persist a final result only if it wins against cancellation."""

    def cancel(self, run_id: str) -> bool:
        """Mark a known run cancelled and report whether it existed."""

    def is_cancelled(self, run_id: str) -> bool:
        """Return whether further work must stop for this run."""


class SQLiteRunStore:
    """Small SQLite-backed store that survives service restarts."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    cancelled INTEGER NOT NULL DEFAULT 0,
                    finished INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(agent_runs)"
                ).fetchall()
            }
            if "finished" not in columns:
                connection.execute(
                    "ALTER TABLE agent_runs ADD COLUMN finished INTEGER NOT NULL DEFAULT 0"
                )
                for run_id, payload in connection.execute(
                    "SELECT run_id, payload FROM agent_runs"
                ).fetchall():
                    run = StoredRun.model_validate_json(payload)
                    if run.result is not None:
                        connection.execute(
                            "UPDATE agent_runs SET finished = 1 WHERE run_id = ?",
                            (run_id,),
                        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=5)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def save(self, run_id: str, run: StoredRun) -> None:
        """Persist a validated run using one parameterized upsert."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (run_id, payload, cancelled)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload = excluded.payload
                """,
                (run_id, run.model_dump_json(), int(run.cancelled)),
            )

    def finish(self, run_id: str, run: StoredRun) -> bool:
        """Atomically let either accepted cancellation or finalization win."""
        expected_cancelled = int(run.cancelled)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET payload = ?, finished = 1
                WHERE run_id = ? AND finished = 0 AND cancelled = ?
                """,
                (run.model_dump_json(), run_id, expected_cancelled),
            )
        return cursor.rowcount == 1

    def load(self, run_id: str) -> StoredRun | None:
        """Load and revalidate a persisted run."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload, cancelled FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        run = StoredRun.model_validate_json(row[0])
        if bool(row[1]) == run.cancelled:
            return run
        return run.model_copy(update={"cancelled": bool(row[1])})

    def cancel(self, run_id: str) -> bool:
        """Atomically accept cancellation only while the run remains active."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET cancelled = 1
                WHERE run_id = ? AND finished = 0
                """,
                (run_id,),
            )
            if cursor.rowcount == 1:
                return True
            row = connection.execute(
                "SELECT payload, cancelled FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return False
            if bool(row[1]):
                return True
            run = StoredRun.model_validate_json(row[0])
            if run.result is None or run.result.status != "approval_required":
                return False
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET cancelled = 1
                WHERE run_id = ? AND finished = 1 AND cancelled = 0
                """,
                (run_id,),
            )
        return cursor.rowcount == 1

    def is_cancelled(self, run_id: str) -> bool:
        """Check cancellation at each model/tool boundary."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT cancelled FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return bool(row[0]) if row is not None else False
