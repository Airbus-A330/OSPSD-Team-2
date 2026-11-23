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
                    cancelled INTEGER NOT NULL DEFAULT 0
                )
                """
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
                    payload = excluded.payload,
                    cancelled = excluded.cancelled
                """,
                (run_id, run.model_dump_json(), int(run.cancelled)),
            )

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
        """Persist cancellation without changing the prior run result."""
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE agent_runs SET cancelled = 1 WHERE run_id = ?", (run_id,)
            )
        return cursor.rowcount == 1

    def is_cancelled(self, run_id: str) -> bool:
        """Check cancellation at each model/tool boundary."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT cancelled FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return bool(row[0]) if row is not None else False
