"""SQLite run records survive construction of a new store instance."""

from pathlib import Path
import sqlite3

from agent_service.contracts import AgentRequest, AgentRunResult, ModelUsage, StoredRun
from agent_service.store import SQLiteRunStore


def test_run_and_cancellation_survive_store_restart(tmp_path: Path) -> None:
    database = tmp_path / "agent.sqlite3"
    first = SQLiteRunStore(database)
    first.save("run-1", StoredRun(request=AgentRequest(goal="Prepare a kickoff")))

    restarted = SQLiteRunStore(database)
    assert restarted.load("run-1") == StoredRun(
        request=AgentRequest(goal="Prepare a kickoff")
    )
    assert restarted.cancel("run-1") is True

    third = SQLiteRunStore(database)
    assert third.is_cancelled("run-1") is True
    assert third.load("run-1") == StoredRun(
        request=AgentRequest(goal="Prepare a kickoff"), cancelled=True
    )
    assert third.cancel("missing") is False


def test_accepted_cancellation_cannot_be_overwritten_by_completion(
    tmp_path: Path,
) -> None:
    store = SQLiteRunStore(tmp_path / "agent.sqlite3")
    request = AgentRequest(goal="Prepare a kickoff")
    store.save("run-1", StoredRun(request=request))

    assert store.cancel("run-1") is True
    assert store.finish("run-1", StoredRun(request=request)) is False
    assert store.finish("run-1", StoredRun(request=request, cancelled=True)) is True
    persisted = store.load("run-1")
    assert persisted is not None and persisted.cancelled is True


def test_schema_migration_keeps_existing_terminal_run_finished(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    terminal = StoredRun(
        request=AgentRequest(goal="Completed before migration"),
        result=AgentRunResult(
            run_id="run-1",
            conversation_id="conversation-1",
            status="completed",
            message="Done",
            model_provider="controlled",
            model_version="v1",
            prompt_version="agent-kickoff-v1",
            trace=[],
            usage=ModelUsage(),
        ),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE agent_runs (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                cancelled INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            "INSERT INTO agent_runs (run_id, payload, cancelled) VALUES (?, ?, 0)",
            ("run-1", terminal.model_dump_json()),
        )

    migrated = SQLiteRunStore(database)

    assert migrated.load("run-1") == terminal
    assert migrated.cancel("run-1") is False
