"""Shared HTTP validation, substitution, and safe failure contracts."""

from unittest.mock import Mock

import pytest
from calendar_contract import (
    CalendarError,
    CalendarService,
    CreateEvent,
    ErrorCode,
    Event,
    ReplaceEvent,
)
from calendar_contract.conformance import CREATE
from fastapi.testclient import TestClient

from app.composition import get_calendar_service, get_event_provider
from app.main import create_app
from app.models import CreateEventRequest, EventReplacement


def test_write_names_are_aliases_of_shared_models() -> None:
    assert CreateEventRequest is CreateEvent
    assert EventReplacement is ReplaceEvent


@pytest.mark.parametrize(
    "method,operation,status",
    [("POST", "create", 201), ("PUT", "replace", 200), ("DELETE", "delete", 204)],
)
def test_common_routes_accept_only_the_shared_interface(
    method: str, operation: str, status: int
) -> None:
    service = Mock(spec=CalendarService)
    event = Event(id="opaque-id", **CREATE)
    getattr(service, operation).return_value = None if method == "DELETE" else event
    application = create_app()
    application.dependency_overrides[get_calendar_service] = lambda: service
    with TestClient(application) as client:
        response = client.request(
            method, "/events" if method == "POST" else "/events/opaque-id", json=CREATE
        )
    assert response.status_code == status
    if method == "POST":
        service.create.assert_called_once_with(CreateEvent(**CREATE))
    elif method == "PUT":
        service.replace.assert_called_once_with("opaque-id", ReplaceEvent(**CREATE))
    else:
        service.delete.assert_called_once_with("opaque-id")
    assert (
        response.content == b""
        if method == "DELETE"
        else response.json() == event.model_dump()
    )


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("title", None),
        ("title", 1),
        ("title", False),
        ("title", "\t\n"),
        ("start", 1730000000),
        ("end", 1730000010),
        ("start", "2030-01-07T15:00:00"),
        ("end", "2030-01-07T16:00:00+01:00"),
        ("unexpected", "private-content"),
    ],
)
def test_shared_invalid_fields_stop_before_provider_setup(
    method: str, field: str, value: object
) -> None:
    application = create_app()
    provider = Mock(side_effect=AssertionError("must not set up provider"))
    application.dependency_overrides[get_event_provider] = provider
    with TestClient(application) as client:
        response = client.request(
            method,
            "/events" if method == "POST" else "/events/id",
            json={**CREATE, field: value},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert response.json()["error"]["retryable"] is False
    assert "private-content" not in response.text
    provider.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/octet-stream", "application/json"]
)
def test_non_json_bodies_are_400_before_setup(method: str, content_type: str) -> None:
    application = create_app()
    provider = Mock(side_effect=AssertionError("must not set up provider"))
    application.dependency_overrides[get_event_provider] = provider
    with TestClient(application) as client:
        response = client.request(
            method,
            "/events" if method == "POST" else "/events/id",
            content=b"not-json",
            headers={"content-type": content_type},
        )
    assert response.status_code == 400
    assert response.json()["error"]["retryable"] is False
    provider.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize(
    "fields",
    [
        {**CREATE, "title": "  Meeting 会議  "},
        {**CREATE, "title": "M" * 100_000},
        {**CREATE, "start": "2030-01-07t15:00:00z", "end": "2030-01-07t15:30:00z"},
        {
            **CREATE,
            "start": "2030-01-07T15:00:00.0000001Z",
            "end": "2030-01-07T15:00:00.0000002Z",
        },
    ],
)
def test_shared_valid_values_reach_provider_unchanged(
    method: str, fields: dict[str, str]
) -> None:
    provider = Mock()
    provider.create_event.return_value = Event(id="id", **fields)
    provider.replace_event.return_value = Event(id="id", **fields)
    application = create_app()
    application.dependency_overrides[get_event_provider] = lambda: provider
    with TestClient(application) as client:
        response = client.request(
            method, "/events" if method == "POST" else "/events/id", json=fields
        )
    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json() == {"id": "id", **fields}
    if method == "POST":
        provider.create_event.assert_called_once_with(CreateEvent(**fields))
    else:
        provider.replace_event.assert_called_once_with("id", ReplaceEvent(**fields))


@pytest.mark.parametrize(
    "method,operation",
    [("POST", "create"), ("GET", "get"), ("PUT", "replace"), ("DELETE", "delete")],
)
@pytest.mark.parametrize(
    "code,status,retryable",
    [
        (ErrorCode.INVALID_INPUT, 422, False),
        (ErrorCode.NOT_FOUND, 404, False),
        (ErrorCode.ACCESS_DENIED, 403, False),
        (ErrorCode.PROVIDER_ERROR, 502, False),
        (ErrorCode.PROVIDER_UNAVAILABLE, 503, True),
    ],
)
def test_plain_shared_errors_are_sanitized_without_local_subclasses(
    method: str,
    operation: str,
    code: ErrorCode,
    status: int,
    retryable: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = Mock(spec=CalendarService)
    getattr(service, operation).side_effect = CalendarError(
        code=code,
        message="private-provider-secret",
        retryable=retryable,
        details={"private": "private-provider-secret"},
    )
    application = create_app()
    application.dependency_overrides[get_calendar_service] = lambda: service
    with TestClient(application) as client:
        response = client.request(
            method, "/events" if method == "POST" else "/events/id", json=CREATE
        )
    assert response.status_code == status
    error = response.json()["error"]
    assert set(error) == {"code", "message", "retryable"}
    assert error["code"] == code.value
    assert error["retryable"] is retryable
    assert "private-provider-secret" not in response.text + caplog.text
    assert getattr(service, operation).call_count == 1
