"""Application entry point for the Calendar Service."""

import os
from collections.abc import Iterator

from fastapi import Body, Depends, FastAPI, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import TypeAdapter, ValidationError
from starlette.exceptions import HTTPException

from app.event_cache import CachedEventProvider, EventCache
from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
)
from app.events import (
    create_event,
    delete_event,
    get_event,
    list_events,
    patch_event,
    replace_event,
    validate_create_event,
    validate_event_id,
    validate_event_limit,
    validate_event_patch,
)
from app.google_calendar import GoogleCalendarProvider, build_google_calendar_client
from app.http_errors import (
    http_error_response,
    request_validation_error_response,
    service_error_response,
)
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider

app = FastAPI()
app.add_exception_handler(HTTPException, http_error_response)
app.add_exception_handler(RequestValidationError, request_validation_error_response)
event_cache = EventCache()

for error_type in (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
):
    app.add_exception_handler(error_type, service_error_response)


def validate_delete_request(event_id: str, request: Request) -> None:
    """Reject blank IDs before provider construction or any deletion attempt."""
    request.state.operation = "delete_event"
    request.state.provider_involved = False
    request.state.invalid_input_message = "Invalid event ID"
    validate_event_id(event_id)


def validate_event_request(event_id: str, request: Request) -> None:
    """Run shared validation before resolving the provider dependency."""
    request.state.operation = "get_event"
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


def validate_create_request(
    request: Request,
    body: object = Body(
        default=None, json_schema_extra=CreateEventRequest.model_json_schema()
    ),
) -> CreateEventRequest:
    """Validate a create request before resolving the provider dependency."""
    request.state.operation = "create_event"
    request.state.provider_involved = False
    try:
        event = CreateEventRequest.model_validate(body)
    except ValidationError:
        raise InvalidInputError("Invalid event data") from None
    validate_create_event(event)
    return event


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
        google_provider = GoogleCalendarProvider(client, calendar_id=calendar_id)
        yield CachedEventProvider(
            google_provider,
            cache=event_cache,
            namespace=calendar_id,
        )
    finally:
        client.close()


@app.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(validate_delete_request)],
    name="delete_event",
)
def delete_calendar_event(
    event_id: str,
    request: Request,
    provider: EventProvider = Depends(get_event_provider),
) -> Response:
    """Delete one event and return an empty response only after success."""
    request.state.provider_involved = True
    delete_event(event_id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@app.post(
    "/events",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"requestBody": {"required": True}},
    name="create_event",
)
def create_event_route(
    request: Request,
    event: CreateEventRequest = Depends(validate_create_request),
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Create a timed event in the configured calendar."""
    request.state.operation = "create_event"
    request.state.provider_involved = True
    return create_event(event, provider=provider)


def validate_replacement_request(
    event_id: str,
    request: Request,
    body: object = Body(
        default=None, json_schema_extra=EventReplacement.model_json_schema()
    ),
) -> EventReplacement:
    """Reject invalid PUT input before provider construction, including OAuth."""
    request.state.operation = "replace_event"
    request.state.provider_involved = False
    validate_event_id(event_id)
    request.state.invalid_input_message = "Invalid event replacement"
    try:
        return EventReplacement.model_validate(body)
    except ValidationError:
        raise InvalidInputError("Invalid event replacement") from None


@app.put(
    "/events/{event_id}",
    response_model=Event,
    openapi_extra={"requestBody": {"required": True}},
    name="replace_event",
)
def replace_calendar_event(
    event_id: str,
    request: Request,
    replacement: EventReplacement = Depends(validate_replacement_request),
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Replace title, start, and end of an existing event and return its values."""
    request.state.provider_involved = True
    return replace_event(event_id, replacement, provider)


def validate_patch_request(
    event_id: str,
    request: Request,
    body: object = Body(default=None, json_schema_extra=EventPatch.model_json_schema()),
) -> EventPatch:
    """Validate PATCH input before provider construction, including OAuth."""
    request.state.operation = "patch_event"
    request.state.provider_involved = False
    request.state.invalid_input_message = "Invalid event ID"
    validate_event_id(event_id)
    request.state.invalid_input_message = "Invalid input"
    try:
        changes = EventPatch.model_validate(body)
    except ValidationError:
        raise InvalidInputError("Invalid event patch") from None
    validate_event_patch(changes)
    return changes


@app.patch(
    "/events/{event_id}",
    response_model=Event,
    openapi_extra={"requestBody": {"required": True}},
    name="patch_event",
)
def patch_calendar_event(
    event_id: str,
    request: Request,
    changes: EventPatch = Depends(validate_patch_request),
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Partially update an existing event, preserving omitted fields."""
    request.state.provider_involved = True
    return patch_event(event_id, changes, provider)
