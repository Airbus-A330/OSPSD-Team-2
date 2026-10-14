"""Application behavior for retrieving calendar events."""

from app.models import Event
from app.providers import EventProvider


def get_event(event_id: str, provider: EventProvider) -> Event:
    """Retrieve an event from the configured calendar.

    The provider dependency is supplied by composition code outside the application
    layer so that concrete provider selection remains explicit and testable.

    Args:
        event_id: Event identifier requested by the caller.
        provider: EventProvider implementation selected by the composition layer.

    Returns:
        The event in the service's public representation.
    """
    return provider.get_event(event_id)
