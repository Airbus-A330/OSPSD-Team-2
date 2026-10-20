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

    def list_events(self, limit: int) -> list[Event]:
        """Read at most limit events from the configured calendar.

        The application supplies a limit from 1 to 100. Return domain Events
        in provider order without changing calendar state. A short or empty
        list is allowed; completeness and pagination are not promised.
        Provider failures use the shared service errors, never SDK exceptions.
        """
        ...
