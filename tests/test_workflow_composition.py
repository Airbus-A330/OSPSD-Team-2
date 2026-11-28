"""Exercise configuration/preflight, public failure states and resource lifetime."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from calendar_contract import Event
from cloud_storage_api import FileInfo, ProviderUnavailableError as StorageUnavailable
from fastapi.testclient import TestClient
from issue_tracker_contract.errors import ErrorCode as IssueErrorCode
from issue_tracker_contract.errors import ServiceError as IssueServiceError
from issue_tracker_contract.models import Issue

from app import composition, storage_composition, workflow_composition, workflows
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
    monkeypatch.delenv("ISSUE_TRACKER_IMPLEMENTATION", raising=False)
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
    order = ["storage", "issue_tracker", "calendar"]
    for later_step in order[order.index(step) + 1 :]:
        later_method = (
            services[later_step].create_issue
            if later_step == "issue_tracker"
            else services[later_step].create
        )
        later_method.assert_not_called()
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
    names = ["storage", "issue_tracker", "calendar"]
    for index, name in enumerate(names):
        expected = (
            "succeeded"
            if index < names.index(step)
            else "failed"
            if name == step
            else "not_attempted"
        )
        assert body["steps"][name]["outcome"] == expected
    if names.index(step) > 0:
        assert body["steps"]["storage"]["document"]["id"] == "controlled-document"
    if names.index(step) > 1:
        assert body["steps"]["issue_tracker"]["issue"]["id"] == "controlled-issue"
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


@pytest.mark.parametrize(
    "document_path",
    [
        "",
        "relative.md",
        "/",
        "/notes//a.md",
        "/notes/./a.md",
        "/notes/../a.md",
        "/notes/",
    ],
)
def test_nonportable_document_path_is_rejected_before_provider_setup(
    resources: tuple[dict[str, Mock], list[str]], document_path: str
) -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/workflows/project-kickoff",
            json={**BODY, "document_path": document_path},
        )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid_input",
        "message": "Invalid project kickoff data",
        "retryable": False,
    }
    assert resources[1] == []
    for service in resources[0].values():
        service.create.assert_not_called()
        service.create_issue.assert_not_called()


def test_mixed_case_document_path_is_preserved(
    resources: tuple[dict[str, Mock], list[str]],
) -> None:
    path = "/Projects/Alpha/Kickoff.md"
    with TestClient(create_app()) as client:
        response = client.post(
            "/workflows/project-kickoff", json={**BODY, "document_path": path}
        )

    assert response.status_code == 201
    resources[0]["storage"].create.assert_called_once_with(
        path, str(BODY["document_content"]).encode("utf-8")
    )


@pytest.mark.parametrize(
    ("content", "expected_status"),
    [("abcd", 201), ("abcde", 422), ("éé", 201), ("ééa", 422)],
)
def test_document_content_limit_uses_encoded_byte_length_before_setup(
    resources: tuple[dict[str, Mock], list[str]],
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    expected_status: int,
) -> None:
    monkeypatch.setattr(workflows, "MAX_DOCUMENT_CONTENT_BYTES", 4)
    with TestClient(create_app()) as client:
        response = client.post(
            "/workflows/project-kickoff",
            json={**BODY, "document_content": content},
        )

    assert response.status_code == expected_status
    if expected_status == 201:
        resources[0]["storage"].create.assert_called_once_with(
            BODY["document_path"], content.encode("utf-8")
        )
    else:
        assert resources[1] == []
        for service in resources[0].values():
            service.create.assert_not_called()
            service.create_issue.assert_not_called()


def test_document_content_limit_is_150_decimal_megabytes() -> None:
    assert workflows.MAX_DOCUMENT_CONTENT_BYTES == 150_000_000


def test_overlong_issue_title_is_rejected_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factories = [
        Mock(side_effect=AssertionError("Unexpected provider setup")) for _ in range(3)
    ]
    for name, factory in zip(
        ("open_issue_creator", "open_calendar_service", "get_document_storage"),
        factories,
    ):
        monkeypatch.setattr(workflow_composition, name, factory)
    with TestClient(create_app()) as client:
        response = client.post(
            "/workflows/project-kickoff", json={**BODY, "issue_title": "x" * 257}
        )
    assert response.status_code == 422
    for factory in factories:
        factory.assert_not_called()


def test_maximum_length_issue_title_reaches_provider(
    resources: tuple[dict[str, Mock], list[str]],
) -> None:
    title = "x" * 256
    with TestClient(create_app()) as client:
        response = client.post(
            "/workflows/project-kickoff", json={**BODY, "issue_title": title}
        )
    assert response.status_code == 201
    resources[0]["issue_tracker"].create_issue.assert_called_once_with(title)


@pytest.mark.parametrize(
    "missing", ["TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID"]
)
def test_whitespace_trello_configuration_fails_before_any_setup(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("ISSUE_TRACKER_IMPLEMENTATION", "team4-trello")
    for name in ("TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID"):
        monkeypatch.setenv(name, "valid")
    monkeypatch.setenv(missing, "   ")
    constructors = [
        Mock(side_effect=AssertionError("Unexpected provider setup")) for _ in range(3)
    ]
    for name, constructor in zip(
        ("TrelloIssueProvider", "open_calendar_service", "get_document_storage"),
        constructors,
    ):
        monkeypatch.setattr(workflow_composition, name, constructor)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 503
    assert response.json()["failed_step"] == "issue_tracker"
    assert all(
        step == {"outcome": "not_attempted"}
        for step in response.json()["steps"].values()
    )
    for constructor in constructors:
        constructor.assert_not_called()


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


@pytest.mark.parametrize("selection", ["", "unknown", "team4-trello"])
def test_issue_selection_fails_closed_without_usable_configuration(
    monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    monkeypatch.setenv("ISSUE_TRACKER_IMPLEMENTATION", selection)
    for name in ("TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == 503
    assert response.json()["failed_step"] == "issue_tracker"
    assert all(
        step == {"outcome": "not_attempted"}
        for step in response.json()["steps"].values()
    )


def test_issue_contract_adapter_returns_shared_issue() -> None:
    provider = Mock()
    provider.create_issue.return_value = Issue(id="issue-1", title="Title")
    result = workflow_composition.IssueTrackerCreator(provider).create_issue("Title")
    assert result == Issue(id="issue-1", title="Title")
    provider.create_issue.assert_called_once_with("Title")


def test_selected_team4_provider_is_constructed_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ISSUE_TRACKER_IMPLEMENTATION", "team4-trello")
    for name in ("TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID"):
        monkeypatch.setenv(name, "controlled")
    provider = Mock()
    provider.create_issue.return_value = Issue(id="issue-1", title="Title")
    monkeypatch.setattr(workflow_composition, "TrelloIssueProvider", lambda: provider)
    with workflow_composition.open_issue_creator() as creator:
        assert creator.create_issue("Title") == Issue(id="issue-1", title="Title")
    provider.create_issue.assert_called_once_with("Title")
    provider.close.assert_called_once_with()


def test_tagged_team4_provider_instantiates_through_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ISSUE_TRACKER_IMPLEMENTATION", "team4-trello")
    for name in ("TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID"):
        monkeypatch.setenv(name, "controlled")
    with workflow_composition.open_issue_creator() as creator:
        assert isinstance(creator, workflow_composition.IssueTrackerCreator)
        assert isinstance(creator.provider, workflow_composition.TrelloIssueProvider)


@pytest.mark.parametrize(
    "code,status",
    [
        (IssueErrorCode.ACCESS_DENIED, 403),
        (IssueErrorCode.SERVICE_NOT_CONFIGURED, 503),
        (IssueErrorCode.PROVIDER_ERROR, 502),
    ],
)
def test_issue_contract_errors_map_through_workflow(
    resources: tuple[dict[str, Mock], list[str]], code: IssueErrorCode, status: int
) -> None:
    provider = Mock()
    provider.create_issue.side_effect = IssueServiceError(code, "private")
    resources[0][
        "issue_tracker"
    ].create_issue.side_effect = workflow_composition.IssueTrackerCreator(
        provider
    ).create_issue
    with TestClient(create_app()) as client:
        response = client.post("/workflows/project-kickoff", json=BODY)
    assert response.status_code == status
    assert response.json()["failed_step"] == "issue_tracker"
    assert response.json()["error"]["retryable"] is False
    assert "private" not in response.text
    provider.create_issue.assert_called_once_with("Kickoff follow-up")


def test_openapi_keeps_original_request_success_and_documents_new_errors() -> None:
    operation = create_app().openapi()["paths"]["/workflows/project-kickoff"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectKickoffRequest"
    }
    responses = operation["responses"]
    assert responses["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectKickoffResult"
    }
    for status in (403, 404, 409, 502, 503):
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
