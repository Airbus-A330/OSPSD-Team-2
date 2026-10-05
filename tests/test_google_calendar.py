"""Credential-free tests of the Google Calendar SDK boundary."""

from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from app.google_calendar import get_event


@pytest.mark.parametrize("calendar_id", ["primary", "team@group.calendar.google.com"])
def test_get_event_passes_identifiers_to_google(calendar_id: str) -> None:
    client = Mock()

    get_event(client, calendar_id=calendar_id, event_id="event123")

    client.events.return_value.get.assert_called_once_with(
        calendarId=calendar_id, eventId="event123"
    )
    client.events.return_value.get.return_value.execute.assert_called_once_with()


def test_get_event_returns_raw_result_for_translation() -> None:
    client = Mock()
    provider_event = {
        "id": "event123",
        "summary": "Team meeting",
        "start": {"dateTime": "2026-10-07T10:00:00-04:00"},
        "end": {"dateTime": "2026-10-07T11:00:00-04:00"},
        "etag": '"provider-version"',
    }
    client.events.return_value.get.return_value.execute.return_value = provider_event

    result = get_event(client, calendar_id="primary", event_id="event123")

    assert result == provider_event


def test_get_event_propagates_provider_failure() -> None:
    client = Mock()
    error = HttpError(Response({"status": "404"}), b'{"error": "Not Found"}')
    client.events.return_value.get.return_value.execute.side_effect = error

    with pytest.raises(HttpError) as caught:
        get_event(client, calendar_id="primary", event_id="missing123")

    assert caught.value is error
