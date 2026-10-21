"""Provider-independent calendar operation contract."""

from typing import Protocol

from app.models import CreateEventRequest, Event, EventPatch, EventReplacement


class EventProvider(Protocol):
    """Calendar event operations as defined in docs/ARCHITECTURE.md."""

    def delete_event(self, event_id: str) -> None:
        """Delete the identified event, returning no provider data.

        Accept an unchanged opaque ID. Missing events, denied access, and
        provider failures use shared service errors. A lost response does not
        establish whether deletion occurred; callers must not assume rollback.
        """
        ...

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        """Apply only explicitly supplied editable fields to an existing event.

        Accept validated domain changes and an opaque ID; preserve omitted
        fields and return the resulting domain Event. Shared service errors
        describe failure; a failed write may have taken effect remotely.
        """
        ...

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

    def create_event(self, event: CreateEventRequest) -> Event:
        """Create one event and return its provider-generated identifier.

        Args:
            event: Provider-independent title and timed-event boundaries.

        Returns:
            The created event in the service's public representation.
        """
        ...

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        """Replace all editable fields of an existing event and return its result.

        Inputs are validated domain values. Missing events, access denial, and
        provider failures use the shared service errors; a failed write may
        have taken effect remotely.
        """
        ...
