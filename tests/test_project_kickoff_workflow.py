"""Fixed three-vertical project-kickoff workflow tests."""

from dataclasses import dataclass

from calendar_contract import CreateEvent, Event
from fastapi.testclient import TestClient

from app.main import create_app
from app.workflow_composition import get_project_kickoff_workflow
from app.workflows import ProjectKickoffRequest, ProjectKickoffWorkflow


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

    assert calls == ["calendar", "storage", "issue_tracker"]
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
    assert calls == ["calendar", "storage", "issue_tracker"]
    assert response.json()["calendar"]["event"]["id"] == "event-123"
    assert response.json()["storage"]["document"]["id"] == "file-456"
    assert response.json()["issue_tracker"]["issue"]["id"] == "issue-789"
