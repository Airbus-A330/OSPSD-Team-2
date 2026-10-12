"""Test the Google provider boundary with a controlled SDK client."""

from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]

from app.google_calendar import GoogleCalendarProvider
from app.models import Event


@pytest.mark.parametrize(
    ("calendar_id", "event_id"),
    [("primary", "event123"), ("team@group.calendar.google.com", "Review_Event-002")],
)
def test_provider_queries_configured_calendar_and_returns_domain_event(
    calendar_id: str, event_id: str
) -> None:
    """Use the supplied identifiers and return only the public event fields."""
    client = Mock()
    request = client.events.return_value.get.return_value
    request.execute.return_value = {
        "id": event_id,
        "summary": "Team review",
        "start": {"dateTime": "2026-10-14T09:00:00.123+05:30"},
        "end": {"dateTime": "2026-10-14T10:00:00.123+05:30"},
        "etag": '"provider-only"',
        "organizer": {"email": "organizer@example.com"},
    }

    provider = GoogleCalendarProvider(client, calendar_id=calendar_id)
    assert client.mock_calls == []

    result = provider.get_event(event_id)

    client.events.return_value.get.assert_called_once_with(
        calendarId=calendar_id, eventId=event_id
    )
    request.execute.assert_called_once_with()
    assert isinstance(result, Event)
    assert result.model_dump() == {
        "id": event_id,
        "title": "Team review",
        "start": "2026-10-14T09:00:00.123+05:30",
        "end": "2026-10-14T10:00:00.123+05:30",
    }


def test_provider_propagates_google_failure() -> None:
    """Preserve the SDK exception rather than fabricate a successful event."""
    client = Mock()
    error = HttpError(Response({"status": "404"}), b'{"error": "Not Found"}')
    client.events.return_value.get.return_value.execute.side_effect = error
    provider = GoogleCalendarProvider(client, calendar_id="primary")

    with pytest.raises(HttpError) as caught:
        provider.get_event("missing123")

    assert caught.value is error


def test_provider_does_not_return_untranslatable_google_data() -> None:
    """Keep the existing failure for all-day events without dateTime fields."""
    client = Mock()
    client.events.return_value.get.return_value.execute.return_value = {
        "id": "all-day123",
        "summary": "All-day event",
        "start": {"date": "2026-10-14"},
        "end": {"date": "2026-10-15"},
    }
    provider = GoogleCalendarProvider(client, calendar_id="primary")

    with pytest.raises(KeyError, match="dateTime"):
        provider.get_event("all-day123")
