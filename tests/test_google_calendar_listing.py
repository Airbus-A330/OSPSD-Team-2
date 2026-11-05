"""Google event listing through a controlled SDK client, without external I/O."""

import socket
from unittest.mock import Mock

import pytest
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import HttpLib2Error, Response  # type: ignore[import-untyped]

from app.errors import PermissionDeniedError, ProviderFailureError, ServiceError
from app.google_calendar import GoogleCalendarProvider
from app.models import Event


def test_google_list_returns_bounded_domain_events_and_hides_page_tokens() -> None:
    client = Mock()
    client.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": f"event-{index}",
                "summary": "Listed event",
                "start": {"dateTime": "2026-10-20T09:00:00+02:00"},
                "end": {"dateTime": "2026-10-20T10:00:00+02:00"},
                "etag": "provider-only",
            }
            for index in range(3)
        ],
        "nextPageToken": "provider-only-token",
    }
    provider = GoogleCalendarProvider(client, calendar_id="team-calendar")

    assert provider.list_events(2) == [
        Event(
            id=f"event-{index}",
            title="Listed event",
            start="2026-10-20T09:00:00+02:00",
            end="2026-10-20T10:00:00+02:00",
        )
        for index in range(2)
    ]
    client.events.return_value.list.assert_called_once_with(
        calendarId="team-calendar", maxResults=2, singleEvents=True
    )


def test_google_list_without_items_returns_empty_collection() -> None:
    client = Mock()
    client.events.return_value.list.return_value.execute.return_value = {}
    assert GoogleCalendarProvider(client, calendar_id="primary").list_events(10) == []


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(403, PermissionDeniedError), (500, ProviderFailureError)],
)
def test_google_list_translates_provider_failures(
    status: int, error_type: type[ServiceError]
) -> None:
    client = Mock()
    client.events.return_value.list.return_value.execute.side_effect = HttpError(
        Response({"status": str(status)}), b'{"error": "synthetic private detail"}'
    )
    with pytest.raises(error_type) as caught:
        GoogleCalendarProvider(client, calendar_id="primary").list_events(10)
    assert "synthetic private detail" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "error",
    [
        HttpLib2Error("synthetic detail"),
        TransportError("synthetic detail"),
        socket.timeout("synthetic detail"),
        ConnectionResetError("synthetic detail"),
    ],
)
def test_google_list_translates_transport_failures(error: Exception) -> None:
    client = Mock()
    client.events.return_value.list.return_value.execute.side_effect = error
    with pytest.raises(ProviderFailureError):
        GoogleCalendarProvider(client, calendar_id="primary").list_events(10)


def test_google_list_rejects_unsupported_all_day_response_as_provider_failure() -> None:
    client = Mock()
    client.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "all-day",
                "summary": "Unsupported event",
                "start": {"date": "2026-10-20"},
                "end": {"date": "2026-10-21"},
            }
        ]
    }
    with pytest.raises(ProviderFailureError):
        GoogleCalendarProvider(client, calendar_id="primary").list_events(10)
