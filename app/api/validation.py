"""FastAPI dependencies that reject invalid input before provider setup."""

from fastapi import Body, Request
from pydantic import TypeAdapter, ValidationError

from app.errors import InvalidInputError
from app.events import (
    validate_create_event,
    validate_event_id,
    validate_event_limit,
    validate_event_patch,
)
from app.models import CreateEventRequest, EventPatch, EventReplacement


def validate_delete_request(event_id: str) -> None:
    """Reject blank delete identifiers before provider construction."""
    try:
        validate_event_id(event_id)
    except InvalidInputError as error:
        error.public_message = "Invalid event ID"
        error.provider_involved = False
        raise


def validate_get_request(event_id: str) -> str:
    """Return a validated opaque identifier before provider construction."""
    try:
        validate_event_id(event_id)
    except InvalidInputError as error:
        error.public_message = "Invalid event ID"
        error.provider_involved = False
        raise
    return event_id


def validate_list_request(request: Request) -> None:
    """Reject malformed or out-of-range limits before provider construction."""
    try:
        raw_limit = request.query_params.get("limit", "10")
        if "." in raw_limit:
            raise InvalidInputError("Event limit must be an integer")
        limit = TypeAdapter(int).validate_python(raw_limit)
        validate_event_limit(limit)
    except (InvalidInputError, ValidationError) as error:
        if isinstance(error, InvalidInputError):
            error.public_message = "Invalid event limit"
            error.provider_involved = False
            raise
        raise InvalidInputError(
            "Event limit must be an integer",
            public_message="Invalid event limit",
            provider_involved=False,
        ) from None


def validate_create_request(
    body: object = Body(
        default=None, json_schema_extra=CreateEventRequest.model_json_schema()
    ),
) -> CreateEventRequest:
    """Validate a create body before resolving the provider dependency."""
    try:
        event = CreateEventRequest.model_validate(body)
        validate_create_event(event)
    except (InvalidInputError, ValidationError) as error:
        if isinstance(error, InvalidInputError):
            error.public_message = "Invalid event data"
            error.provider_involved = False
            raise
        raise InvalidInputError(
            "Invalid event data",
            public_message="Invalid event data",
            provider_involved=False,
        ) from None
    return event


def validate_replacement_request(
    event_id: str,
    body: object = Body(
        default=None, json_schema_extra=EventReplacement.model_json_schema()
    ),
) -> EventReplacement:
    """Validate a complete replacement before provider construction."""
    try:
        validate_event_id(event_id)
    except InvalidInputError as error:
        error.public_message = "Invalid event ID"
        error.provider_involved = False
        raise
    try:
        return EventReplacement.model_validate(body)
    except ValidationError:
        raise InvalidInputError(
            "Invalid event replacement",
            public_message="Invalid event replacement",
            provider_involved=False,
        ) from None


def validate_patch_request(
    event_id: str,
    body: object = Body(default=None, json_schema_extra=EventPatch.model_json_schema()),
) -> EventPatch:
    """Validate partial changes before provider construction."""
    try:
        validate_event_id(event_id)
    except InvalidInputError as error:
        error.public_message = "Invalid event ID"
        error.provider_involved = False
        raise
    try:
        changes = EventPatch.model_validate(body)
        validate_event_patch(changes)
    except (InvalidInputError, ValidationError) as error:
        if isinstance(error, InvalidInputError):
            error.public_message = "Invalid input"
            error.provider_involved = False
            raise
        raise InvalidInputError(
            "Invalid event patch",
            public_message="Invalid input",
            provider_involved=False,
        ) from None
    return changes
