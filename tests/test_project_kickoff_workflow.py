"""Fixed three-vertical project-kickoff workflow tests."""

from dataclasses import dataclass
from unittest.mock import Mock, patch

import pytest
from calendar_contract import CalendarError, CreateEvent, ErrorCode, Event
from fastapi.testclient import TestClient

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ProviderUnavailableError,
    StorageConflictError,
)
from app.main import create_app
from app.workflow_composition import get_project_kickoff_workflow
from app.workflows import ProjectKickoffRequest, ProjectKickoffWorkflow, WorkflowFailure


EVENT_INPUT = {
    "title": "Project kickoff",
    "start": "2026-11-16T10:00:00-05:00",
    "end": "2026-11-16T11:00:00-05:00",
}


@dataclass
class ControlledFile:
    """Stored-file result returned by the controlled storage boundary."""

    id: str | None
    path: str


@dataclass
class ControlledIssue:
    """Issue result returned by the controlled issue boundary."""

    id: str
    title: str


class ControlledCalendar:
    """Record Calendar create calls without external credentials."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.requests: list[CreateEvent] = []

    def create(self, request: CreateEvent) -> Event:
        self.calls.append("calendar")
        self.requests.append(request)
        return Event(id="event-123", **request.model_dump())


class ControlledStorage:
    """Record document creation without a storage provider."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.requests: list[tuple[str, bytes]] = []

    def create(self, path: str, content: bytes) -> ControlledFile:
        self.calls.append("storage")
        self.requests.append((path, content))
        return ControlledFile(id="file-456", path=path)


class ControlledIssues:
    """Record issue creation without an issue provider."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.titles: list[str] = []

    def create_issue(self, title: str) -> ControlledIssue:
        self.calls.append("issue_tracker")
        self.titles.append(title)
        return ControlledIssue(id="issue-789", title=title)


def configured_workflow() -> tuple[
    ProjectKickoffWorkflow,
    list[str],
    ControlledCalendar,
    ControlledStorage,
    ControlledIssues,
]:
    """Build one workflow with observable controlled boundaries."""
    calls: list[str] = []
    calendar = ControlledCalendar(calls)
    storage = ControlledStorage(calls)
    issues = ControlledIssues(calls)
    return (
        ProjectKickoffWorkflow(calendar, storage, issues),
        calls,
        calendar,
        storage,
        issues,
    )


def test_project_kickoff_runs_three_steps_once_in_fixed_order() -> None:
    workflow, calls, calendar, storage, issues = configured_workflow()
    request = ProjectKickoffRequest(
        event=CreateEvent(**EVENT_INPUT),
        document_path="/projects/alpha/kickoff.txt",
        document_content="Agenda and decisions",
        issue_title="Track kickoff follow-up",
    )

    result = workflow.run(request)

    assert calls == ["storage", "issue_tracker", "calendar"]
    assert calendar.requests == [CreateEvent(**EVENT_INPUT)]
    assert storage.requests == [
        ("/projects/alpha/kickoff.txt", b"Agenda and decisions")
    ]
    assert issues.titles == ["Track kickoff follow-up"]
    assert result.model_dump() == {
        "calendar": {
            "outcome": "succeeded",
            "event": {"id": "event-123", **EVENT_INPUT},
        },
        "storage": {
            "outcome": "succeeded",
            "document": {
                "id": "file-456",
                "path": "/projects/alpha/kickoff.txt",
            },
        },
        "issue_tracker": {
            "outcome": "succeeded",
            "issue": {
                "id": "issue-789",
                "title": "Track kickoff follow-up",
            },
        },
    }


def test_storage_failure_prevents_downstream_writes_and_identifies_step() -> None:
    workflow, calls, calendar, storage, issues = configured_workflow()
    application = create_app()
    application.dependency_overrides[get_project_kickoff_workflow] = lambda: workflow
    with (
        patch.object(
            storage, "create", side_effect=ProviderFailureError("private detail")
        ),
        TestClient(application) as client,
    ):
        response = client.post(
            "/workflows/project-kickoff",
            json={
                "event": EVENT_INPUT,
                "document_path": "/projects/alpha/kickoff.txt",
                "document_content": "Agenda and decisions",
                "issue_title": "Track kickoff follow-up",
            },
        )
    assert response.status_code == 502
    body = response.json()
    assert body["failed_step"] == "storage"
    assert body["steps"]["calendar"] == {"outcome": "not_attempted"}
    assert body["steps"]["storage"] == {"outcome": "uncertain"}
    assert body["steps"]["issue_tracker"] == {"outcome": "not_attempted"}
    assert calls == []
    assert calendar.requests == []
    assert issues.titles == []
    assert "private detail" not in response.text


def test_project_kickoff_http_operation_returns_combined_result() -> None:
    workflow, calls, _, _, _ = configured_workflow()
    application = create_app()
    application.dependency_overrides[get_project_kickoff_workflow] = lambda: workflow

    with TestClient(application) as client:
        response = client.post(
            "/workflows/project-kickoff",
            json={
                "event": EVENT_INPUT,
                "document_path": "/projects/alpha/kickoff.txt",
                "document_content": "Agenda and decisions",
                "issue_title": "Track kickoff follow-up",
            },
        )

    assert response.status_code == 201
    assert calls == ["storage", "issue_tracker", "calendar"]
    assert response.json()["calendar"]["event"]["id"] == "event-123"
    assert response.json()["storage"]["document"]["id"] == "file-456"
    assert response.json()["issue_tracker"]["issue"]["id"] == "issue-789"


@pytest.fixture
def kickoff_body() -> dict[str, object]:
    return {
        "event": EVENT_INPUT,
        "document_path": "/projects/alpha/kickoff.txt",
        "document_content": "Agenda and decisions",
        "issue_title": "Track kickoff follow-up",
    }


@pytest.mark.parametrize("step_index", [0, 1, 2])
@pytest.mark.parametrize(
    "error,status,code,outcome",
    [
        (InvalidInputError("private"), 422, "invalid_input", "failed"),
        (NotFoundError("private"), 404, "not_found", "failed"),
        (PermissionDeniedError("private"), 403, "access_denied", "failed"),
        (ProviderFailureError("private"), 502, "provider_error", "uncertain"),
        (ProviderUnavailableError("private"), 503, "provider_unavailable", "uncertain"),
        (
            CalendarError(
                ErrorCode.PROVIDER_ERROR, "private", False, {"secret": "private"}
            ),
            502,
            "provider_error",
            "uncertain",
        ),
        (RuntimeError("private"), 502, "provider_error", "uncertain"),
    ],
)
def test_each_step_failure_preserves_progress_and_sanitizes_errors(
    step_index: int,
    error: Exception,
    status: int,
    code: str,
    outcome: str,
    kickoff_body: dict[str, object],
) -> None:
    workflow, calls, calendar, storage, issues = configured_workflow()
    names = ["storage", "issue_tracker", "calendar"]
    target = (storage, issues, calendar)[step_index]
    method = "create_issue" if names[step_index] == "issue_tracker" else "create"
    application = create_app()
    application.dependency_overrides[get_project_kickoff_workflow] = lambda: workflow
    with (
        patch.object(target, method, side_effect=error) as failed_call,
        TestClient(application) as client,
    ):
        response = client.post("/workflows/project-kickoff", json=kickoff_body)
    assert response.status_code == status
    body = response.json()
    assert body["error"] == {
        "code": code,
        "message": f"Workflow {names[step_index]} operation failed",
        "retryable": False,
    }
    assert body["failed_step"] == names[step_index]
    assert body["failure_stage"] == "operation"
    for index, name in enumerate(names):
        assert body["steps"][name]["outcome"] == (
            "succeeded"
            if index < step_index
            else outcome
            if index == step_index
            else "not_attempted"
        )
    if step_index > 0:
        assert body["steps"]["storage"]["document"] == {
            "id": "file-456",
            "path": kickoff_body["document_path"],
        }
    if step_index > 1:
        assert body["steps"]["issue_tracker"]["issue"] == {
            "id": "issue-789",
            "title": kickoff_body["issue_title"],
        }
    assert calls == names[:step_index]
    assert failed_call.call_count == 1
    assert "private" not in response.text


def test_successful_storage_claim_blocks_downstream_writes_on_resubmission(
    kickoff_body: dict[str, object],
) -> None:
    workflow, calls, calendar, storage, issues = configured_workflow()
    saved: dict[str, bytes] = {}

    def claim_path(path: str, content: bytes) -> ControlledFile:
        calls.append("storage")
        if path in saved:
            raise StorageConflictError()
        saved[path] = content
        return ControlledFile(id="file-456", path=path)

    def fail_issue(*args: object) -> None:
        calls.append("issue_tracker")
        raise ProviderUnavailableError("private provider detail")

    application = create_app()
    application.dependency_overrides[get_project_kickoff_workflow] = lambda: workflow
    with (
        patch.object(storage, "create", side_effect=claim_path),
        patch.object(issues, "create_issue", side_effect=fail_issue) as issue_call,
        TestClient(application) as client,
    ):
        first = client.post("/workflows/project-kickoff", json=kickoff_body)
        second = client.post("/workflows/project-kickoff", json=kickoff_body)

    assert first.status_code == 503
    assert first.json()["steps"]["storage"]["outcome"] == "succeeded"
    assert first.json()["steps"]["issue_tracker"]["outcome"] == "uncertain"
    assert first.json()["steps"]["calendar"] == {"outcome": "not_attempted"}
    assert second.status_code == 409
    assert second.json()["error"] == {
        "code": "conflict",
        "message": (
            "Storage path already exists; inspect its metadata and content "
            "before retrying"
        ),
        "retryable": False,
    }
    assert second.json()["steps"]["storage"]["outcome"] == "failed"
    assert second.json()["steps"]["issue_tracker"] == {"outcome": "not_attempted"}
    assert second.json()["steps"]["calendar"] == {"outcome": "not_attempted"}
    assert first.json()["error"]["retryable"] is False
    assert second.json()["error"]["retryable"] is False
    assert calendar.requests == []
    assert issue_call.call_count == 1
    assert calls == ["storage", "issue_tracker", "storage"]
    assert saved == {"/projects/alpha/kickoff.txt": b"Agenda and decisions"}
    assert issues.titles == []


@pytest.mark.parametrize("step_index", [0, 1, 2])
def test_committed_write_with_lost_response_is_uncertain_not_known_failed(
    step_index: int,
    kickoff_body: dict[str, object],
) -> None:
    workflow, _, calendar, storage, issues = configured_workflow()
    committed: list[str] = []
    target = (storage, issues, calendar)[step_index]

    def lose_response(*args: object) -> None:
        committed.append("write happened")
        raise RuntimeError("private lost-response detail")

    with patch.object(
        target,
        "create_issue" if step_index == 1 else "create",
        side_effect=lose_response,
    ):
        with pytest.raises(WorkflowFailure) as caught:
            workflow.run(ProjectKickoffRequest.model_validate(kickoff_body))
    result = caught.value.result().model_dump(mode="json")
    step = ["storage", "issue_tracker", "calendar"][step_index]
    assert result["steps"][step] == {"outcome": "uncertain"}
    assert result["error"]["retryable"] is False
    assert committed == ["write happened"]


def test_malformed_return_after_storage_write_prevents_downstream_calls(
    kickoff_body: dict[str, object],
) -> None:
    workflow, _, _, storage, issues = configured_workflow()
    with patch.object(storage, "create", return_value=Mock(id=42, path="/notes.md")):
        with pytest.raises(WorkflowFailure) as caught:
            workflow.run(ProjectKickoffRequest.model_validate(kickoff_body))
    assert caught.value.failed_step == "storage"
    assert caught.value.steps.calendar.outcome == "not_attempted"
    assert caught.value.steps.storage.outcome == "uncertain"
    assert issues.titles == []


def test_previous_success_does_not_leak_into_a_later_failed_execution(
    kickoff_body: dict[str, object],
) -> None:
    workflow, _, calendar, _, _ = configured_workflow()
    request = ProjectKickoffRequest.model_validate(kickoff_body)
    first = workflow.run(request)
    with patch.object(calendar, "create", side_effect=PermissionDeniedError("denied")):
        with pytest.raises(WorkflowFailure) as caught:
            workflow.run(request)
    assert caught.value.result().steps.model_dump() == {
        "calendar": {"outcome": "failed"},
        "storage": {
            "outcome": "succeeded",
            "document": {
                "id": "file-456",
                "path": "/projects/alpha/kickoff.txt",
            },
        },
        "issue_tracker": {
            "outcome": "succeeded",
            "issue": {
                "id": "issue-789",
                "title": "Track kickoff follow-up",
            },
        },
    }
    assert first.calendar.event.id == "event-123"


def test_storage_without_provider_identifier_remains_a_valid_success(
    kickoff_body: dict[str, object],
) -> None:
    workflow, _, _, storage, _ = configured_workflow()
    with patch.object(
        storage, "create", return_value=ControlledFile(None, "/notes.md")
    ):
        result = workflow.run(ProjectKickoffRequest.model_validate(kickoff_body))
    assert result.storage.document.model_dump() == {"id": None, "path": "/notes.md"}
