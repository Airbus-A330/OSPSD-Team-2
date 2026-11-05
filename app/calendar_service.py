"""Adapt existing application operations to the shared Python interface."""

from calendar_contract import CreateEvent, Event, ReplaceEvent

from app import events
from app.models import CreateEventRequest, EventReplacement
from app.providers import EventProvider


class CalendarServiceAdapter:
    """Reuse Team 2 operations without exposing its extension methods.

    GET is the migrated HTTP slice. The other methods bridge existing operations;
    their complete conformance and HTTP migration remain follow-up work.
    """

    def __init__(self, provider: EventProvider, *, validate_get: bool = True) -> None:
        self._provider = provider
        self._validate_get = validate_get

    def get(self, event_id: str) -> Event:
        """Read an event, validating IDs unless HTTP already validated them."""
        return events.get_event(event_id, self._provider, validate=self._validate_get)

    def create(self, request: CreateEvent) -> Event:
        """Bridge a shared request to the existing create operation, without retries."""
        return events.create_event(
            CreateEventRequest(**request.model_dump()), self._provider
        )

    def replace(self, event_id: str, request: ReplaceEvent) -> Event:
        """Bridge a shared replacement to the existing application operation."""
        return events.replace_event(
            event_id, EventReplacement(**request.model_dump()), self._provider
        )

    def delete(self, event_id: str) -> None:
        """Delegate deletion without changing its existing provider behavior."""
        events.delete_event(event_id, self._provider)
