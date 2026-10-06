"""Local event data used until the provider integration is connected."""

from app.models import Event


def get_event(event_id: str) -> Event:
    """Build a fixed example event for the requested identifier.

    Args:
        event_id: Identifier to preserve in the returned event.

    Returns:
        An event with fixed details; no existence lookup is performed.
    """
    return Event(
        id=event_id,
        title="Team Meeting",
        start="2026-10-01T10:00:00-04:00",
        end="2026-10-01T11:00:00-04:00",
    )
