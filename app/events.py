"""Application behavior for retrieving calendar events."""

from app.models import Event
from app.providers import EventProvider


def get_event(event_id: str, provider: EventProvider | None = None) -> Event:
    """Retrieve an event from the configured calendar.

    The provider dependency is supplied by composition code outside the application
    layer so that concrete provider selection remains explicit and testable.

    Args:
        event_id: Event identifier requested by the caller.
        provider: EventProvider implementation selected by the composition layer.

    Returns:
        The event in the service's public representation.

    Raises:
        ValueError: If the caller forgets to provide the provider dependency.
    """
    if provider is None:
        raise ValueError(
            "A provider must be supplied by composition code; application logic "
            "must not instantiate the concrete Google provider."
        )
    return provider.get_event(event_id)
