"""SQLite run records survive construction of a new store instance."""

from pathlib import Path

from agent_service.contracts import AgentRequest, StoredRun
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
