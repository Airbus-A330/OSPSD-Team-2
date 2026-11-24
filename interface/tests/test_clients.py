"""HTTP contract rendering, response uncertainty, and outbound boundaries."""

import asyncio
import ast
import json
from pathlib import Path

import httpx
import pytest
from calendar_contract import CreateEvent

from app.workflows import ProjectKickoffRequest
from interface.agent_client import HTTPAgentClient
from interface.clients import HTTPWorkflowClient, workflow_response
from interface.tests.support import FORM


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (400, "invalid_input", "correct"),
        (422, "invalid_input", "correct"),
        (403, "access_denied", "reconnect"),
        (404, "not_found", "destination"),
        (409, "conflict", "compare"),
        (502, "provider_error", "confirm"),
        (503, "provider_unavailable", "unavailable"),
    ],
)
def test_documented_error_codes_keep_message_and_actionable_guidance(
    status: int, code: str, expected: str
) -> None:
    view = workflow_response(
        httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "Documented useful message",
                    "retryable": False,
                }
            },
        )
    )
    assert view.code == code
    assert view.message == "Documented useful message"
    assert expected in view.guidance
    assert all(step.state == "not attempted" for step in view.steps)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, text="private raw exception"),
        httpx.Response(201, json={"unexpected": "payload"}),
        httpx.Response(200, json={}),
        httpx.Response(307, headers={"location": "https://provider.invalid"}),
    ],
)
def test_unrecognized_response_is_uncertain_without_raw_body(
    response: httpx.Response,
) -> None:
    view = workflow_response(response)
    assert view.state == "uncertain"
    assert "Do not submit again" in view.guidance
    assert "private raw exception" not in view.message
    assert all(step.state == "uncertain" for step in view.steps)


def test_http_client_calls_only_configured_api_once_and_keeps_token_off_payload() -> (
    None
):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["authorization"] == "Bearer test-api-access"
        assert b"test-api-access" not in request.content
        raise httpx.ReadTimeout("private transport data")

    client = HTTPWorkflowClient(
        "https://api.example.test",
        "test-api-access",
        transport=httpx.MockTransport(handler),
    )
    request = ProjectKickoffRequest(
        event=CreateEvent(**{key: FORM[key] for key in ("title", "start", "end")}),
        document_path=FORM["document_path"],
        document_content=FORM["document_content"],
        issue_title=FORM["issue_title"],
    )
    view = asyncio.run(client.kickoff(request))
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.example.test/workflows/project-kickoff"
    assert view.state == "uncertain"
    assert "private transport data" not in repr(view)
    assert "test-api-access" not in repr(view)


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "https://name:secret@api.example",
        "https://api.example?token=x",
        "file:///tmp/file",
        "https://api.example#fragment",
    ],
)
def test_service_url_requires_secure_remote_transport(url: str) -> None:
    with pytest.raises(ValueError):
        HTTPWorkflowClient(url)


def test_client_import_boundary_has_no_provider_database_or_workflow_execution() -> (
    None
):
    root = Path(__file__).parents[1]
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
                if node.module == "app.workflows":
                    assert all(
                        alias.name != "ProjectKickoffWorkflow" for alias in node.names
                    )
            else:
                continue
            assert not any(
                name.startswith(
                    (
                        "google",
                        "dropbox",
                        "team_4",
                        "sqlite3",
                        "sqlalchemy",
                        "app.composition",
                        "app.workflow_composition",
                        "app.google_calendar",
                    )
                )
                for name in imports
            )
    script = (root / "static" / "progress.js").read_text()
    assert "fetch(" not in script and "XMLHttpRequest" not in script


def agent_run_payload() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "conversation_id": "conversation-1",
        "status": "approval_required",
        "message": "Review the exact proposal.",
        "model_provider": "scripted",
        "model_version": "v1",
        "prompt_version": "agent-kickoff-v1",
        "proposal": {
            "proposal_id": "proposal-1",
            "digest": "a" * 64,
            "tool_name": "propose_project_kickoff",
            "method": "POST",
            "target": "/workflows/project-kickoff",
            "exact_changes": {
                "event": {
                    "title": FORM["title"],
                    "start": FORM["start"],
                    "end": FORM["end"],
                },
                "document_path": FORM["document_path"],
                "document_content": FORM["document_content"],
                "issue_title": FORM["issue_title"],
            },
            "effects": [
                "Create one storage document.",
                "Create one issue-tracker issue.",
                "Create one calendar event.",
            ],
        },
        "trace": [],
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "cost_usd": None,
        },
    }


def test_agent_client_uses_real_contract_and_maps_exact_proposal() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer interface-agent-token"
        assert b"interface-agent-token" not in request.content
        return httpx.Response(200, json=agent_run_payload())

    client = HTTPAgentClient(
        "https://agent.example.test",
        "interface-agent-token",
        transport=httpx.MockTransport(handler),
    )

    view = asyncio.run(client.submit("Prepare my kickoff"))

    assert len(requests) == 1
    assert str(requests[0].url) == "https://agent.example.test/agent/requests"
    assert json.loads(requests[0].content) == {"goal": "Prepare my kickoff"}
    assert view.state == "awaiting approval"
    assert view.available_decisions == ("reject",)
    assert view.proposal is not None
    assert view.proposal.proposal_id == "proposal-1"
    assert view.proposal.digest == "a" * 64
    assert [change.provider for change in view.proposal.changes] == [
        "Cloud Storage",
        "Issue Tracker",
        "Calendar",
    ]


def test_agent_client_refreshes_and_rejects_exact_proposal_by_cancelling() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"run_id": "run-1", "cancelled": True})
        return httpx.Response(
            200,
            json={
                "request": {"goal": "Prepare my kickoff", "conversation": []},
                "result": agent_run_payload(),
                "cancelled": False,
            },
        )

    client = HTTPAgentClient(
        "http://127.0.0.1:8001", transport=httpx.MockTransport(handler)
    )
    refreshed = asyncio.run(client.refresh("run-1"))
    assert refreshed.proposal is not None

    rejected = asyncio.run(client.decide("run-1", "proposal-1", "a" * 64, "reject", ""))

    assert rejected.state == "cancelled"
    assert calls == [
        ("GET", "/agent/runs/run-1"),
        ("POST", "/agent/runs/run-1/cancel"),
    ]


def test_agent_client_refuses_unimplemented_approval_without_http_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=agent_run_payload())

    client = HTTPAgentClient(
        "http://127.0.0.1:8001", transport=httpx.MockTransport(handler)
    )
    asyncio.run(client.submit("Prepare my kickoff"))

    with pytest.raises(ValueError, match="approval execution is not available"):
        asyncio.run(client.decide("run-1", "proposal-1", "a" * 64, "approve", ""))

    assert calls == 1
