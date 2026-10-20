"""Application entry point for the Calendar Service."""

import os
from collections.abc import Iterator

from fastapi import Depends, FastAPI, Request

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
)
from app.events import get_event, validate_event_id
from app.google_calendar import GoogleCalendarProvider, build_google_calendar_client
from app.http_errors import service_error_response
from app.models import Event
from app.providers import EventProvider

app = FastAPI()

for error_type in (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
):
    app.add_exception_handler(error_type, service_error_response)


def validate_event_request(event_id: str, request: Request) -> None:
    """Run shared validation before resolving the provider dependency."""
    request.state.provider_involved = False
    validate_event_id(event_id)


def get_event_provider(request: Request) -> Iterator[EventProvider]:
    """FastAPI dependency that supplies the configured GoogleCalendarProvider.

    This is the explicit composition point where the concrete provider is chosen.
    The application layer depends only on the EventProvider protocol. The Google
    client is scoped to one request and closed afterward.
    """
    request.state.provider_involved = True
    client = build_google_calendar_client()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID") or "primary"
    try:
        yield GoogleCalendarProvider(client, calendar_id=calendar_id)
    finally:
        client.close()


@app.get(
    "/events/{event_id}",
    response_model=Event,
    dependencies=[Depends(validate_event_request)],
)
def read_event(
    event_id: str,
    request: Request,
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Return an event from the configured calendar.

    Args:
        event_id: Identifier supplied in the request path.
        request: Request-local context for safe failure logging.
        provider: Injected EventProvider supplying the concrete Google provider.

    Returns:
        The event in the service's public representation.
    """
    request.state.provider_involved = True
    return get_event(event_id, provider=provider)
