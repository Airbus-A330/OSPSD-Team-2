"""Validate structural compatibility with the EventProvider contract."""

from app.models import Event, EventReplacement
from app.providers import EventProvider


def test_implementation_satisfies_provider_without_inheritance() -> None:
    class ExampleProvider:
        def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
            return Event(id=event_id, **replacement.model_dump())

        def get_event(self, event_id: str) -> Event:
            return Event(
                id=event_id,
                title="Team Meeting",
                start="2026-10-01T10:00:00-04:00",
                end="2026-10-01T11:00:00-04:00",
            )

        def list_events(self, limit: int) -> list[Event]:
            return [self.get_event("opaque-event-123")][:limit]

    provider: EventProvider = ExampleProvider()

    assert provider.get_event(event_id="opaque-event-123") == Event(
        id="opaque-event-123",
        title="Team Meeting",
        start="2026-10-01T10:00:00-04:00",
        end="2026-10-01T11:00:00-04:00",
    )
