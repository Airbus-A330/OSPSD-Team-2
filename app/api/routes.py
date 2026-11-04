"""Thin FastAPI routes for Calendar operations."""

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.validation import (
    validate_create_request,
    validate_delete_request,
    validate_get_request,
    validate_list_request,
    validate_patch_request,
    validate_replacement_request,
)
from app.composition import get_event_provider
from app.events import (
    create_event,
    delete_event,
    get_event,
    list_events,
    patch_event,
    replace_event,
)
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider

router = APIRouter()


@router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(validate_delete_request)],
    name="delete_event",
)
def delete_calendar_event(
    event_id: str,
    provider: EventProvider = Depends(get_event_provider),
) -> Response:
    """Delete one event and return an empty response only after success."""
    delete_event(event_id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/events",
    response_model=list[Event],
    dependencies=[Depends(validate_list_request)],
    name="list_events",
)
def read_events(
    limit: int = Query(default=10, ge=1, le=100),
    provider: EventProvider = Depends(get_event_provider),
) -> list[Event]:
    """Return at most limit public events from the configured calendar."""
    return list_events(limit, provider=provider)


@router.get(
    "/events/{event_id}",
    response_model=Event,
    dependencies=[Depends(validate_get_request)],
    name="get_event",
)
def read_event(
    event_id: str,
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Return one event from the configured calendar."""
    return get_event(event_id, provider=provider, validate=False)


@router.post(
    "/events",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"requestBody": {"required": True}},
    name="create_event",
)
def create_event_route(
    event: CreateEventRequest = Depends(validate_create_request),
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Create a timed event in the configured calendar."""
    return create_event(event, provider=provider)


@router.put(
    "/events/{event_id}",
    response_model=Event,
    openapi_extra={"requestBody": {"required": True}},
    name="replace_event",
)
def replace_calendar_event(
    event_id: str,
    replacement: EventReplacement = Depends(validate_replacement_request),
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Replace title, start, and end of an existing event."""
    return replace_event(event_id, replacement, provider)


@router.patch(
    "/events/{event_id}",
    response_model=Event,
    openapi_extra={"requestBody": {"required": True}},
    name="patch_event",
)
def patch_calendar_event(
    event_id: str,
    changes: EventPatch = Depends(validate_patch_request),
    provider: EventProvider = Depends(get_event_provider),
) -> Event:
    """Partially update an existing event, preserving omitted fields."""
    return patch_event(event_id, changes, provider)
