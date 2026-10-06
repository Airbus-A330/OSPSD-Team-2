"""HTTP behavior tests for the event retrieval endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("event_id", ["event-001", "Review_Event-002"])
def test_get_event_returns_expected_json_for_requested_id(event_id: str) -> None:
    """Return the complete event response with the requested ID unchanged."""
    with TestClient(app) as client:
        response = client.get(f"/events/{event_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": event_id,
        "title": "Team Meeting",
        "start": "2026-10-01T10:00:00-04:00",
        "end": "2026-10-01T11:00:00-04:00",
    }


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
