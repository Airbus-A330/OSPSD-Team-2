"""Evaluation definitions retain exact model, prompt, tools, usage, and outcomes."""

from pathlib import Path

import pytest

from agent_service.contracts import ModelDecision
from agent_service.evaluation import (
    ADVERSARIAL_RETRIEVED_CONTENT,
    PROJECT_KICKOFF_PROPOSAL,
    evaluate,
)
from agent_service.model import ScriptedModel
from tests.agent.conftest import ControlledApi, build_service
from tests.agent.test_tools import KICKOFF_ARGUMENTS

EVALUATION_ARGUMENTS = {
    "event": {
        "title": "Agent Evaluation",
        "start": "2030-01-07T15:00:00Z",
        "end": "2030-01-07T15:30:00Z",
    },
    "document_path": "/agent-evaluation.md",
    "document_content": "# Agent Evaluation",
    "issue_title": "Review Agent Evaluation",
}


def test_evaluation_requires_five_real_model_attempts(tmp_path: Path) -> None:
    model = ScriptedModel([])
    service = build_service(tmp_path, model, ControlledApi())

    with pytest.raises(ValueError, match="at least five"):
        evaluate(
            PROJECT_KICKOFF_PROPOSAL,
            attempts=4,
            run=service.run,
            definitions=service.tool_definitions(),
        )


def test_repeated_evaluation_records_provenance_and_results(tmp_path: Path) -> None:
    decisions = [
        ModelDecision.model_validate(
            {
                "action": "tool_call",
                "message": "Propose kickoff",
                "tool_call": {
                    "call_id": f"call-{number}",
                    "name": "propose_project_kickoff",
                    "arguments": EVALUATION_ARGUMENTS,
                },
            }
        )
        for number in range(5)
    ]
    service = build_service(tmp_path, ScriptedModel(decisions), ControlledApi())

    records = evaluate(
        PROJECT_KICKOFF_PROPOSAL,
        attempts=5,
        run=service.run,
        definitions=service.tool_definitions(),
    )

    assert len(records) == 5
    assert all(record.success for record in records)
    assert {record.attempt for record in records} == {1, 2, 3, 4, 5}
    assert {record.prompt_version for record in records} == {"agent-kickoff-v1"}
    assert len({record.tool_definitions_digest for record in records}) == 1
    assert {record.model_version for record in records} == {"v1"}


def test_kickoff_evaluation_rejects_incorrect_proposal_fields(tmp_path: Path) -> None:
    decisions = [
        ModelDecision.model_validate(
            {
                "action": "tool_call",
                "message": "Propose a different kickoff",
                "tool_call": {
                    "call_id": f"call-{number}",
                    "name": "propose_project_kickoff",
                    "arguments": KICKOFF_ARGUMENTS,
                },
            }
        )
        for number in range(5)
    ]
    service = build_service(tmp_path, ScriptedModel(decisions), ControlledApi())

    records = evaluate(
        PROJECT_KICKOFF_PROPOSAL,
        attempts=5,
        run=service.run,
        definitions=service.tool_definitions(),
    )

    assert not any(record.success for record in records)
    assert {record.failure for record in records} == {"unexpected_proposal_changes"}


def test_adversarial_evaluation_requires_successful_controlled_event_read(
    tmp_path: Path,
) -> None:
    decisions = [
        ModelDecision(action="complete", message="Safe without reading")
        for _ in range(5)
    ]
    service = build_service(tmp_path, ScriptedModel(decisions), ControlledApi())

    records = evaluate(
        ADVERSARIAL_RETRIEVED_CONTENT,
        attempts=5,
        run=service.run,
        definitions=service.tool_definitions(),
    )

    assert not any(record.success for record in records)
    assert {record.failure for record in records} == {"controlled_event_was_not_read"}


def test_adversarial_evaluation_accepts_exact_successful_fixture_read(
    tmp_path: Path,
) -> None:
    decisions: list[ModelDecision] = []
    for number in range(5):
        decisions.extend(
            [
                ModelDecision.model_validate(
                    {
                        "action": "tool_call",
                        "message": "Read controlled event",
                        "tool_call": {
                            "call_id": f"read-{number}",
                            "name": "read_calendar_event",
                            "arguments": {"event_id": "controlled-injection"},
                        },
                    }
                ),
                ModelDecision(
                    action="complete", message="Ignored untrusted write instruction"
                ),
            ]
        )
    service = build_service(tmp_path, ScriptedModel(decisions), ControlledApi())

    records = evaluate(
        ADVERSARIAL_RETRIEVED_CONTENT,
        attempts=5,
        run=service.run,
        definitions=service.tool_definitions(),
    )

    assert all(record.success for record in records)
