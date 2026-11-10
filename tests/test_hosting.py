"""Credential-free deployment lifecycle and persistent authorization checks."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError, TransportError

from app import credential_store, google_calendar
from app.composition import get_calendar_service
from app.errors import ProviderFailureError, ProviderUnavailableError
from app.hosting import StartupConfigurationError, create_hosted_app, prepare_runtime

# Synthetic test fixtures only; these cannot authorize any Google account.
TOKEN_INFO = {
    "client_id": "test-client",
    "client_secret": "test-secret",
    "refresh_token": "test-refresh",
    "token": "test-access",
    "token_uri": "https://oauth2.googleapis.com/token",
    "expiry": "2000-01-01T00:00:00Z",
}
API_TOKEN = "test-only-deployment-key-" + "x" * 32


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "token.json"
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "primary")
    monkeypatch.setenv("CALENDAR_API_TOKEN", API_TOKEN)
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_FILE", str(path))
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_JSON", json.dumps(TOKEN_INFO))
    monkeypatch.setenv("GOOGLE_CALENDAR_NONINTERACTIVE", "1")
    return path


@pytest.mark.parametrize(
    "key",
    [
        "GOOGLE_CALENDAR_ID",
        "CALENDAR_API_TOKEN",
        "GOOGLE_CALENDAR_TOKEN_FILE",
        "GOOGLE_CALENDAR_TOKEN_JSON",
    ],
)
def test_missing_runtime_configuration_fails_at_startup(runtime, monkeypatch, key):
    monkeypatch.delenv(key)
    with pytest.raises(StartupConfigurationError):
        with TestClient(create_hosted_app()):
            pass


@pytest.mark.parametrize(
    "payload",
    [
        "not-json-private-detail",
        "[]",
        "{}",
        '{"refresh_token": "private-detail"}',
        '{"expiry": "private-detail"}',
    ],
)
def test_invalid_authorization_is_sanitized(runtime, monkeypatch, payload):
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_JSON", payload)
    with pytest.raises(StartupConfigurationError) as caught:
        prepare_runtime()
    assert payload not in str(caught.value)
    assert "private-detail" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert not runtime.exists()


def test_seed_is_private_and_never_overwrites_refreshed_state(runtime, monkeypatch):
    prepare_runtime()
    if os.name != "nt":
        assert runtime.stat().st_mode & 0o777 == 0o600
    updated = dict(TOKEN_INFO, refresh_token="new-test-refresh")
    runtime.write_text(json.dumps(updated))
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_JSON", "invalid-old-seed")
    prepare_runtime()
    assert json.loads(runtime.read_text()) == updated


def test_unwritable_or_missing_token_directory_fails_safely(runtime, monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_CALENDAR_TOKEN_FILE", str(runtime.parent / "missing" / "token.json")
    )
    with pytest.raises(StartupConfigurationError):
        prepare_runtime()


def test_readiness_does_not_depend_on_provider_availability(runtime):
    application = create_hosted_app()
    provider = Mock()
    provider.get.side_effect = ProviderUnavailableError("Google unavailable")
    application.dependency_overrides[get_calendar_service] = lambda: provider
    with TestClient(application) as client:
        assert client.get("/readyz").status_code == 200
        provider.get.assert_not_called()
        response = client.get(
            "/events/event123", headers={"Authorization": f"Bearer {API_TOKEN}"}
        )
        assert response.status_code == 503
        assert client.get("/readyz").json() == {"status": "ready"}
        assert client.get("/healthz").status_code == 200
    assert application.state.ready is False
    assert application.state.api_token == ""


def test_hosted_api_is_protected_but_local_app_is_unchanged(runtime):
    application = create_hosted_app()
    with TestClient(application) as client:
        for path in ("/events/test", "/docs", "/openapi.json"):
            assert client.get(path).status_code == 403
            assert (
                client.get(path, headers={"Authorization": "Bearer wrong"}).status_code
                == 403
            )
        assert (
            client.get(
                "/openapi.json", headers={"Authorization": f"Bearer {API_TOKEN}"}
            ).status_code
            == 200
        )
    from app.main import create_app

    assert TestClient(create_app()).get("/openapi.json").status_code == 200


def test_hosted_missing_token_never_opens_a_browser(runtime, monkeypatch):
    authorize = Mock()
    monkeypatch.setattr(
        google_calendar.InstalledAppFlow, "from_client_secrets_file", authorize
    )
    with pytest.raises(ProviderFailureError, match="operator setup"):
        google_calendar.build_google_calendar_client()
    authorize.assert_not_called()


def test_concurrent_refresh_reloads_persisted_token_once(runtime, monkeypatch):
    prepare_runtime()
    calls = []

    def refresh(credentials, request):
        calls.append(1)
        credentials.token = "updated-test-access"
        from datetime import datetime, timedelta, timezone

        credentials.expiry = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) + timedelta(hours=1)

    monkeypatch.setattr(credential_store.Credentials, "refresh", refresh)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: credential_store.load_hosted_credentials(
                    runtime, google_calendar.GOOGLE_CALENDAR_SCOPES
                ),
                range(4),
            )
        )
    assert len(calls) == 1
    assert all(result.token == "updated-test-access" for result in results)
    assert json.loads(runtime.read_text())["token"] == "updated-test-access"
    if os.name != "nt":
        assert runtime.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "error", [RefreshError("private-secret"), TransportError("private-secret")]
)
def test_hosted_refresh_failure_preserves_state_and_is_sanitized(
    runtime, monkeypatch, error
):
    prepare_runtime()
    before = runtime.read_text()
    monkeypatch.setattr(
        credential_store.Credentials, "refresh", Mock(side_effect=error)
    )
    expected = (
        ProviderUnavailableError
        if isinstance(error, TransportError)
        else ProviderFailureError
    )
    with pytest.raises(expected) as caught:
        google_calendar.build_google_calendar_client()
    assert "private-secret" not in str(caught.value)
    assert runtime.read_text() == before


def test_failed_atomic_write_preserves_previous_token(runtime, monkeypatch):
    prepare_runtime()
    before = runtime.read_text()
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("test failure")))
    with pytest.raises(OSError):
        credential_store.write_token_atomically(runtime, "replacement")
    assert runtime.read_text() == before
    assert list(runtime.parent.iterdir()) == [runtime]


def test_sdk_refresh_persists_and_stale_client_reuses_new_token(runtime, monkeypatch):
    from datetime import datetime, timedelta, timezone

    info = dict(TOKEN_INFO, expiry="2099-01-01T00:00:00Z")
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_JSON", json.dumps(info))
    prepare_runtime()
    first = credential_store.load_hosted_credentials(
        runtime, google_calendar.GOOGLE_CALENDAR_SCOPES
    )
    stale = credential_store.load_hosted_credentials(
        runtime, google_calendar.GOOGLE_CALENDAR_SCOPES
    )
    refreshed = []

    def refresh(credentials, request):
        refreshed.append(1)
        credentials.token = "sdk-refreshed-test-token"
        credentials.expiry = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) + timedelta(hours=1)

    monkeypatch.setattr(credential_store.Credentials, "refresh", refresh)
    first.refresh(Mock())  # The SDK can invoke this on a 401 after client creation.
    stale.refresh(Mock())
    assert refreshed == [1]
    assert first.token == stale.token == "sdk-refreshed-test-token"
    assert json.loads(runtime.read_text())["token"] == first.token
