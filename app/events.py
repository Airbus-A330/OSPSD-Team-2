"""Application behavior for retrieving calendar events."""

import os

from app.google_calendar import build_google_calendar_client, translate_google_event
from app.google_calendar import get_event as get_google_event
from app.models import Event


def get_event(event_id: str) -> Event:
    """Retrieve an event from the configured Google calendar.

    Args:
        event_id: Google Calendar event identifier.

    Returns:
        The event in the service's public representation.
    """
    client = build_google_calendar_client()
    provider_event = get_google_event(
        client,
        calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        event_id=event_id,
    )
    return translate_google_event(provider_event)
