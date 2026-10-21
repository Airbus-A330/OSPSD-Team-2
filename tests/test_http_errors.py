"""HTTP failure contracts and safe logging with controlled providers."""

import logging
import socket
from dataclasses import dataclass, field
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.event_cache import EventCache
from app.main import app, get_event_provider
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider


@dataclass
class ControlledProvider:
    """Return a configured outcome and record identifiers without external I/O."""

    outcome: Event | Exception
    calls: list[str] = field(default_factory=list)

    def delete_event(self, event_id: str) -> None:
        pytest.fail("Retrieval tests must not delete an event")

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        raise NotImplementedError

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        pytest.fail("Retrieval tests must not write provider state")

    def get_event(self, event_id: str) -> Event:
        self.calls.append(event_id)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def list_events(self, limit: int) -> list[Event]:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return [self.outcome][:limit]

    def create_event(self, event: CreateEventRequest) -> Event:
        """Creation is outside this retrieval-focused controlled provider."""
        raise NotImplementedError


def override_provider(provider: EventProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the production dependency override and restore it after the test."""
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)


def assert_failure_log(
    caplog: pytest.LogCaptureFixture, code: str, status: int, involved: bool
) -> None:
    records = [record for record in caplog.records if record.name == "app.http_errors"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.__dict__["operation"] == "get_event"
    assert record.__dict__["error_code"] == code
    assert record.__dict__["http_status"] == status
    assert record.__dict__["provider_involved"] is involved
    assert record.exc_info is None
    assert record.stack_info is None


@pytest.mark.parametrize(
    ("error_type", "status", "code", "message"),
    [
        (InvalidInputError, 400, "invalid_input", "Invalid event ID"),
        (NotFoundError, 404, "not_found", "Event not found"),
        (PermissionDeniedError, 403, "permission_denied", "Permission denied"),
        (
            ProviderFailureError,
            502,
            "provider_error",
            "Calendar provider request failed",
        ),
    ],
)
def test_http_service_failure_contract_and_safe_log(
    error_type: type[ServiceError],
    status: int,
    code: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "synthetic-token-and-private-provider-payload"
    event_id = "synthetic-private-event-id"
    provider = ControlledProvider(error_type(secret))
    override_provider(provider, monkeypatch)

    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get(
            f"/events/{event_id}", headers={"Authorization": f"Bearer {secret}"}
        )

    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"error": {"code": code, "message": message}}
    assert provider.calls == [event_id]
    assert_failure_log(caplog, code, status, True)
    assert secret not in response.text
    assert secret not in caplog.text
    assert event_id not in caplog.text
    assert all(secret not in repr(record.__dict__) for record in caplog.records)


@pytest.mark.parametrize("event_id", ["   ", "\t\n", "\u2003"])
def test_blank_http_input_fails_before_google_client_construction(
    event_id: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def unexpected_client() -> None:
        pytest.fail("Blank input must not construct a Google client or start OAuth")

    monkeypatch.setattr("app.main.build_google_calendar_client", unexpected_client)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get(f"/events/{quote(event_id, safe='')}")

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": "Invalid event ID"}
    }
    assert_failure_log(caplog, "invalid_input", 400, False)


@pytest.mark.parametrize("event_id", [" valid-id ", "会議"])
def test_http_success_preserves_identifier_and_has_no_failure_log(
    event_id: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    event = Event(
        id=event_id,
        title="Controlled event",
        start="2026-10-18T09:00:00-04:00",
        end="2026-10-18T10:00:00-04:00",
    )
    provider = ControlledProvider(event)
    override_provider(provider, monkeypatch)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get(f"/events/{quote(event_id, safe='')}")

    assert response.status_code == 200
    assert response.json() == event.model_dump()
    assert provider.calls == [event_id]
    assert not [record for record in caplog.records if record.name == "app.http_errors"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFoundError(), 404),
        (PermissionDeniedError(), 403),
        (ProviderFailureError(), 502),
    ],
)
def test_request_scoped_client_closes_on_handled_failure(
    error: ServiceError, status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    google_client = MagicMock()
    provider = ControlledProvider(error)
    monkeypatch.setattr("app.main.build_google_calendar_client", lambda: google_client)
    monkeypatch.setattr(
        "app.main.GoogleCalendarProvider", lambda client, *, calendar_id: provider
    )
    with TestClient(app) as client:
        response = client.get("/events/test-event")

    assert response.status_code == status
    assert provider.calls == ["test-event"]
    google_client.close.assert_called_once_with()


def test_service_failure_during_provider_setup_is_rendered_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail_setup() -> None:
        raise ProviderFailureError("synthetic-private-setup-details")

    monkeypatch.setattr("app.main.build_google_calendar_client", fail_setup)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get("/events/test-event")

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_error",
            "message": "Calendar provider request failed",
        }
    }
    assert_failure_log(caplog, "provider_error", 502, True)
    assert "synthetic-private-setup-details" not in caplog.text


@pytest.mark.parametrize(
    "transport_error",
    [
        socket.timeout("synthetic-private-network-detail"),
        ConnectionResetError("synthetic-private-network-detail"),
    ],
)
def test_socket_failure_is_sanitized_as_provider_error(
    transport_error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    google_client = MagicMock()
    google_client.events.return_value.get.return_value.execute.side_effect = (
        transport_error
    )
    monkeypatch.setattr("app.main.build_google_calendar_client", lambda: google_client)
    monkeypatch.setattr("app.main.event_cache", EventCache())

    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get("/events/network-failure")

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_error",
            "message": "Calendar provider request failed",
        }
    }
    assert_failure_log(caplog, "provider_error", 502, True)
    assert "synthetic-private-network-detail" not in response.text
    assert "synthetic-private-network-detail" not in caplog.text
    google_client.close.assert_called_once_with()


@pytest.mark.parametrize(
    "error", [RuntimeError("unexpected bug"), ServiceError("unknown category")]
)
def test_unexpected_errors_are_not_disguised_as_expected_failures(
    error: Exception, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    override_provider(ControlledProvider(error), monkeypatch)
    with TestClient(app) as client, pytest.raises(type(error)) as caught:
        client.get("/events/test-event")

    assert caught.value is error
    assert not [record for record in caplog.records if record.name == "app.http_errors"]


@pytest.mark.parametrize(
    ("method", "path", "operation", "message"),
    [
        ("POST", "/events", "create_event", "Invalid event data"),
        ("PUT", "/events/private-id", "replace_event", "Invalid event replacement"),
        ("PATCH", "/events/private-id", "patch_event", "Invalid input"),
    ],
)
@pytest.mark.parametrize("body", [b'{"title":"private-body-\xff"}', b'{"title":'])
def test_malformed_json_has_shared_error_and_safe_log_before_provider_setup(
    method: str,
    path: str,
    operation: str,
    message: str,
    body: bytes,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def unexpected_client() -> None:
        pytest.fail("Invalid JSON must not construct a provider or start OAuth")

    monkeypatch.setattr("app.main.build_google_calendar_client", unexpected_client)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.request(
            method, path, content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "invalid_input", "message": message}}
    records = [record for record in caplog.records if record.name == "app.http_errors"]
    assert len(records) == 1
    record = records[0]
    assert record.__dict__["operation"] == operation
    assert record.__dict__["error_code"] == "invalid_input"
    assert record.__dict__["http_status"] == 400
    assert record.__dict__["provider_involved"] is False
    assert record.exc_info is None and record.stack_info is None
    assert "private-body" not in caplog.text + response.text
    assert "private-id" not in caplog.text + response.text


@pytest.mark.parametrize(
    ("method", "path", "status", "detail"),
    [
        ("GET", "/unknown-route", 404, "Not Found"),
        ("DELETE", "/events", 405, "Method Not Allowed"),
    ],
)
def test_framework_routing_errors_keep_their_existing_response(
    method: str,
    path: str,
    status: int,
    detail: str,
) -> None:
    with TestClient(app) as client:
        response = client.request(method, path)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    if status == 405:
        assert "allow" in response.headers


@pytest.mark.parametrize("status", [400, 403])
def test_other_http_errors_preserve_details_and_headers(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = HTTPException(
        status, "Unrelated framework error", headers={"X-Test": "preserved"}
    )
    override_provider(ControlledProvider(error), monkeypatch)
    with TestClient(app) as client:
        response = client.get("/events/example")
    assert response.status_code == status
    assert response.json() == {"detail": "Unrelated framework error"}
    assert response.headers["X-Test"] == "preserved"
