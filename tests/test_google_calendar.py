"""Credential-free tests for Google Calendar authentication and retrieval."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]

from app.google_calendar import (
    GOOGLE_CALENDAR_SCOPES,
    build_google_calendar_client,
    get_event,
)


@patch("app.google_calendar.build")
@patch("app.google_calendar.Credentials.from_authorized_user_file")
def test_build_client_uses_valid_saved_credentials(
    load_credentials: MagicMock,
    build: MagicMock,
    monkeypatch,
    tmp_path: Path,
) -> None:
    credentials_path = tmp_path / "client.json"
    token_path = tmp_path / "saved-token.json"
    token_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", str(credentials_path))
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_FILE", str(token_path))
    credentials = MagicMock(valid=True)
    load_credentials.return_value = credentials
    expected_client = MagicMock()
    build.return_value = expected_client

    client = build_google_calendar_client()

    assert client is expected_client
    load_credentials.assert_called_once_with(str(token_path), GOOGLE_CALENDAR_SCOPES)
    build.assert_called_once_with("calendar", "v3", credentials=credentials)


@patch("app.google_calendar.Request")
@patch("app.google_calendar.build")
@patch("app.google_calendar.Credentials.from_authorized_user_file")
def test_build_client_refreshes_expired_credentials(
    load_credentials: MagicMock,
    build: MagicMock,
    request: MagicMock,
    monkeypatch,
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_FILE", str(token_path))
    credentials = MagicMock(
        valid=False,
        expired=True,
        refresh_token="refresh-token",
    )
    credentials.to_json.return_value = '{"token": "new-token"}'
    load_credentials.return_value = credentials

    build_google_calendar_client()

    credentials.refresh.assert_called_once_with(request.return_value)
    assert token_path.read_text(encoding="utf-8") == '{"token": "new-token"}'


@patch("app.google_calendar.InstalledAppFlow.from_client_secrets_file")
@patch("app.google_calendar.build")
def test_build_client_runs_oauth_flow_without_saved_credentials(
    build: MagicMock,
    create_flow: MagicMock,
    monkeypatch,
    tmp_path: Path,
) -> None:
    credentials_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    monkeypatch.setenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", str(credentials_path))
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_FILE", str(token_path))
    credentials = MagicMock(valid=True)
    credentials.to_json.return_value = '{"token": "new-token"}'
    create_flow.return_value.run_local_server.return_value = credentials

    build_google_calendar_client()

    create_flow.assert_called_once_with(str(credentials_path), GOOGLE_CALENDAR_SCOPES)
    create_flow.return_value.run_local_server.assert_called_once_with(port=0)
    assert token_path.read_text(encoding="utf-8") == '{"token": "new-token"}'


@pytest.mark.parametrize("calendar_id", ["primary", "team@group.calendar.google.com"])
def test_get_event_passes_identifiers_to_google(calendar_id: str) -> None:
    client = Mock()

    get_event(client, calendar_id=calendar_id, event_id="event123")

    client.events.return_value.get.assert_called_once_with(
        calendarId=calendar_id, eventId="event123"
    )
    client.events.return_value.get.return_value.execute.assert_called_once_with()


def test_get_event_returns_raw_result_for_translation() -> None:
    client = Mock()
    provider_event = {
        "id": "event123",
        "summary": "Team meeting",
        "start": {"dateTime": "2026-10-07T10:00:00-04:00"},
        "end": {"dateTime": "2026-10-07T11:00:00-04:00"},
        "etag": '"provider-version"',
    }
    client.events.return_value.get.return_value.execute.return_value = provider_event

    result = get_event(client, calendar_id="primary", event_id="event123")

    assert result == provider_event


def test_get_event_propagates_provider_failure() -> None:
    client = Mock()
    error = HttpError(Response({"status": "404"}), b'{"error": "Not Found"}')
    client.events.return_value.get.return_value.execute.side_effect = error

    with pytest.raises(HttpError) as caught:
        get_event(client, calendar_id="primary", event_id="missing123")

    assert caught.value is error
