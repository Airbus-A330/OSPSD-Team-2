"""Application composition for the concrete Google Calendar provider."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from calendar_contract import CalendarService
from fastapi import Depends

from app.calendar_service import CalendarServiceAdapter
from app.event_cache import CachedEventProvider, EventCache
from app.google_calendar import GoogleCalendarProvider, build_google_calendar_client
from app.providers import EventProvider

event_cache = EventCache()


@contextmanager
def open_calendar_service() -> Iterator[CalendarService]:
    """Supply the configured shared Calendar service to a composed workflow.

    The caller owns this context for one synchronous workflow execution. The
    existing provider dependency closes its client on success or failure.
    Calendar errors propagate unchanged; no operation is retried or rolled back.

    Yields:
        Team 2's implementation of the tagged shared CalendarService contract.

    Raises:
        ValueError: If CALENDAR_IMPLEMENTATION is set to anything but team2.
    """
    if os.getenv("CALENDAR_IMPLEMENTATION", "team2") != "team2":
        raise ValueError("CALENDAR_IMPLEMENTATION must be team2")

    with contextmanager(get_event_provider)() as provider:
        yield CalendarServiceAdapter(provider)


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
    """Supply the shared interface after early HTTP input validation.

    Non-HTTP consumers construct CalendarServiceAdapter with validation enabled
    by default. All common routes consume this shared service boundary.
    The nested provider dependency retains ownership of client cleanup.
    """
    return CalendarServiceAdapter(provider, validate_get=False)
