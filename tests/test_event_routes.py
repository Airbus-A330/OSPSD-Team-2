"""HTTP behavior tests for the event retrieval endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.events import get_event as retrieve_event
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

    provider = get_event_provider()
    assert provider.get_event("event-001") == Event(
        id="event-001",
        title="Provider title",
        start="2026-10-07T09:00:00-04:00",
        end="2026-10-07T10:00:00-04:00",
    )
    google_client.events.return_value.get.assert_called_once_with(
        calendarId=expected_calendar_id, eventId="event-001"
    )


@pytest.mark.parametrize("path", ["/events", "/events/"])
def test_get_event_without_required_id_returns_not_found(path: str) -> None:
    """Reject paths that omit the required event ID without redirecting."""
    with TestClient(app) as client:
        response = client.get(path, follow_redirects=False)

    assert response.status_code == 404


def test_application_logic_requires_explicit_provider() -> None:
    """The application layer must not decide which concrete provider to use."""
    with pytest.raises(ValueError, match="provider"):
        retrieve_event("event-001", provider=None)


def test_post_event_returns_method_not_allowed() -> None:
    """Reject POST requests to the retrieval-only event endpoint."""
    with TestClient(app) as client:
        response = client.post("/events/event-001")

    assert response.status_code == 405
