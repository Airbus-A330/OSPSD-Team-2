"""Application composition for the concrete Google Calendar provider."""

import os
from collections.abc import Iterator

from calendar_contract import CalendarService
from fastapi import Depends

from app.calendar_service import CalendarServiceAdapter
from app.event_cache import CachedEventProvider, EventCache
from app.google_calendar import GoogleCalendarProvider, build_google_calendar_client
from app.providers import EventProvider

event_cache = EventCache()


def get_event_provider() -> Iterator[EventProvider]:
    """Supply one request-scoped Google provider behind the domain boundary."""
    client = build_google_calendar_client()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID") or "primary"
    try:
        google_provider = GoogleCalendarProvider(client, calendar_id=calendar_id)
        yield CachedEventProvider(
            google_provider,
            cache=event_cache,
            namespace=calendar_id,
        )
    finally:
        client.close()


def get_calendar_service(
    provider: EventProvider = Depends(get_event_provider),
) -> CalendarService:
    """Supply the shared interface after the GET route's early ID validation.

    Non-HTTP consumers construct CalendarServiceAdapter with validation enabled
    by default. This dependency is only used by the already-validated GET route.
    The nested provider dependency retains ownership of client cleanup.
    """
    return CalendarServiceAdapter(provider, validate_get=False)
