"""HTTP contract rendering, response uncertainty, and outbound boundaries."""

import asyncio
import ast
from pathlib import Path

import httpx
import pytest
from calendar_contract import CreateEvent

from app.workflows import ProjectKickoffRequest
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
