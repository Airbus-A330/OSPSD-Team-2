"""Application behavior for retrieving calendar events."""

from app.errors import InvalidInputError
from app.models import Event
from app.providers import EventProvider


def validate_event_id(event_id: str) -> None:
    """Reject blank identifiers without changing any valid identifier."""
    if not event_id.strip():
        raise InvalidInputError("Event ID must contain a non-whitespace character")


def validate_event_limit(limit: int) -> None:
    """Reject listing limits outside the public 1–100 range."""
    if not 1 <= limit <= 100:
        raise InvalidInputError("Event limit must be between 1 and 100")


def list_events(limit: int, provider: EventProvider) -> list[Event]:
    """Read a bounded collection without changing provider state."""
    validate_event_limit(limit)
    return provider.list_events(limit)


def get_event(event_id: str, provider: EventProvider) -> Event:
    """Retrieve an event from the configured calendar.

    The provider dependency is supplied by composition code outside the application
    layer so that concrete provider selection remains explicit and testable.

    Args:
        event_id: Event identifier requested by the caller.
        provider: EventProvider implementation selected by the composition layer.

    Returns:
        The event in the service's public representation.

    Raises:
        InvalidInputError: If event_id is empty or whitespace-only.
    """
    validate_event_id(event_id)
    return provider.get_event(event_id)
