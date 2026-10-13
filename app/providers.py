"""Provider-independent event retrieval contract."""

from typing import Protocol

from app.models import Event


class EventProvider(Protocol):
    """Read-only event access as defined in docs/ARCHITECTURE.md."""

    def get_event(self, event_id: str) -> Event:
        """Retrieve one event without changing provider state.

        Args:
            event_id: Opaque, service-visible event identifier.

        Returns:
            The event in the service's existing domain representation.
        """
        ...
