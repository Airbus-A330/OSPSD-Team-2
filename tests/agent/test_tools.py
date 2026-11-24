"""Tool contracts validate model output and never bypass the API service."""

from calendar_contract import Event
import pytest
from pydantic import JsonValue

from agent_service.contracts import ToolCall
from agent_service.tools import ToolRegistry, ToolRejectedError
from tests.agent.conftest import ControlledApi

KICKOFF_ARGUMENTS: dict[str, JsonValue] = {
    "event": {
        "title": "Agent kickoff",
        "start": "2030-01-07T15:00:00Z",
        "end": "2030-01-07T15:30:00Z",
    },
    "document_path": "/agent-kickoff.md",
    "document_content": "# Agent kickoff",
    "issue_title": "Review agent kickoff",
}


def call(name: str, arguments: dict[str, JsonValue]) -> ToolCall:
    return ToolCall(call_id="call-1", name=name, arguments=arguments)


def test_read_tool_uses_api_service_and_returns_bounded_event() -> None:
    api = ControlledApi()
    registry = ToolRegistry(api)

    execution = registry.execute(
        call("read_calendar_event", {"event_id": "event-1"}), timeout_seconds=3
    )

    assert api.event_ids == ["event-1"]
    assert api.timeouts == [3]
    assert execution.proposal is None
    assert execution.observation.outcome == "succeeded"
    assert execution.observation.result == {
        "event": Event(
            id="event-1",
            title="Project kickoff",
            start="2030-01-07T15:00:00Z",
            end="2030-01-07T15:30:00Z",
        ).model_dump(mode="json")
    }


@pytest.mark.parametrize(
    ("name", "arguments", "code"),
    [
        ("unknown_provider_tool", {}, "unknown_tool"),
        ("read_calendar_event", {"event_id": ""}, "invalid_tool_arguments"),
        (
            "read_calendar_event",
            {"event_id": "event-1", "user_id": "attacker-selected"},
            "invalid_tool_arguments",
        ),
        (
            "propose_project_kickoff",
            {**KICKOFF_ARGUMENTS, "user_id": "attacker-selected"},
            "invalid_tool_arguments",
        ),
    ],
)
def test_unknown_or_invalid_calls_are_rejected_before_api_use(
    name: str, arguments: dict[str, JsonValue], code: str
) -> None:
    api = ControlledApi()
    registry = ToolRegistry(api)

    with pytest.raises(ToolRejectedError, match=code):
        registry.execute(call(name, arguments))

    assert api.event_ids == []


def test_composed_write_tool_creates_exact_proposal_without_execution() -> None:
    api = ControlledApi()
    registry = ToolRegistry(api)

    first = registry.execute(call("propose_project_kickoff", KICKOFF_ARGUMENTS))
    second = registry.execute(call("propose_project_kickoff", KICKOFF_ARGUMENTS))
    changed = registry.execute(
        call(
            "propose_project_kickoff",
            {**KICKOFF_ARGUMENTS, "issue_title": "A changed issue"},
        )
    )

    assert first.proposal is not None and second.proposal is not None
    assert changed.proposal is not None
    assert first.proposal.digest == second.proposal.digest
    assert first.proposal.proposal_id != second.proposal.proposal_id
    assert changed.proposal.digest != first.proposal.digest
    assert first.proposal.target == "/workflows/project-kickoff"
    assert first.proposal.exact_changes == KICKOFF_ARGUMENTS
    assert first.observation.result["execution_status"] == (
        "not_executed_approval_required"
    )
    assert api.event_ids == []


def test_registry_documents_preconditions_effects_and_failures() -> None:
    definitions = ToolRegistry(ControlledApi()).definitions()

    assert [definition.name for definition in definitions] == [
        "propose_project_kickoff",
        "read_calendar_event",
    ]
    for definition in definitions:
        assert definition.arguments_schema
        assert definition.result_schema
        assert definition.preconditions
        assert definition.effects
        assert definition.failure_behavior
