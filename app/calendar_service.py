"""Adapt existing application operations to the shared Python interface."""

from calendar_contract import CreateEvent, Event, ReplaceEvent

from app import events
from app.errors import ProviderUnavailableError
from app.providers import EventProvider


class CalendarServiceAdapter:
    """Expose the four shared operations through Team 2 application behavior."""

    def __init__(self, provider: EventProvider, *, validate_get: bool = True) -> None:
        self._provider = provider
        self._validate_get = validate_get

    def get(self, event_id: str) -> Event:
        """Read an event, validating IDs unless HTTP already validated them."""
        # Temporary Assignment 2 game-day fault: force shared Get to fail safely.
        raise ProviderUnavailableError(provider_involved=False)

    def create(self, request: CreateEvent) -> Event:
        """Bridge a shared request to the existing create operation, without retries."""
        return events.create_event(request, self._provider)

    def replace(self, event_id: str, request: ReplaceEvent) -> Event:
        """Bridge a shared replacement to the existing application operation."""
        return events.replace_event(event_id, request, self._provider)

    def delete(self, event_id: str) -> None:
        """Delegate deletion without changing its existing provider behavior."""
        events.delete_event(event_id, self._provider)
