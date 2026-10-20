"""Test the Google provider boundary with a controlled SDK client."""

import json
from typing import Any
from unittest.mock import Mock

import pytest
from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import HttpLib2Error, Response  # type: ignore[import-untyped]

from app.errors import (
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.google_calendar import GoogleCalendarProvider
from app.models import Event, EventReplacement


@pytest.mark.parametrize(
    ("calendar_id", "event_id"),
    [("primary", "event123"), ("team@group.calendar.google.com", "Review_Event-002")],
)
def test_provider_queries_configured_calendar_and_returns_domain_event(
    calendar_id: str, event_id: str
) -> None:
    """Use the supplied identifiers and return only the public event fields."""
    client = Mock()
    request = client.events.return_value.get.return_value
    request.execute.return_value = {
        "id": event_id,
        "summary": "Team review",
        "start": {"dateTime": "2026-10-14T09:00:00.123+05:30"},
        "end": {"dateTime": "2026-10-14T10:00:00.123+05:30"},
        "etag": '"provider-only"',
        "organizer": {"email": "organizer@example.com"},
    }

    provider = GoogleCalendarProvider(client, calendar_id=calendar_id)
    assert client.mock_calls == []

    result = provider.get_event(event_id)

    client.events.return_value.get.assert_called_once_with(
        calendarId=calendar_id, eventId=event_id
    )
    request.execute.assert_called_once_with()
    assert isinstance(result, Event)
    assert result.model_dump() == {
        "id": event_id,
        "title": "Team review",
        "start": "2026-10-14T09:00:00.123+05:30",
        "end": "2026-10-14T10:00:00.123+05:30",
    }


def _google_http_error(status: str, reason: str | None) -> HttpError:
    """Build an HttpError with Google's structured error response shape."""
    detail: dict[str, Any] = {"code": int(status), "message": "provider-only detail"}
    if reason is not None:
        domain = (
            "usageLimits"
            if reason in {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
            else "global"
        )
        detail["errors"] = [
            {"domain": domain, "reason": reason, "message": "provider-only detail"}
        ]
    return HttpError(
        Response({"status": status, "content-type": "application/json"}),
        json.dumps({"error": detail}).encode(),
    )


@pytest.mark.parametrize(
    ("status", "reason", "service_error"),
    [
        ("404", "notFound", NotFoundError),
        ("403", "forbidden", PermissionDeniedError),
        ("403", None, PermissionDeniedError),
        ("403", "rateLimitExceeded", ProviderFailureError),
        ("403", "userRateLimitExceeded", ProviderFailureError),
        ("403", "quotaExceeded", ProviderFailureError),
        ("429", "rateLimitExceeded", ProviderFailureError),
        ("400", None, ProviderFailureError),
        ("500", "backendError", ProviderFailureError),
    ],
)
def test_provider_translates_google_failure(
    status: str, reason: str | None, service_error: type[ServiceError]
) -> None:
    """Map Google HTTP failures to service errors at the provider boundary."""
    client = Mock()
    error = _google_http_error(status, reason)
    client.events.return_value.get.return_value.execute.side_effect = error
    provider = GoogleCalendarProvider(client, calendar_id="primary")

    with pytest.raises(service_error) as caught:
        provider.get_event("event123")

    assert isinstance(caught.value, ServiceError)
    assert not isinstance(caught.value, HttpError)
    assert "provider-only detail" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "transport_error",
    [
        HttpLib2Error("provider-only detail"),
        TransportError("provider-only detail"),
    ],
    ids=["httplib2", "google_auth"],
)
def test_provider_translates_transport_failure(transport_error: Exception) -> None:
    """Map documented transport failures to ProviderFailureError."""
    client = Mock()
    client.events.return_value.get.return_value.execute.side_effect = transport_error
    provider = GoogleCalendarProvider(client, calendar_id="primary")

    with pytest.raises(ProviderFailureError) as caught:
        provider.get_event("event123")

    assert isinstance(caught.value, ServiceError)
    assert "provider-only detail" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_provider_does_not_return_untranslatable_google_data() -> None:
    """Keep the existing failure for all-day events without dateTime fields."""
    client = Mock()
    client.events.return_value.get.return_value.execute.return_value = {
        "id": "all-day123",
        "summary": "All-day event",
        "start": {"date": "2026-10-14"},
        "end": {"date": "2026-10-15"},
    }
    provider = GoogleCalendarProvider(client, calendar_id="primary")

    with pytest.raises(KeyError, match="dateTime"):
        provider.get_event("all-day123")


def test_replace_uses_full_update_and_translates_result() -> None:
    client = Mock()
    replacement = EventReplacement(
        title="New title", start="2026-10-20T10:00:00Z", end="2026-10-20T11:00:00Z"
    )
    request = client.events.return_value.update.return_value
    request.execute.return_value = {
        "id": "opaque-id",
        "summary": "New title",
        "start": {"dateTime": replacement.start},
        "end": {"dateTime": replacement.end},
        "etag": "hidden",
    }
    provider = GoogleCalendarProvider(client, calendar_id="team-calendar")
    assert provider.replace_event("opaque-id", replacement) == Event(
        id="opaque-id", **replacement.model_dump()
    )
    client.events.return_value.update.assert_called_once_with(
        calendarId="team-calendar",
        eventId="opaque-id",
        body={
            "summary": replacement.title,
            "start": {"dateTime": replacement.start},
            "end": {"dateTime": replacement.end},
        },
    )
    request.execute.assert_called_once_with()
    client.events.return_value.patch.assert_not_called()
    client.events.return_value.get.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_google_http_error("404", "notFound"), NotFoundError),
        (_google_http_error("403", "forbidden"), PermissionDeniedError),
        (_google_http_error("403", "rateLimitExceeded"), ProviderFailureError),
        (_google_http_error("500", "backendError"), ProviderFailureError),
        (TransportError("private detail"), ProviderFailureError),
        (HttpLib2Error("private detail"), ProviderFailureError),
    ],
)
def test_replace_translates_failures_without_retry(
    error: Exception,
    expected: type[ServiceError],
) -> None:
    client = Mock()
    request = client.events.return_value.update.return_value
    request.execute.side_effect = error
    provider = GoogleCalendarProvider(client, calendar_id="primary")
    replacement = EventReplacement(
        title="New title", start="2026-10-20T10:00:00Z", end="2026-10-20T11:00:00Z"
    )
    with pytest.raises(expected) as caught:
        provider.replace_event("event-id", replacement)
    assert caught.value.__cause__ is None
    assert "private detail" not in str(caught.value)
    assert "provider-only detail" not in str(caught.value)
    request.execute.assert_called_once_with()


def test_replace_malformed_provider_result_is_provider_failure() -> None:
    client = Mock()
    client.events.return_value.update.return_value.execute.return_value = {
        "id": "event-id"
    }
    provider = GoogleCalendarProvider(client, calendar_id="primary")
    replacement = EventReplacement(
        title="New title", start="2026-10-20T10:00:00Z", end="2026-10-20T11:00:00Z"
    )
    with pytest.raises(ProviderFailureError):
        provider.replace_event("event-id", replacement)
