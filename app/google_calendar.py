"""Google Calendar authentication, event retrieval, and translation."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]

from app.models import Event

GOOGLE_CALENDAR_SCOPES = ("https://www.googleapis.com/auth/calendar.events.readonly",)


class EventProvider(Protocol):
    """Provider-independent interface for event retrieval.

    Application code depends on this protocol, not on concrete provider
    implementations. The GoogleCalendarProvider satisfies this contract.
    """

    def get_event(self, event_id: str) -> Event: ...


class GoogleCalendarProvider:
    """Concrete provider that implements EventProvider using Google Calendar SDK.

    Responsible for:
    - Google Calendar SDK client construction and authentication
    - Provider-specific event retrieval
    - Translating provider responses into the service's domain Event model

    Google-specific types and SDK calls remain encapsulated behind this boundary.
    """

    def __init__(self, calendar_id: str | None = None) -> None:
        configured_calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
        self.calendar_id: str = (
            calendar_id
            if calendar_id is not None
            else configured_calendar_id or "primary"
        )

    def get_event(self, event_id: str) -> Event:
        """Retrieve and translate a Google Calendar event.

        Args:
            event_id: Google Calendar event identifier.

        Returns:
            The event in the service's public representation.
        """
        client = build_google_calendar_client()
        provider_event = get_event(
            client,
            calendar_id=self.calendar_id,
            event_id=event_id,
        )
        return translate_google_event(provider_event)


def build_google_calendar_client() -> Resource:
    """Build an authenticated Google Calendar API client.

    Credential and token paths can be configured with the
    ``GOOGLE_CALENDAR_CREDENTIALS_FILE`` and ``GOOGLE_CALENDAR_TOKEN_FILE``
    environment variables. They default to ``credentials.json`` and
    ``token.json`` in the current working directory.

    Returns:
        An authenticated Google Calendar v3 client.
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
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), GOOGLE_CALENDAR_SCOPES
            )
            credentials = flow.run_local_server(port=0)

        token_path.write_text(credentials.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=credentials)


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


class GoogleCalendarProvider:
    """Retrieve domain events through a configured Google Calendar client."""

    def __init__(self, client: Resource, *, calendar_id: str) -> None:
        """Store the client and calendar configuration without performing I/O."""
        self._client = client
        self._calendar_id = calendar_id

    def get_event(self, event_id: str) -> Event:
        """Retrieve a Google event and translate it into the domain model.

        Args:
            event_id: Identifier of the event to retrieve.

        Returns:
            The event in the service's public representation.
        """
        provider_event = get_event(
            self._client,
            calendar_id=self._calendar_id,
            event_id=event_id,
        )
        return translate_google_event(provider_event)
