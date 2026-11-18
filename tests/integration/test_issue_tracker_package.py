"""Exercise the tagged Team 4 provider through the workflow with controlled HTTP."""

import io
import json
from contextlib import contextmanager
from email.message import Message
from typing import Iterator
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest
from calendar_contract import Event
from cloud_storage_api import FileInfo
from fastapi.testclient import TestClient
from team_4_issue_tracker_trello import provider as trello

from app import workflow_composition
from app.main import create_app

BODY = {
    "event": {
        "title": "Kickoff",
        "start": "2030-01-01T10:00:00Z",
        "end": "2030-01-01T11:00:00Z",
    },
    "document_path": "/kickoff.md",
    "document_content": "Notes",
    "issue_title": "Follow up",
}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOW_IMPLEMENTATION", "configured")
    monkeypatch.delenv("WORKFLOW_FAIL_STEP", raising=False)
    monkeypatch.setenv("ISSUE_TRACKER_IMPLEMENTATION", "team4-trello")
    monkeypatch.setenv("TRELLO_API_KEY", "test-key")
    monkeypatch.setenv("TRELLO_TOKEN", "test-token")
    monkeypatch.setenv("TRELLO_LIST_ID", "test-list")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    calendar = Mock()
    calendar.create.return_value = Event(
        id="event-1",
        title="Kickoff",
        start="2030-01-01T10:00:00Z",
        end="2030-01-01T11:00:00Z",
    )
    storage = Mock()
    storage.create.return_value = FileInfo(
        "file-1", "kickoff.md", "/kickoff.md", 5, None, None, None
    )

    @contextmanager
    def open_calendar() -> Iterator[Mock]:
        yield calendar

    def open_storage() -> Iterator[Mock]:
        yield storage

    monkeypatch.setattr(workflow_composition, "open_calendar_service", open_calendar)
    monkeypatch.setattr(workflow_composition, "get_document_storage", open_storage)


def test_team4_create_reaches_workflow_response(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[Request] = []

    def send(request: Request, *, timeout: float) -> io.BytesIO:
        requests.append(request)
        return io.BytesIO(json.dumps({"id": "a" * 24, "name": "Follow up"}).encode())

    monkeypatch.setattr(trello, "urlopen", send)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 201
    assert response.json()["issue_tracker"]["issue"] == {
        "id": "a" * 24,
        "title": "Follow up",
    }
    assert len(requests) == 1
    assert requests[0].get_method() == "POST"
    assert parse_qs(urlsplit(requests[0].full_url).query) == {
        "idList": ["test-list"],
        "name": ["Follow up"],
    }


@pytest.mark.parametrize(
    "provider_status,status,outcome", [(403, 403, "failed"), (500, 502, "uncertain")]
)
def test_team4_http_failure_preserves_workflow_progress(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    provider_status: int,
    status: int,
    outcome: str,
) -> None:
    send = Mock(
        side_effect=HTTPError(
            "https://example.invalid", provider_status, "private", Message(), None
        )
    )
    monkeypatch.setattr(trello, "urlopen", send)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == status
    result = response.json()
    assert result["failed_step"] == "issue_tracker"
    assert result["steps"]["calendar"]["outcome"] == "succeeded"
    assert result["steps"]["storage"]["outcome"] == "succeeded"
    assert result["steps"]["issue_tracker"] == {"outcome": outcome}
    assert result["error"]["retryable"] is False
    assert "private" not in response.text
    assert send.call_count == 1
