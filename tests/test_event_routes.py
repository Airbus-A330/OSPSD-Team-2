"""HTTP behavior tests for the event retrieval endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("event_id", ["event-001", "Review_Event-002"])
@pytest.mark.parametrize(
    ("calendar_id", "configured_calendar_id"),
    [("team-calendar@example.com", "team-calendar@example.com"), ("primary", None)],
)
def test_get_event_returns_google_event_in_public_shape(
    event_id: str,
    calendar_id: str,
    configured_calendar_id: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return translated provider data without contacting Google."""
    if configured_calendar_id is None:
        monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    else:
        monkeypatch.setenv("GOOGLE_CALENDAR_ID", configured_calendar_id)
    google_client = MagicMock()
    google_client.events.return_value.get.return_value.execute.return_value = {
        "id": event_id,
        "summary": "Provider title",
        "start": {"dateTime": "2026-10-07T09:00:00-04:00"},
        "end": {"dateTime": "2026-10-07T10:00:00-04:00"},
        "etag": '"provider-only"',
    }

    with (
        patch("app.events.build_google_calendar_client", return_value=google_client),
        TestClient(app) as client,
    ):
        response = client.get(f"/events/{event_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": event_id,
        "title": "Provider title",
        "start": "2026-10-07T09:00:00-04:00",
        "end": "2026-10-07T10:00:00-04:00",
    }
    google_client.events.return_value.get.assert_called_once_with(
        calendarId=calendar_id, eventId=event_id
    )


@pytest.mark.parametrize("path", ["/events", "/events/"])
def test_get_event_without_required_id_returns_not_found(path: str) -> None:
    """Reject paths that omit the required event ID without redirecting."""
    with TestClient(app) as client:
        response = client.get(path, follow_redirects=False)

    assert response.status_code == 404


def test_post_event_returns_method_not_allowed() -> None:
    """Reject POST requests to the retrieval-only event endpoint."""
    with TestClient(app) as client:
        response = client.post("/events/event-001")

    assert response.status_code == 405
