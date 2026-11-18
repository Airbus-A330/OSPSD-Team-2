"""Exercise configuration/preflight, public failure states and resource lifetime."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from calendar_contract import Event
from cloud_storage_api import FileInfo, ProviderUnavailableError as StorageUnavailable
from fastapi.testclient import TestClient

from app import composition, storage_composition, workflow_composition
from app.errors import ProviderUnavailableError
from app.main import create_app
from app.workflows import IssueResult

BODY = {
    "event": {
        "title": "Kickoff",
        "start": "2030-01-01T10:00:00Z",
        "end": "2030-01-01T11:00:00Z",
    },
    "document_path": "/kickoff.md",
    "document_content": "Exact UTF-8 notes: café",
    "issue_title": "Kickoff follow-up",
}


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKFLOW_IMPLEMENTATION", raising=False)
    monkeypatch.delenv("WORKFLOW_FAIL_STEP", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


@pytest.fixture
def resources(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Mock], list[str]]:
    services = {name: Mock() for name in ("calendar", "storage", "issue_tracker")}
    services["calendar"].create.return_value = Event(
        id="event-1",
        title="Kickoff",
        start="2030-01-01T10:00:00Z",
        end="2030-01-01T11:00:00Z",
    )
    services["storage"].create.return_value = FileInfo(
        "file-1", "kickoff.md", "/kickoff.md", 23, None, None, None
    )
    services["issue_tracker"].create_issue.return_value = IssueResult(
        id="issue-1", title="Kickoff follow-up"
    )
    lifetime: list[str] = []

    @contextmanager
    def opened(name: str) -> Iterator[Mock]:
        lifetime.append("open:" + name)
        try:
            yield services[name]
        finally:
            services[name].close()
            lifetime.append("close:" + name)

    def storage() -> Iterator[Mock]:
        with opened("storage") as service:
            yield service

    monkeypatch.setattr(
        workflow_composition, "open_issue_creator", lambda: opened("issue_tracker")
    )
    monkeypatch.setattr(
        workflow_composition, "open_calendar_service", lambda: opened("calendar")
    )
    monkeypatch.setattr(workflow_composition, "get_document_storage", storage)
    return services, lifetime


def test_configured_factories_supply_same_http_workflow_and_close_all_clients(
    resources: tuple[dict[str, Mock], list[str]],
) -> None:
    services, lifetime = resources
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 201
    assert response.json()["storage"]["document"] == {
        "id": "file-1",
        "path": "/kickoff.md",
    }
    assert response.json()["issue_tracker"]["issue"]["id"] == "issue-1"
    services["storage"].create.assert_called_once_with(
        "/kickoff.md", "Exact UTF-8 notes: café".encode()
    )
    assert lifetime == [
        "open:issue_tracker",
        "open:calendar",
        "open:storage",
        "close:storage",
        "close:calendar",
        "close:issue_tracker",
    ]
    for service in services.values():
        service.close.assert_called_once_with()


@pytest.mark.parametrize("step", ["calendar", "storage", "issue_tracker"])
def test_operation_failure_closes_all_clients_and_does_not_retry(
    resources: tuple[dict[str, Mock], list[str]],
    step: str,
) -> None:
    services, lifetime = resources
    method = (
        services[step].create_issue
        if step == "issue_tracker"
        else services[step].create
    )
    method.side_effect = (
        StorageUnavailable("private")
        if step == "storage"
        else ProviderUnavailableError("private")
    )
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == (502 if step == "storage" else 503)
    assert response.json()["failed_step"] == step
    assert response.json()["failure_stage"] == "operation"
    assert response.json()["error"]["retryable"] is False
    assert response.json()["steps"][step] == {"outcome": "uncertain"}
    assert method.call_count == 1
    assert lifetime[-3:] == ["close:storage", "close:calendar", "close:issue_tracker"]
    assert "private" not in response.text


@pytest.mark.parametrize(
    "step,factory",
    [
        ("issue_tracker", "open_issue_creator"),
        ("calendar", "open_calendar_service"),
        ("storage", "get_document_storage"),
    ],
)
@pytest.mark.parametrize("unexpected", [False, True])
def test_setup_failure_leaves_all_writes_unattempted_and_unwinds_resources(
    resources: tuple[dict[str, Mock], list[str]],
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    factory: str,
    unexpected: bool,
) -> None:
    services, lifetime = resources
    error = (
        RuntimeError("private") if unexpected else ProviderUnavailableError("private")
    )
    monkeypatch.setattr(workflow_composition, factory, Mock(side_effect=error))
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    body = response.json()
    assert response.status_code == (502 if unexpected else 503)
    assert body["failed_step"] == step and body["failure_stage"] == "setup"
    assert body["steps"] == {name: {"outcome": "not_attempted"} for name in services}
    assert body["error"]["retryable"] is (not unexpected)
    for service in services.values():
        service.create.assert_not_called()
        service.create_issue.assert_not_called()
    opened = [entry[5:] for entry in lifetime if entry.startswith("open:")]
    closed = [entry[6:] for entry in lifetime if entry.startswith("close:")]
    assert closed == list(reversed(opened))
    assert "private" not in response.text


@pytest.mark.parametrize("step", ["calendar", "storage", "issue_tracker"])
def test_explicit_controlled_mode_forces_selected_step_without_provider_setup(
    monkeypatch: pytest.MonkeyPatch,
    step: str,
) -> None:
    monkeypatch.setenv("WORKFLOW_IMPLEMENTATION", "controlled")
    monkeypatch.setenv("WORKFLOW_FAIL_STEP", step)
    constructors = []
    for name in ("open_issue_creator", "open_calendar_service", "get_document_storage"):
        constructor = Mock(side_effect=AssertionError("Must not construct providers"))
        constructors.append(constructor)
        monkeypatch.setattr(workflow_composition, name, constructor)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 403
    body = response.json()
    assert body["failed_step"] == step and body["failure_stage"] == "operation"
    names = ["calendar", "storage", "issue_tracker"]
    for index, name in enumerate(names):
        expected = (
            "succeeded"
            if index < names.index(step)
            else "failed"
            if name == step
            else "not_attempted"
        )
        assert body["steps"][name]["outcome"] == expected
    if step != "calendar":
        assert body["steps"]["calendar"]["event"]["id"] == "controlled-event"
    for constructor in constructors:
        constructor.assert_not_called()


@pytest.mark.parametrize(
    "mode,step",
    [
        ("", None),
        ("unknown", None),
        ("configured", "storage"),
        ("controlled", None),
        ("controlled", ""),
        ("controlled", "STORAGE"),
        ("controlled", "storage "),
    ],
)
def test_bad_mode_or_fault_configuration_fails_closed_before_any_setup(
    resources: tuple[dict[str, Mock], list[str]],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    step: str | None,
) -> None:
    monkeypatch.setenv("WORKFLOW_IMPLEMENTATION", mode)
    if step is not None:
        monkeypatch.setenv("WORKFLOW_FAIL_STEP", step)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 502
    assert response.json()["failed_step"] == "configuration"
    assert response.json()["failure_stage"] == "setup"
    assert response.json()["error"]["retryable"] is False
    assert resources[1] == []


@pytest.mark.parametrize("step", ["calendar", "storage"])
def test_existing_vertical_selectors_fail_before_provider_auth(
    resources: tuple[dict[str, Mock], list[str]],
    monkeypatch: pytest.MonkeyPatch,
    step: str,
) -> None:
    auth = Mock(side_effect=AssertionError("Must reject before auth"))
    if step == "calendar":
        monkeypatch.setenv("CALENDAR_IMPLEMENTATION", "unsupported")
        monkeypatch.setattr(composition, "build_google_calendar_client", auth)
        monkeypatch.setattr(
            workflow_composition,
            "open_calendar_service",
            composition.open_calendar_service,
        )
    else:
        monkeypatch.setenv("STORAGE_IMPLEMENTATION", "unsupported")
        monkeypatch.setattr(storage_composition, "get_dropbox_client", auth)
        monkeypatch.setattr(
            workflow_composition,
            "get_document_storage",
            storage_composition.get_document_storage,
        )
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 502
    assert response.json()["failed_step"] == step
    assert response.json()["failure_stage"] == "setup"
    auth.assert_not_called()
    for service in resources[0].values():
        service.create.assert_not_called()
        service.create_issue.assert_not_called()


@pytest.mark.parametrize(
    "payload,status",
    [(None, 422), ({}, 422), ({**BODY, "extra": True}, 422), ("{", 400)],
)
def test_request_validation_precedes_resource_setup(
    resources: tuple[dict[str, Mock], list[str]],
    payload: object,
    status: int,
) -> None:
    with TestClient(create_app()) as client:
        response = (
            client.post(
                "/workflows/project-kickoff",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
            if isinstance(payload, str)
            else client.post("/workflows/project-kickoff", json=payload)
        )
    assert response.status_code == status
    assert response.json()["error"] == {
        "code": "invalid_input",
        "message": "Invalid project kickoff data",
        "retryable": False,
    }
    assert resources[1] == []


def test_missing_issue_integration_is_explicit_and_never_falls_back_to_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calendar = Mock(side_effect=AssertionError("Must fail before Calendar setup"))
    storage = Mock(side_effect=AssertionError("Must fail before storage setup"))
    monkeypatch.setattr(workflow_composition, "open_calendar_service", calendar)
    monkeypatch.setattr(workflow_composition, "get_document_storage", storage)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 503
    body = response.json()
    assert body["failed_step"] == "issue_tracker" and body["failure_stage"] == "setup"
    assert all(step == {"outcome": "not_attempted"} for step in body["steps"].values())
    calendar.assert_not_called()
    storage.assert_not_called()


def test_openapi_keeps_original_request_success_and_documents_new_errors() -> None:
    operation = create_app().openapi()["paths"]["/workflows/project-kickoff"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectKickoffRequest"
    }
    responses = operation["responses"]
    assert responses["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectKickoffResult"
    }
    for status in (403, 404, 502, 503):
        assert responses[str(status)]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ProjectKickoffFailureResult"
        }
    assert "400" in responses and "422" in responses


def test_changing_only_controlled_configuration_changes_failed_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFLOW_IMPLEMENTATION", "controlled")
    with TestClient(create_app()) as client:
        for step in ("calendar", "storage", "issue_tracker"):
            monkeypatch.setenv("WORKFLOW_FAIL_STEP", step)
            response = client.post("/workflows/project-kickoff", json=BODY)
            assert response.status_code == 403
            assert response.json()["failed_step"] == step
