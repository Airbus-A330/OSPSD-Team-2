"""Provider-independent application behavior for calendar events."""

import re
from datetime import datetime

from app.errors import InvalidInputError
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider

_RFC3339_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


def validate_event_id(event_id: str) -> None:
    """Reject blank identifiers without changing any valid identifier."""
    if not event_id.strip():
        raise InvalidInputError("Event ID must contain a non-whitespace character")


def validate_event_limit(limit: int) -> None:
    """Reject listing limits outside the public 1–100 range."""
    if not 1 <= limit <= 100:
        raise InvalidInputError("Event limit must be between 1 and 100")


def list_events(limit: int, provider: EventProvider) -> list[Event]:
    """Read a bounded collection without changing provider state."""
    validate_event_limit(limit)
    return provider.list_events(limit)


def delete_event(event_id: str, provider: EventProvider) -> None:
    """Validate an event ID and delete it through the supplied provider.

    Args:
        event_id: Opaque identifier, preserved unchanged when nonblank.
        provider: Provider selected by the composition layer.

    Raises:
        InvalidInputError: If the identifier is empty or whitespace-only.
        NotFoundError: If the provider reports a missing event.
        PermissionDeniedError: If the provider denies deletion.
        ProviderFailureError: If deletion cannot be confirmed.
    """
    validate_event_id(event_id)
    provider.delete_event(event_id)


def get_event(event_id: str, provider: EventProvider) -> Event:
    """Retrieve an event from the configured calendar.

    The provider dependency is supplied by composition code outside the application
    layer so that concrete provider selection remains explicit and testable.

    Args:
        event_id: Event identifier requested by the caller.
        provider: EventProvider implementation selected by the composition layer.

    Returns:
        The event in the service's public representation.

    Raises:
        InvalidInputError: If event_id is empty or whitespace-only.
    """
    validate_event_id(event_id)
    return provider.get_event(event_id)


def _parse_event_time(value: str, field_name: str) -> datetime:
    """Parse one RFC3339-compatible timestamp with a required UTC offset."""
    if not _RFC3339_TIMESTAMP.fullmatch(value):
        raise InvalidInputError(f"{field_name} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise InvalidInputError(f"{field_name} must be a valid timestamp") from None
    if parsed.utcoffset() is None:
        raise InvalidInputError(f"{field_name} must include a UTC offset")
    return parsed


def validate_create_event(event: CreateEventRequest) -> None:
    """Validate locally checkable create constraints before a provider write."""
    if not event.title.strip():
        raise InvalidInputError("Event title must contain non-whitespace content")

    start = _parse_event_time(event.start, "Event start")
    end = _parse_event_time(event.end, "Event end")
    if end <= start:
        raise InvalidInputError("Event end must be after its start")


def create_event(event: CreateEventRequest, provider: EventProvider) -> Event:
    """Validate and create an event through the configured provider.

    Args:
        event: Provider-independent values for the event to create.
        provider: EventProvider implementation selected by composition code.

    Returns:
        The created event, including its provider-generated identifier.

    Raises:
        InvalidInputError: If the title or timed-event boundaries are invalid.
    """
    validate_create_event(event)
    return provider.create_event(event)


def replace_event(
    event_id: str, replacement: EventReplacement, provider: EventProvider
) -> Event:
    """Replace an existing event's complete editable representation.

    The replacement model validates title and interval before any provider write.
    Shared service failures propagate to the HTTP boundary without retries.
    """
    validate_event_id(event_id)
    return provider.replace_event(event_id, replacement)


def validate_event_patch(changes: EventPatch) -> None:
    """Reject locally invalid supplied values before provider setup or writes."""
    if changes.title is not None and not changes.title.strip():
        raise InvalidInputError("Event title must contain non-whitespace content")
    start = (
        _parse_event_time(changes.start, "Event start")
        if changes.start is not None
        else None
    )
    end = (
        _parse_event_time(changes.end, "Event end") if changes.end is not None else None
    )
    if start is not None and end is not None and end <= start:
        raise InvalidInputError("Event end must be after its start")


def patch_event(event_id: str, changes: EventPatch, provider: EventProvider) -> Event:
    """Apply only supplied changes, checking a single time against stored state.

    A single supplied time requires one read before the write. This is not an
    atomic comparison: concurrent changes and uncertain write outcomes remain
    the provider's responsibility. No automatic retries are performed.
    """
    validate_event_id(event_id)
    validate_event_patch(changes)
    if (changes.start is None) != (changes.end is None):
        current = provider.get_event(event_id)
        start = _parse_event_time(
            changes.start if changes.start is not None else current.start, "Event start"
        )
        end = _parse_event_time(
            changes.end if changes.end is not None else current.end, "Event end"
        )
        if end <= start:
            raise InvalidInputError("Event end must be after its start")
    return provider.patch_event(event_id, changes)
