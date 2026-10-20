"""Application and HTTP behavior for creating timed calendar events."""

import logging
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from app.errors import PermissionDeniedError, ProviderFailureError, ServiceError
from app.events import create_event
from app.main import app, get_event_provider
from app.models import CreateEventRequest, Event, EventReplacement


@dataclass
class ControlledCreateProvider:
    """Record create attempts and return or raise one configured outcome."""

    outcome: Event | ServiceError
    created: list[CreateEventRequest] = field(default_factory=list)

    def get_event(self, event_id: str) -> Event:
        raise NotImplementedError

    def list_events(self, limit: int) -> list[Event]:
        raise NotImplementedError

    def create_event(self, event: CreateEventRequest) -> Event:
        self.created.append(event)
        if isinstance(self.outcome, ServiceError):
            raise self.outcome
        return self.outcome

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        raise NotImplementedError


@pytest.fixture
def create_request() -> CreateEventRequest:
    return CreateEventRequest(
        title=" Team planning ",
        start="2026-10-20T09:00:00-04:00",
        end="2026-10-20T10:00:00-04:00",
    )


@pytest.fixture
def created_event(create_request: CreateEventRequest) -> Event:
    return Event(id="created-123", **create_request.model_dump())


def test_application_creates_event_with_provider_generated_id(
    create_request: CreateEventRequest, created_event: Event
) -> None:
    provider = ControlledCreateProvider(created_event)

    result = create_event(create_request, provider)

    assert result == created_event
    assert provider.created == [create_request]


def test_http_create_returns_created_event_and_records_effect(
    create_request: CreateEventRequest,
    created_event: Event,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ControlledCreateProvider(created_event)
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)

    with TestClient(app) as client:
        response = client.post("/events", json=create_request.model_dump())

    assert response.status_code == 201
    assert response.json() == created_event.model_dump()
    assert provider.created == [create_request]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "title": "   ",
            "start": "2026-10-20T09:00:00-04:00",
            "end": "2026-10-20T10:00:00-04:00",
        },
        {
            "title": "Meeting",
            "start": "2026-10-20T09:00:00-04:00",
            "end": "2026-10-20T09:00:00-04:00",
        },
        {
            "title": "Meeting",
            "start": "2026-10-20T09:00:00",
            "end": "2026-10-20T10:00:00",
        },
        {
            "title": "Meeting",
            "start": "not-a-timestamp",
            "end": "2026-10-20T10:00:00-04:00",
        },
        {
            "title": "Meeting",
            "start": "2026-10-22T10:00:00+00:60",
            "end": "2026-10-22T11:00:00+00:60",
        },
    ],
    ids=[
        "blank_title",
        "end_not_after_start",
        "missing_offsets",
        "invalid_start",
        "invalid_offset",
    ],
)
def test_invalid_create_is_rejected_before_provider_write(
    payload: dict[str, str],
    created_event: Event,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ControlledCreateProvider(created_event)
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)

    with TestClient(app) as client:
        response = client.post("/events", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": "Invalid event data"}
    }
    assert provider.created == []


def test_missing_create_field_is_rejected_before_client_construction(
    create_request: CreateEventRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory_calls: list[None] = []

    def unavailable_client() -> None:
        factory_calls.append(None)
        raise ProviderFailureError("synthetic provider setup failure")

    monkeypatch.setattr("app.main.build_google_calendar_client", unavailable_client)
    payload = create_request.model_dump()
    del payload["title"]

    with TestClient(app) as client:
        response = client.post("/events", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": "Invalid event data"}
    }
    assert factory_calls == []


@pytest.mark.parametrize("missing_field", ["title", "start", "end"])
def test_create_requires_each_request_field_before_provider_write(
    missing_field: str,
    create_request: CreateEventRequest,
    created_event: Event,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ControlledCreateProvider(created_event)
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    payload = create_request.model_dump()
    del payload[missing_field]

    with TestClient(app) as client:
        response = client.post("/events", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": "Invalid event data"}
    }
    assert provider.created == []


@pytest.mark.parametrize(
    ("error", "status", "code", "message"),
    [
        (
            PermissionDeniedError("private provider detail"),
            403,
            "permission_denied",
            "Permission denied",
        ),
        (
            ProviderFailureError("private provider detail"),
            502,
            "provider_error",
            "Calendar provider request failed",
        ),
    ],
)
def test_http_create_renders_provider_failures(
    error: ServiceError,
    status: int,
    code: str,
    message: str,
    create_request: CreateEventRequest,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = ControlledCreateProvider(error)
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)

    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.post("/events", json=create_request.model_dump())

    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}
    assert provider.created == [create_request]
    assert "private provider detail" not in response.text
    records = [record for record in caplog.records if record.name == "app.http_errors"]
    assert len(records) == 1
    assert records[0].__dict__["operation"] == "create_event"
    assert records[0].__dict__["provider_involved"] is True
    assert "private provider detail" not in caplog.text
