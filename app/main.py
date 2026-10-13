"""Application entry point for the Calendar Service."""

import os

from fastapi import Depends, FastAPI

from app.events import get_event
from app.google_calendar import GoogleCalendarProvider, build_google_calendar_client
from app.models import Event
from app.providers import EventProvider

app = FastAPI()


def get_event_provider() -> EventProvider:
    """FastAPI dependency that supplies the configured GoogleCalendarProvider.

    This is the explicit composition point where the concrete provider is chosen.
    The application layer depends only on the EventProvider protocol.
    """
    client = build_google_calendar_client()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID") or "primary"
    return GoogleCalendarProvider(client, calendar_id=calendar_id)


@app.get("/events/{event_id}", response_model=Event)
def read_event(
    event_id: str, provider: EventProvider = Depends(get_event_provider)
) -> Event:
    """Return an event from the configured calendar.

    Args:
        event_id: Identifier supplied in the request path.
        provider: Injected EventProvider supplying the concrete Google provider.

    Returns:
        The event in the service's public representation.
    """
    return get_event(event_id, provider=provider)
