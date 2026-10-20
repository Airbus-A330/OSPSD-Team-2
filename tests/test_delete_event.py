"""Deletion effects, public failures, and the Google boundary without network I/O."""

import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import HttpLib2Error, Response  # type: ignore[import-untyped]

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.events import delete_event
from app.google_calendar import GoogleCalendarProvider
from app.main import app, get_event_provider
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement


@dataclass
class DeletionProvider:
    """Keep observable event state and optionally fail a deletion attempt."""

    events: dict[str, Event]
    failure: ServiceError | None = None
    calls: list[str] = field(default_factory=list)
    fail_after_delete: bool = False

    def get_event(self, event_id: str) -> Event:
        if event_id not in self.events:
            raise NotFoundError()
        return self.events[event_id]

    def delete_event(self, event_id: str) -> None:
        self.calls.append(event_id)
        if self.failure is not None and not self.fail_after_delete:
            raise self.failure
        self.get_event(event_id)
        del self.events[event_id]
        if self.failure is not None:
            raise self.failure

    def list_events(self, limit: int) -> list[Event]:
        return list(self.events.values())[:limit]

    def create_event(self, event: CreateEventRequest) -> Event:
        pytest.fail("Deletion must not create an event")

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        pytest.fail("Deletion must not replace an event")

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        pytest.fail("Deletion must not patch an event")


@pytest.fixture
def provider() -> DeletionProvider:
    return DeletionProvider(
        {
            event_id: Event(
                id=event_id,
                title="Disposable test event",
                start="2026-10-22T10:00:00-04:00",
                end="2026-10-22T11:00:00-04:00",
            )
            for event_id in ("target", "untouched")
        }
    )


def test_delete_removes_only_target_and_repeated_delete_is_not_found(
    provider: DeletionProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    untouched = provider.events["untouched"].model_dump()
    with TestClient(app) as client:
        assert client.get("/events/target").status_code == 200
        response = client.delete("/events/target")
        assert response.status_code == 204
        assert response.content == b""
        assert "content-type" not in response.headers
        assert not caplog.records
        assert set(provider.events) == {"untouched"}
        assert client.get("/events/untouched").json() == untouched
        assert client.get("/events/target").status_code == 404
        repeated = client.delete("/events/target")
        assert repeated.status_code == 404
        assert repeated.json() == {
            "error": {"code": "not_found", "message": "Event not found"}
        }
    assert provider.calls == ["target", "target"]
    assert provider.events["untouched"].model_dump() == untouched


@pytest.mark.parametrize("event_id", ["", "   ", "\t\n", "\u2003"])
def test_application_rejects_blank_id_before_deletion(
    event_id: str, provider: DeletionProvider
) -> None:
    before = dict(provider.events)
    with pytest.raises(InvalidInputError):
        delete_event(event_id, provider)
    assert provider.calls == []
    assert provider.events == before


@pytest.mark.parametrize("event_id", [" target ", "会議"])
def test_delete_preserves_nonblank_identifier(
    event_id: str, provider: DeletionProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider.events[event_id] = provider.events.pop("target").model_copy(
        update={"id": event_id}
    )
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    with TestClient(app) as client:
        response = client.delete(f"/events/{quote(event_id, safe='')}")
    assert response.status_code == 204
    assert provider.calls == [event_id]
    assert set(provider.events) == {"untouched"}


def test_blank_http_id_is_rejected_before_client_setup(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def unexpected_client() -> None:
        pytest.fail("Invalid DELETE must not construct a Google client")

    monkeypatch.setattr("app.main.build_google_calendar_client", unexpected_client)
    with TestClient(app) as client:
        response = client.delete("/events/%20%20")
    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": "Invalid event ID"}
    }
    record = caplog.records[-1]
    assert record.__dict__["operation"] == "delete_event"
    assert record.__dict__["provider_involved"] is False


@pytest.mark.parametrize(
    ("failure", "status", "code", "message"),
    [
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
def test_delete_failure_is_sanitized_logged_and_does_not_retry(
    failure: type[ServiceError],
    status: int,
    code: str,
    message: str,
    provider: DeletionProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider.failure = failure("private provider response and token")
    before = dict(provider.events)
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    with TestClient(app) as client:
        response = client.delete("/events/target")
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}
    assert provider.calls == ["target"]
    assert provider.events == before
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.__dict__["operation"] == "delete_event"
    assert record.__dict__["error_code"] == code
    assert record.__dict__["http_status"] == status
    assert record.__dict__["provider_involved"] is True
    assert record.exc_info is None
    assert "private provider" not in caplog.text + response.text
    assert "target" not in caplog.text


def test_lost_delete_response_does_not_retry_or_claim_rollback(
    provider: DeletionProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider.failure = ProviderFailureError("Lost response")
    provider.fail_after_delete = True
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    with TestClient(app) as client:
        assert client.delete("/events/target").status_code == 502
    assert provider.calls == ["target"]
    assert set(provider.events) == {"untouched"}


def test_google_delete_uses_configured_calendar_and_returns_no_data() -> None:
    client = MagicMock()
    client.events.return_value.delete.return_value.execute.return_value = b""
    provider = GoogleCalendarProvider(client, calendar_id="configured-calendar")

    provider.delete_event(" opaque-id ")

    client.events.return_value.delete.assert_called_once_with(
        calendarId="configured-calendar", eventId=" opaque-id "
    )
    client.events.return_value.delete.return_value.execute.assert_called_once_with()
    client.events.return_value.get.assert_not_called()
    client.close.assert_not_called()


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        (404, "notFound", NotFoundError),
        (410, "deleted", NotFoundError),
        (410, "fullSyncRequired", ProviderFailureError),
        (403, "forbidden", PermissionDeniedError),
        (403, "rateLimitExceeded", ProviderFailureError),
        (429, "rateLimitExceeded", ProviderFailureError),
        (500, "backendError", ProviderFailureError),
    ],
)
def test_google_delete_translates_failures(
    status: int, reason: str, expected: type[ServiceError]
) -> None:
    client = MagicMock()
    request = client.events.return_value.delete.return_value
    request.execute.side_effect = HttpError(
        Response({"status": str(status)}),
        json.dumps({"error": {"errors": [{"reason": reason}]}}).encode(),
    )
    with pytest.raises(expected):
        GoogleCalendarProvider(client, calendar_id="configured-calendar").delete_event(
            "target"
        )
    request.execute.assert_called_once_with()


@pytest.mark.parametrize("failure", [TransportError("lost"), HttpLib2Error("lost")])
def test_google_delete_translates_transport_failures(failure: Exception) -> None:
    client = MagicMock()
    request = client.events.return_value.delete.return_value
    request.execute.side_effect = failure
    with pytest.raises(ProviderFailureError):
        GoogleCalendarProvider(client, calendar_id="configured-calendar").delete_event(
            "target"
        )
    request.execute.assert_called_once_with()


@pytest.mark.parametrize("fails", [False, True])
def test_delete_composition_closes_client_on_success_or_failure(
    fails: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock()
    request = client.events.return_value.delete.return_value
    if fails:
        request.execute.side_effect = TransportError("lost")
    monkeypatch.setattr("app.main.build_google_calendar_client", lambda: client)
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "configured-calendar")
    with TestClient(app) as http:
        response = http.delete("/events/target")
    assert response.status_code == (502 if fails else 204)
    client.events.return_value.delete.assert_called_once_with(
        calendarId="configured-calendar", eventId="target"
    )
    client.close.assert_called_once_with()


@pytest.mark.parametrize("retains_fields", [False, True])
def test_get_of_google_deleted_tombstone_is_not_found(
    retains_fields: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Google may retain all fields after deletion; neither shape is a live Event."""
    client = MagicMock()
    tombstone: dict[str, object] = {"id": "deleted-target", "status": "cancelled"}
    if retains_fields:
        tombstone.update(
            {
                "summary": "Deleted test event",
                "start": {"dateTime": "2026-10-22T10:00:00-04:00"},
                "end": {"dateTime": "2026-10-22T11:00:00-04:00"},
            }
        )
    client.events.return_value.get.return_value.execute.return_value = tombstone
    monkeypatch.setattr("app.main.build_google_calendar_client", lambda: client)
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "configured-calendar")
    with TestClient(app) as http:
        response = http.get("/events/deleted-target")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Event not found"}
    }
    client.events.return_value.get.assert_called_once_with(
        calendarId="configured-calendar", eventId="deleted-target"
    )
    client.close.assert_called_once_with()
