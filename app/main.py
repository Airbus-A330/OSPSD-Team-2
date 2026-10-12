"""Application entry point for the Calendar Service."""

from fastapi import Depends, FastAPI

from app.google_calendar import EventProvider, GoogleCalendarProvider
from app.events import get_event
from app.models import Event

app = FastAPI()


def get_event_provider() -> EventProvider:
    """FastAPI dependency that supplies the configured GoogleCalendarProvider.

    This is the explicit composition point where the concrete provider is chosen.
    The application layer depends only on the EventProvider protocol.
    """
    return GoogleCalendarProvider()


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
