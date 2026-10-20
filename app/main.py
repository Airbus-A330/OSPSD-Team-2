"""Application entry point for the Calendar Service."""

import os
from collections.abc import Iterator

from fastapi import Depends, FastAPI, Query, Request
from pydantic import TypeAdapter, ValidationError

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
)
from app.events import get_event, list_events, validate_event_id, validate_event_limit
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


def validate_list_request(request: Request) -> None:
    """Reject invalid limits before resolving the Google provider dependency."""
    request.state.operation = "list_events"
    request.state.provider_involved = False
    try:
        limit = TypeAdapter(int).validate_python(
            request.query_params.get("limit", "10")
        )
    except ValidationError:
        raise InvalidInputError("Event limit must be an integer") from None
    validate_event_limit(limit)


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
    "/events",
    response_model=list[Event],
    dependencies=[Depends(validate_list_request)],
)
def read_events(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    provider: EventProvider = Depends(get_event_provider),
) -> list[Event]:
    """Return at most limit public events from the configured calendar."""
    request.state.provider_involved = True
    return list_events(limit, provider=provider)


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
