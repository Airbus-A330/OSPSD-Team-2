"""Google Calendar authentication, event operations, and translation."""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import HttpLib2Error  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.errors import (
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider

GOOGLE_CALENDAR_SCOPES = ("https://www.googleapis.com/auth/calendar.events",)
_TRANSPORT_ERRORS = (HttpLib2Error, TransportError, TimeoutError, ConnectionError)

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
        ProviderFailureError: If refreshing saved authorization fails because
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
                raise ProviderFailureError(
                    "Google authorization refresh failed"
                ) from None
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), GOOGLE_CALENDAR_SCOPES
            )
            try:
                credentials = flow.run_local_server(port=0)
            except _TRANSPORT_ERRORS:
                raise ProviderFailureError(
                    "Google authorization request failed"
                ) from None

        token_path.write_text(credentials.to_json(), encoding="utf-8")

    try:
        return build("calendar", "v3", credentials=credentials)
    except _TRANSPORT_ERRORS:
        raise ProviderFailureError("Google Calendar client setup failed") from None


def translate_google_event(provider_event: Mapping[str, Any]) -> Event:
    """Translate a titled, timed Google event without exposing its metadata.

    Args:
        provider_event: JSON response from the Google Calendar events API.

    Returns:
        The event's identifier, title, and unchanged dateTime strings.
    """
    return Event(
        id=provider_event["id"],
        title=provider_event["summary"],
        start=provider_event["start"]["dateTime"],
        end=provider_event["end"]["dateTime"],
    )


def get_event(client: Any, *, calendar_id: str, event_id: str) -> dict[str, object]:
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


def create_event(
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


def _translate_google_error(error: HttpError) -> ServiceError:
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
    return ProviderFailureError("Google Calendar request failed")


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
                raise NotFoundError(
                    "Google Calendar event is already deleted"
                ) from None
            raise _translate_google_error(error) from None
        except _TRANSPORT_ERRORS:
            raise ProviderFailureError("Google Calendar request failed") from None

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        """Send only caller-supplied changes using Google patch semantics."""
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
            raise _translate_google_error(error) from None
        except _TRANSPORT_ERRORS:
            raise ProviderFailureError("Google Calendar request failed") from None
        try:
            return translate_google_event(result)
        except (KeyError, TypeError, ValidationError):
            raise ProviderFailureError(
                "Invalid Google Calendar patch response"
            ) from None

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
            raise _translate_google_error(error) from None
        except _TRANSPORT_ERRORS:
            raise ProviderFailureError("Google Calendar request failed") from None
        try:
            return [
                translate_google_event(item)
                for item in response.get("items", [])[:limit]
            ]
        except (KeyError, TypeError, ValidationError):
            raise ProviderFailureError("Unsupported Google event data") from None

    def get_event(self, event_id: str) -> Event:
        """Retrieve a Google event and translate it into the domain model.

        Args:
            event_id: Identifier of the event to retrieve.

        Returns:
            The event in the service's public representation.

        Raises:
            NotFoundError: If Google reports that the event does not exist.
            PermissionDeniedError: If Google denies access to the event.
            ProviderFailureError: If another Google failure, a quota or
                rate-limit failure, or a transport failure prevents retrieval.
        """
        try:
            provider_event = get_event(
                self._client,
                calendar_id=self._calendar_id,
                event_id=event_id,
            )
        except HttpError as error:
            raise _translate_google_error(error) from None
        except _TRANSPORT_ERRORS:
            raise ProviderFailureError("Google Calendar request failed") from None
        if provider_event.get("status") == "cancelled":
            raise NotFoundError("Google Calendar event is cancelled")
        try:
            return translate_google_event(provider_event)
        except (KeyError, TypeError, ValidationError):
            raise ProviderFailureError(
                "Invalid Google Calendar retrieval response"
            ) from None

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
            provider_event = create_event(
                self._client,
                calendar_id=self._calendar_id,
                event=event,
            )
        except HttpError as error:
            raise _translate_google_error(error) from None
        except _TRANSPORT_ERRORS:
            raise ProviderFailureError("Google Calendar request failed") from None
        try:
            return translate_google_event(provider_event)
        except (KeyError, TypeError, ValidationError):
            raise ProviderFailureError(
                "Invalid Google Calendar creation response"
            ) from None

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        """Fully update an event using Google events.update, without retries.

        Google HTTP/transport failures use the existing service error mapping.
        A lost response can leave the write outcome unknown to the caller.
        """
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
            raise _translate_google_error(error) from None
        except _TRANSPORT_ERRORS:
            raise ProviderFailureError("Google Calendar request failed") from None
        try:
            return translate_google_event(provider_event)
        except (KeyError, TypeError, ValidationError):
            raise ProviderFailureError(
                "Invalid Google Calendar update response"
            ) from None
