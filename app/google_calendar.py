"""Google Calendar authentication and client construction."""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]

GOOGLE_CALENDAR_SCOPES = ("https://www.googleapis.com/auth/calendar.events.readonly",)


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
