"""Application and HTTP behavior with a controlled EventProvider."""

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.events import get_event
from app.main import app, get_event_provider
from app.models import Event
from app.providers import EventProvider


@dataclass
class ControlledEventProvider:
    """Return configured domain events without credentials or external I/O."""

    events: dict[str, Event]

    def get_event(self, event_id: str) -> Event:
        """Return the configured event for the requested identifier."""
        return self.events[event_id]


@pytest.fixture
def configured_events() -> dict[str, Event]:
    return {
        "Review_Event-001": Event(
            id="Review_Event-001",
            title="Design review",
            start="2026-10-13T09:00:00-04:00",
            end="2026-10-13T10:00:00-04:00",
        ),
        "event-002": Event(
            id="event-002",
            title="Planning session",
            start="2026-10-14T16:00:00+02:00",
            end="2026-10-14T16:30:00+02:00",
        ),
    }


@pytest.fixture
def controlled_provider(configured_events: dict[str, Event]) -> EventProvider:
    return ControlledEventProvider(configured_events)


@pytest.mark.parametrize("event_id", ["Review_Event-001", "event-002"])
def test_application_returns_configured_event(
    event_id: str,
    controlled_provider: EventProvider,
    configured_events: dict[str, Event],
) -> None:
    assert (
        get_event(event_id, provider=controlled_provider) == configured_events[event_id]
    )


def test_application_repeated_reads_preserve_events(
    controlled_provider: EventProvider,
    configured_events: dict[str, Event],
) -> None:
    before = {key: event.model_dump() for key, event in configured_events.items()}

    for event_id in ["Review_Event-001", "event-002", "Review_Event-001"]:
        assert (
            get_event(event_id, provider=controlled_provider).model_dump()
            == before[event_id]
        )

    assert {
        key: event.model_dump() for key, event in configured_events.items()
    } == before


@pytest.mark.parametrize("event_id", ["Review_Event-001", "event-002"])
def test_http_returns_configured_provider_event(
    event_id: str,
    controlled_provider: EventProvider,
    configured_events: dict[str, Event],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def supply_provider() -> EventProvider:
        return controlled_provider

    monkeypatch.setitem(app.dependency_overrides, get_event_provider, supply_provider)
    with TestClient(app) as client:
        response = client.get(f"/events/{event_id}")

    expected = configured_events[event_id]
    assert response.status_code == 200
    assert response.json() == {
        "id": expected.id,
        "title": expected.title,
        "start": expected.start,
        "end": expected.end,
    }
