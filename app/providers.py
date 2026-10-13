"""Provider-independent contracts for external event sources."""

from typing import Protocol

from app.models import Event


class EventProvider(Protocol):
    """Retrieve domain events without exposing provider-specific data."""

    def get_event(self, event_id: str) -> Event:
        """Return the event identified by the opaque service-visible ID."""
        ...
