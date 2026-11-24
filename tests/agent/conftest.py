"""Shared controlled agent-service fixtures."""

from pathlib import Path

import pytest
from calendar_contract import Event

from agent_service.model import ScriptedModel
from agent_service.service import AgentLimits, AgentService
from agent_service.store import SQLiteRunStore
from agent_service.tools import ApiServiceClient, ToolRegistry


class ControlledApi:
    """API-service boundary fake; it is not a provider fake."""

    def __init__(self, *, title: str = "Project kickoff") -> None:
        self.title = title
        self.event_ids: list[str] = []
        self.timeouts: list[float | None] = []

    def get_event(
        self, event_id: str, *, timeout_seconds: float | None = None
    ) -> Event:
        self.event_ids.append(event_id)
        self.timeouts.append(timeout_seconds)
        return Event(
            id=event_id,
            title=self.title,
            start="2030-01-07T15:00:00Z",
            end="2030-01-07T15:30:00Z",
        )


@pytest.fixture
def controlled_api() -> ControlledApi:
    return ControlledApi()


def build_service(
    tmp_path: Path,
    model: ScriptedModel,
    api: ApiServiceClient,
    *,
    limits: AgentLimits | None = None,
) -> AgentService:
    return AgentService(
        model=model,
        tools=ToolRegistry(api),
        store=SQLiteRunStore(tmp_path / "agent.sqlite3"),
        limits=limits or AgentLimits(),
    )
