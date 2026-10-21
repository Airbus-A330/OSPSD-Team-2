"""Google PATCH request mapping and failure translation without network access."""

import json
import socket
from unittest.mock import Mock

import pytest
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import HttpLib2Error, Response  # type: ignore[import-untyped]

from app.errors import (
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.google_calendar import GoogleCalendarProvider
from app.models import Event, EventPatch


def _active_google_event(event_id: str) -> dict[str, object]:
    return {
        "id": event_id,
        "summary": "Original",
        "start": {"dateTime": "2026-10-22T10:00:00-04:00"},
        "end": {"dateTime": "2026-10-22T11:00:00-04:00"},
    }


@pytest.mark.parametrize(
    ("changes", "body"),
    [
        ({"title": " New title "}, {"summary": " New title "}),
        (
            {"start": "2026-10-22T10:15:00-04:00"},
            {"start": {"dateTime": "2026-10-22T10:15:00-04:00"}},
        ),
        (
            {"end": "2026-10-22T12:00:00-04:00"},
            {"end": {"dateTime": "2026-10-22T12:00:00-04:00"}},
        ),
        (
            {
                "title": "New",
                "start": "2026-10-22T10:00:00Z",
                "end": "2026-10-22T11:00:00Z",
            },
            {
                "summary": "New",
                "start": {"dateTime": "2026-10-22T10:00:00Z"},
                "end": {"dateTime": "2026-10-22T11:00:00Z"},
            },
        ),
    ],
)
def test_google_patch_sends_only_supplied_fields(
    changes: dict[str, str],
    body: dict[str, object],
) -> None:
    client = Mock()
    expected = Event(
        id=" opaque-id ",
        title=changes.get("title", "Original"),
        start=changes.get("start", "2026-10-22T10:00:00-04:00"),
        end=changes.get("end", "2026-10-22T11:00:00-04:00"),
    )
    client.events.return_value.patch.return_value.execute.return_value = {
        "id": expected.id,
        "summary": expected.title,
        "start": {"dateTime": expected.start},
        "end": {"dateTime": expected.end},
        "etag": "private-metadata",
    }
    client.events.return_value.get.return_value.execute.return_value = (
        _active_google_event(expected.id)
    )
    provider = GoogleCalendarProvider(client, calendar_id="test-calendar")
    assert provider.patch_event(expected.id, EventPatch(**changes)) == expected
    client.events.return_value.patch.assert_called_once_with(
        calendarId="test-calendar",
        eventId=expected.id,
        body=body,
    )
    client.events.return_value.patch.return_value.execute.assert_called_once_with()
    client.events.return_value.update.assert_not_called()
    client.events.return_value.get.assert_called_once_with(
        calendarId="test-calendar", eventId=expected.id
    )


@pytest.mark.parametrize(
    ("status", "reason", "expected_error"),
    [
        (404, "notFound", NotFoundError),
        (403, "forbidden", PermissionDeniedError),
        (403, "rateLimitExceeded", ProviderFailureError),
        (500, "backendError", ProviderFailureError),
    ],
)
def test_google_patch_translates_http_failures(
    status: int,
    reason: str,
    expected_error: type[ServiceError],
) -> None:
    client = Mock()
    client.events.return_value.get.return_value.execute.return_value = (
        _active_google_event("event")
    )
    client.events.return_value.patch.return_value.execute.side_effect = HttpError(
        Response({"status": status}),
        json.dumps(
            {"error": {"message": "private", "errors": [{"reason": reason}]}}
        ).encode(),
    )
    with pytest.raises(expected_error) as exc_info:
        GoogleCalendarProvider(client, calendar_id="primary").patch_event(
            "event", EventPatch(title="New")
        )
    assert "private" not in str(exc_info.value)
    client.events.return_value.patch.return_value.execute.assert_called_once_with()


@pytest.mark.parametrize(
    "error",
    [
        TransportError("private"),
        HttpLib2Error("private"),
        socket.timeout("private"),
        ConnectionResetError("private"),
    ],
)
def test_google_patch_translates_transport_failures(error: Exception) -> None:
    client = Mock()
    client.events.return_value.get.return_value.execute.return_value = (
        _active_google_event("event")
    )
    client.events.return_value.patch.return_value.execute.side_effect = error
    with pytest.raises(ProviderFailureError):
        GoogleCalendarProvider(client, calendar_id="primary").patch_event(
            "event", EventPatch(title="New")
        )
    client.events.return_value.patch.return_value.execute.assert_called_once_with()


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {
            "id": "event",
            "summary": "New",
            "start": {"date": "2026-10-22"},
            "end": {"date": "2026-10-23"},
        },
    ],
)
def test_google_patch_malformed_result_is_provider_failure(result: object) -> None:
    client = Mock()
    client.events.return_value.get.return_value.execute.return_value = (
        _active_google_event("event")
    )
    client.events.return_value.patch.return_value.execute.return_value = result
    with pytest.raises(ProviderFailureError):
        GoogleCalendarProvider(client, calendar_id="primary").patch_event(
            "event", EventPatch(title="New")
        )
    client.events.return_value.patch.return_value.execute.assert_called_once_with()
