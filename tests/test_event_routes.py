"""HTTP behavior tests for the event retrieval endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app, get_event_provider
from app.models import Event


@pytest.mark.parametrize(
    ("configured_calendar_id", "expected_calendar_id"),
    [("team-calendar@example.com", "team-calendar@example.com"), (None, "primary")],
)
def test_provider_composition_uses_configured_calendar(
    configured_calendar_id: str | None,
    expected_calendar_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build the Google provider with the configured or default calendar."""
    if configured_calendar_id is None:
        monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    else:
        monkeypatch.setenv("GOOGLE_CALENDAR_ID", configured_calendar_id)

    google_client = MagicMock()
    google_client.events.return_value.get.return_value.execute.return_value = {
        "id": "event-001",
        "summary": "Provider title",
        "start": {"dateTime": "2026-10-07T09:00:00-04:00"},
        "end": {"dateTime": "2026-10-07T10:00:00-04:00"},
    }
    monkeypatch.setattr("app.main.build_google_calendar_client", lambda: google_client)

    dependency = get_event_provider(Request({"type": "http"}))
    provider = next(dependency)
    try:
        assert provider.get_event("event-001") == Event(
            id="event-001",
            title="Provider title",
            start="2026-10-07T09:00:00-04:00",
            end="2026-10-07T10:00:00-04:00",
        )
        google_client.events.return_value.get.assert_called_once_with(
            calendarId=expected_calendar_id, eventId="event-001"
        )
    finally:
        with pytest.raises(StopIteration):
            next(dependency)

    google_client.close.assert_called_once_with()


def test_collection_trailing_slash_redirects_to_listing() -> None:
    """The collection route now lists events rather than representing a missing ID."""
    with TestClient(app) as client:
        response = client.get("/events/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/events")


def test_post_event_returns_method_not_allowed() -> None:
    """Reject POST requests to the retrieval-only event endpoint."""
    with TestClient(app) as client:
        response = client.post("/events/event-001")

    assert response.status_code == 405


def test_listing_uses_google_composition_and_closes_request_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    google_client = MagicMock()
    google_client.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "listed-event",
                "summary": "Listed event",
                "start": {"dateTime": "2026-10-20T09:00:00Z"},
                "end": {"dateTime": "2026-10-20T10:00:00Z"},
            }
        ]
    }
    monkeypatch.setattr("app.main.build_google_calendar_client", lambda: google_client)
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "listing-calendar")
    with TestClient(app) as client:
        response = client.get("/events?limit=1")
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "listed-event",
            "title": "Listed event",
            "start": "2026-10-20T09:00:00Z",
            "end": "2026-10-20T10:00:00Z",
        }
    ]
    google_client.events.return_value.list.assert_called_once_with(
        calendarId="listing-calendar", maxResults=1, singleEvents=True
    )
    google_client.close.assert_called_once_with()
