"""Google Calendar authentication, event operations, and translation."""

import json
import logging
import os
import ssl
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Never

from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import HttpLib2Error  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ProviderUnavailableError,
    ServiceError,
)
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider

GOOGLE_CALENDAR_SCOPES = ("https://www.googleapis.com/auth/calendar.events",)
_TRANSPORT_ERRORS = (
    HttpLib2Error,
    TransportError,
    TimeoutError,
    ConnectionError,
    ssl.SSLError,
)
logger = logging.getLogger(__name__)

# Machine-readable Google error reasons that report a quota or rate limit
# rather than a permission failure. Google returns them with HTTP 403 (and
# rateLimitExceeded also with 429); see the Calendar API error guide.
_LIMIT_REASONS = frozenset(
    {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
)


def build_google_calendar_client() -> Resource:
    """Build an authenticated Google Calendar API client.

    Credential and token paths can be configured with the
    ``GOOGLE_CALENDAR_CREDENTIALS_FILE`` and ``GOOGLE_CALENDAR_TOKEN_FILE``
    environment variables. They default to ``credentials.json`` and
    ``token.json`` in the current working directory.

    Returns:
        An authenticated Google Calendar v3 client.

    Raises:
        ProviderUnavailableError: If refreshing saved authorization fails because
            the authentication provider cannot be reached.
    """
    credentials_path = Path(
        os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "credentials.json")
    )
    token_path = Path(os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "token.json"))

    credentials: Credentials | None = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_path), GOOGLE_CALENDAR_SCOPES
        )

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except _TRANSPORT_ERRORS:
                _raise_transport_failure(
                    "refresh_credentials",
                    "Google authorization refresh failed",
                    retryable=True,
                )
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), GOOGLE_CALENDAR_SCOPES
            )
            try:
                credentials = flow.run_local_server(port=0)
            except _TRANSPORT_ERRORS:
                _raise_transport_failure(
                    "authorize_credentials",
                    "Google authorization request failed",
                    retryable=True,
                )

        token_path.write_text(credentials.to_json(), encoding="utf-8")

    try:
        return build("calendar", "v3", credentials=credentials)
    except _TRANSPORT_ERRORS:
        _raise_transport_failure(
            "build_calendar_client",
            "Google Calendar client setup failed",
            retryable=True,
        )


def translate_google_event(provider_event: Mapping[str, Any]) -> Event:
    """Translate a timed Google event without exposing its metadata.

    Args:
        provider_event: JSON response from the Google Calendar events API.

    Returns:
        The event's identifier, title, and unchanged dateTime strings.
    """
    return Event(
        id=provider_event["id"],
        title=provider_event.get("summary", ""),
        start=provider_event["start"]["dateTime"],
        end=provider_event["end"]["dateTime"],
    )


def _validated_google_event(value: object, *, event_id: str | None = None) -> Event:
    """Reject unsupported success data and never expose a cancelled resource."""
    if not isinstance(value, Mapping):
        raise ProviderFailureError("Invalid Google Calendar event response")
    if event_id is not None and value.get("id") != event_id:
        raise ProviderFailureError("Unexpected Google Calendar event identifier")
    if value.get("status") == "cancelled":
        if event_id is not None:
            raise NotFoundError("Google Calendar event is cancelled")
        raise ProviderFailureError("Unsupported cancelled Google Calendar event")
    try:
        event = translate_google_event(value)
    except (KeyError, TypeError, ValidationError):
        raise ProviderFailureError("Unsupported Google Calendar event data") from None
    if not event.id.strip():
        raise ProviderFailureError("Unexpected Google Calendar event identifier")
    return event


def execute_google_event_get(
    client: Any, *, calendar_id: str, event_id: str
) -> dict[str, object]:
    """Read one event using an already configured Google Calendar v3 client.

    Args:
        client: Authenticated client owned and configured by the caller. Uses
            Any because the SDK generates service methods dynamically.
        calendar_id: Google calendar identifier, or ``primary`` for the
            authenticated user's primary calendar. No default is selected here.
        event_id: Google event ID within that calendar, not an iCalendar UID.

    Returns:
        Raw Google event data for the translation boundary, not an HTTP response.

    Raises:
        googleapiclient.errors.HttpError: If Google rejects the request.
            Transport failures also propagate to the caller.
    """
    return client.events().get(calendarId=calendar_id, eventId=event_id).execute()


def execute_google_event_insert(
    client: Any, *, calendar_id: str, event: CreateEventRequest
) -> dict[str, object]:
    """Create one timed Google Calendar event using domain request values.

    Args:
        client: Authenticated client owned and configured by the caller.
        calendar_id: Google calendar identifier, or ``primary``.
        event: Provider-independent event creation request.

    Returns:
        Raw Google event data for translation inside this module.
    """
    body = {
        "summary": event.title,
        "start": {"dateTime": event.start},
        "end": {"dateTime": event.end},
    }
    return client.events().insert(calendarId=calendar_id, body=body).execute()


def _google_error_reasons(error: HttpError) -> set[str]:
    """Extract Google's machine-readable error reasons from a failure body.

    Args:
        error: The HTTP failure raised by the Google Calendar SDK.

    Returns:
        The ``reason`` values from the structured error response, or an
        empty set when the body has no structured reasons.
    """
    try:
        payload = json.loads(error.content)
    except (TypeError, ValueError):
        return set()
    if not isinstance(payload, dict):
        return set()
    detail = payload.get("error")
    if not isinstance(detail, dict):
        return set()
    entries = detail.get("errors")
    if not isinstance(entries, list):
        return set()
    reasons: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict):
            reason = entry.get("reason")
            if isinstance(reason, str):
                reasons.add(reason)
    return reasons


def _translate_google_error(
    error: HttpError, *, retryable_read: bool = False
) -> ServiceError:
    """Translate a Google HTTP failure into the matching service error.

    Classification uses the response status and, for 403, Google's
    machine-readable error reasons: Google also returns 403 for quota and
    rate-limit failures, and those are provider failures, not permission
    failures. Human-readable messages never cross the provider boundary.

    Args:
        error: The HTTP failure raised by the Google Calendar SDK.

    Returns:
        The service error defined by the Level 5 contract for the failure.
    """
    if error.status_code == 404:
        return NotFoundError("Google Calendar reported that the event does not exist")
    if error.status_code == 403 and not (_google_error_reasons(error) & _LIMIT_REASONS):
        return PermissionDeniedError("Google Calendar denied access to the event")
    if retryable_read and (
        error.status_code == 429
        or error.status_code >= 500
        or bool(_google_error_reasons(error) & _LIMIT_REASONS)
    ):
        return ProviderUnavailableError("Google Calendar is temporarily unavailable")
    return ProviderFailureError("Google Calendar request failed")


def _raise_google_http_error(
    operation: str, error: HttpError, *, retryable_read: bool = False
) -> Never:
    """Log safe Google HTTP context and raise its service-level translation."""
    logger.warning(
        "Google Calendar operation failed: operation=%s status=%s",
        operation,
        error.status_code,
        extra={
            "provider_operation": operation,
            "provider_status": error.status_code,
        },
    )
    raise _translate_google_error(error, retryable_read=retryable_read) from None


def _raise_transport_failure(
    operation: str, message: str, *, retryable: bool = False
) -> Never:
    """Log a transport category without exposing exception or request data."""
    logger.warning(
        "Google Calendar transport failed: operation=%s",
        operation,
        extra={"provider_operation": operation},
    )
    if retryable:
        raise ProviderUnavailableError(message) from None
    raise ProviderFailureError(message) from None


def _validated_operation_result(
    operation: str, value: object, *, event_id: str | None = None
) -> Event:
    """Validate a Google success payload and log safe context on rejection."""
    try:
        return _validated_google_event(value, event_id=event_id)
    except (NotFoundError, ProviderFailureError):
        logger.warning(
            "Google Calendar response rejected: operation=%s",
            operation,
            extra={"provider_operation": operation},
        )
        raise


class GoogleCalendarProvider(EventProvider):
    """Perform domain event operations through a Google Calendar client."""

    def __init__(self, client: Resource, *, calendar_id: str) -> None:
        """Store the client and calendar configuration without performing I/O."""
        self._client = client
        self._calendar_id = calendar_id

    def delete_event(self, event_id: str) -> None:
        """Delete one event using Google events.delete, without retries.

        Args:
            event_id: Unchanged identifier within the configured calendar.

        Raises:
            NotFoundError: If Google reports a missing or already deleted event.
            PermissionDeniedError: If Google denies access.
            ProviderFailureError: If another Google or transport failure occurs.
                A lost response may leave the deletion outcome uncertain.
        """
        try:
            self._client.events().delete(
                calendarId=self._calendar_id, eventId=event_id
            ).execute()
        except HttpError as error:
            if error.status_code == 410 and "deleted" in _google_error_reasons(error):
                logger.warning(
                    "Google Calendar operation failed: operation=delete status=%s",
                    error.status_code,
                    extra={
                        "provider_operation": "delete",
                        "provider_status": error.status_code,
                    },
                )
                raise NotFoundError(
                    "Google Calendar event is already deleted"
                ) from None
            _raise_google_http_error("delete", error)
        except _TRANSPORT_ERRORS:
            _raise_transport_failure("delete", "Google Calendar request failed")

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        """Check fresh existence, then send only supplied fields using patch.

        The preflight bypasses application caches. It is not atomic with the
        subsequent Google mutation, so concurrent external changes can race it.
        """
        current = self.get_event(event_id)
        if (changes.start is None) != (changes.end is None):
            # Application validation may have read cached state. Recheck the
            # resulting interval against this fresh preflight before writing.
            try:
                Event(
                    id=current.id,
                    title=current.title,
                    start=changes.start if changes.start is not None else current.start,
                    end=changes.end if changes.end is not None else current.end,
                )
            except ValidationError:
                raise InvalidInputError("Event end must be after start") from None
        body: dict[str, object] = {}
        if changes.title is not None:
            body["summary"] = changes.title
        if changes.start is not None:
            body["start"] = {"dateTime": changes.start}
        if changes.end is not None:
            body["end"] = {"dateTime": changes.end}
        try:
            result = (
                self._client.events()
                .patch(
                    calendarId=self._calendar_id,
                    eventId=event_id,
                    body=body,
                )
                .execute()
            )
        except HttpError as error:
            _raise_google_http_error("patch", error)
        except _TRANSPORT_ERRORS:
            _raise_transport_failure("patch", "Google Calendar request failed")
        return _validated_operation_result("patch", result, event_id=event_id)

    def list_events(self, limit: int) -> list[Event]:
        """Read one bounded page of titled, timed events as domain values.

        Recurrences are expanded. No page token or provider metadata escapes;
        unsupported event shapes and provider failures use service errors.
        """
        try:
            response = (
                self._client.events()
                .list(calendarId=self._calendar_id, maxResults=limit, singleEvents=True)
                .execute()
            )
        except HttpError as error:
            _raise_google_http_error("list", error)
        except _TRANSPORT_ERRORS:
            _raise_transport_failure("list", "Google Calendar request failed")
        if not isinstance(response, Mapping):
            raise ProviderFailureError("Invalid Google Calendar list response")
        items = response.get("items", [])
        if not isinstance(items, list):
            raise ProviderFailureError("Invalid Google Calendar list items")
        return [_validated_operation_result("list", item) for item in items[:limit]]

    def get_event(self, event_id: str) -> Event:
        """Retrieve a Google event and translate it into the domain model.

        Args:
            event_id: Identifier of the event to retrieve.

        Returns:
            The event in the service's public representation.

        Raises:
            NotFoundError: If Google reports that the event does not exist.
            PermissionDeniedError: If Google denies access to the event.
            ProviderUnavailableError: If a quota, rate-limit, server, or
                transport failure temporarily prevents retrieval.
            ProviderFailureError: If Google rejects the request for another
                reason or returns unsupported event data.
        """
        try:
            provider_event = execute_google_event_get(
                self._client,
                calendar_id=self._calendar_id,
                event_id=event_id,
            )
        except HttpError as error:
            _raise_google_http_error("get", error, retryable_read=True)
        except _TRANSPORT_ERRORS:
            _raise_transport_failure(
                "get", "Google Calendar request failed", retryable=True
            )
        return _validated_operation_result("get", provider_event, event_id=event_id)

    def create_event(self, event: CreateEventRequest) -> Event:
        """Create a Google event and return its translated domain representation.

        Args:
            event: Provider-independent event creation request.

        Returns:
            The created event with its Google-generated identifier.

        Raises:
            PermissionDeniedError: If Google denies the event creation.
            ProviderFailureError: If another Google or transport failure occurs.
        """
        try:
            provider_event = execute_google_event_insert(
                self._client,
                calendar_id=self._calendar_id,
                event=event,
            )
        except HttpError as error:
            _raise_google_http_error("insert", error)
        except _TRANSPORT_ERRORS:
            _raise_transport_failure("insert", "Google Calendar request failed")
        return _validated_operation_result("insert", provider_event)

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        """Fully update an event using Google events.update, without retries.

        Google HTTP/transport failures use the existing service error mapping.
        A fresh read rejects missing/cancelled events before mutation. This is
        not atomic with the write; concurrent external changes remain possible.
        A lost response can leave the write outcome unknown to the caller.
        """
        self.get_event(event_id)
        try:
            provider_event = (
                self._client.events()
                .update(
                    calendarId=self._calendar_id,
                    eventId=event_id,
                    body={
                        "summary": replacement.title,
                        "start": {"dateTime": replacement.start},
                        "end": {"dateTime": replacement.end},
                    },
                )
                .execute()
            )
        except HttpError as error:
            _raise_google_http_error("update", error)
        except _TRANSPORT_ERRORS:
            _raise_transport_failure("update", "Google Calendar request failed")
        return _validated_operation_result("update", provider_event, event_id=event_id)
