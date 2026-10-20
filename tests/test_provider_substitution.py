"""Application and HTTP behavior with a controlled EventProvider."""

from collections.abc import Mapping
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.events import get_event, list_events
from app.main import app, get_event_provider
from app.models import CreateEventRequest, Event
from app.providers import EventProvider


@dataclass
class ControlledEventProvider:
    """Return configured events or service failures without external I/O."""

    outcomes: Mapping[str, Event | ServiceError]

    def get_event(self, event_id: str) -> Event:
        """Return or raise the configured outcome for the requested identifier."""
        outcome = self.outcomes[event_id]
        if isinstance(outcome, ServiceError):
            raise outcome
        return outcome

    def list_events(self, limit: int) -> list[Event]:
        return [self.get_event(event_id) for event_id in list(self.outcomes)[:limit]]

    def create_event(self, event: CreateEventRequest) -> Event:
        """Creation is outside this retrieval-focused controlled provider."""
        raise NotImplementedError


@pytest.fixture
def configured_events() -> dict[str, Event]:
    return {
        "Review_Event-001": Event(
            id="Review_Event-001",
            title="Design review",
            start="2026-10-13T09:00:00-04:00",
            end="2026-10-13T10:00:00-04:00",
        ),
        "event-002": Event(
            id="event-002",
            title="Planning session",
            start="2026-10-14T16:00:00+02:00",
            end="2026-10-14T16:30:00+02:00",
        ),
    }


@pytest.fixture
def controlled_provider(configured_events: dict[str, Event]) -> EventProvider:
    return ControlledEventProvider(configured_events)


@pytest.mark.parametrize("event_id", ["", "   ", "\t\n", "\r\n \t", "\u2003"])
def test_invalid_event_id_is_rejected_without_provider_call(event_id: str) -> None:
    class UnusedProvider:
        def get_event(self, event_id: str) -> Event:
            pytest.fail("Invalid input must not invoke the provider")

        def list_events(self, limit: int) -> list[Event]:
            pytest.fail("Invalid input must not invoke the provider")

        def create_event(self, event: CreateEventRequest) -> Event:
            pytest.fail("Retrieval validation must not create an event")

    with pytest.raises(InvalidInputError):
        get_event(event_id, provider=UnusedProvider())


@pytest.mark.parametrize(
    "event_id", ["abc123", " abc123 ", "\tabc123\n", "unusual:/?@!", "会議"]
)
def test_nonblank_event_id_is_passed_unchanged(
    event_id: str, configured_events: dict[str, Event]
) -> None:
    expected = configured_events["event-002"].model_copy(update={"id": event_id})
    provider = ControlledEventProvider({event_id: expected})

    assert get_event(event_id, provider=provider) is expected


@pytest.mark.parametrize("event_id", ["Review_Event-001", "event-002"])
def test_application_returns_configured_event(
    event_id: str,
    controlled_provider: EventProvider,
    configured_events: dict[str, Event],
) -> None:
    assert (
        get_event(event_id, provider=controlled_provider) == configured_events[event_id]
    )


def test_application_repeated_reads_preserve_events(
    controlled_provider: EventProvider,
    configured_events: dict[str, Event],
) -> None:
    before = {key: event.model_dump() for key, event in configured_events.items()}

    for event_id in ["Review_Event-001", "event-002", "Review_Event-001"]:
        assert (
            get_event(event_id, provider=controlled_provider).model_dump()
            == before[event_id]
        )

    assert {
        key: event.model_dump() for key, event in configured_events.items()
    } == before


@pytest.mark.parametrize("event_id", ["Review_Event-001", "event-002"])
def test_http_returns_configured_provider_event(
    event_id: str,
    controlled_provider: EventProvider,
    configured_events: dict[str, Event],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def supply_provider() -> EventProvider:
        return controlled_provider

    monkeypatch.setitem(app.dependency_overrides, get_event_provider, supply_provider)
    with TestClient(app) as client:
        response = client.get(f"/events/{event_id}")

    expected = configured_events[event_id]
    assert response.status_code == 200
    assert response.json() == {
        "id": expected.id,
        "title": expected.title,
        "start": expected.start,
        "end": expected.end,
    }


@pytest.mark.parametrize(
    ("error_type", "status", "code", "message"),
    [
        pytest.param(
            NotFoundError, 404, "not_found", "Event not found", id="not_found"
        ),
        pytest.param(
            PermissionDeniedError,
            403,
            "permission_denied",
            "Permission denied",
            id="permission_denied",
        ),
        pytest.param(
            ProviderFailureError,
            502,
            "provider_error",
            "Calendar provider request failed",
            id="provider_error",
        ),
    ],
)
def test_http_failures_do_not_affect_subsequent_retrieval(
    error_type: type[ServiceError],
    status: int,
    code: str,
    message: str,
    configured_events: dict[str, Event],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider: EventProvider = ControlledEventProvider(
        {**configured_events, "failing-event": error_type("synthetic internal context")}
    )
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    event_id = "Review_Event-001"
    event = configured_events[event_id]
    expected = {
        "id": event.id,
        "title": event.title,
        "start": event.start,
        "end": event.end,
    }

    with TestClient(app) as client:
        response = client.get(f"/events/{event_id}")
        assert response.status_code == 200
        assert response.json() == expected

        response = client.get("/events/%20%20%20")
        assert response.status_code == 400
        assert response.json() == {
            "error": {"code": "invalid_input", "message": "Invalid event ID"}
        }

        response = client.get("/events/failing-event")
        assert response.status_code == status
        assert response.json() == {"error": {"code": code, "message": message}}

        response = client.get(f"/events/{event_id}")
        assert response.status_code == 200
        assert response.json() == expected


@pytest.mark.parametrize(("limit", "expected_count"), [(None, 10), (1, 1), (100, 12)])
def test_http_lists_public_events_with_default_and_bounded_limits(
    limit: int | None,
    expected_count: int,
    configured_events: dict[str, Event],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = configured_events["event-002"]
    events = {
        f"event-{index}": template.model_copy(update={"id": f"event-{index}"})
        for index in range(12)
    }
    provider: EventProvider = ControlledEventProvider(events)
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    with TestClient(app) as client:
        response = client.get(
            "/events", params={} if limit is None else {"limit": limit}
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": f"event-{index}",
            "title": template.title,
            "start": template.start,
            "end": template.end,
        }
        for index in range(expected_count)
    ]


def test_http_list_of_empty_calendar_returns_empty_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider: EventProvider = ControlledEventProvider({})
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    with TestClient(app) as client:
        response = client.get("/events")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("limit", ["0", "101", "abc", "1.5", ""])
def test_http_invalid_list_limit_is_rejected_before_google_setup(
    limit: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_client() -> None:
        pytest.fail(
            "Invalid limits must not construct a client or contact the provider"
        )

    monkeypatch.setattr("app.main.build_google_calendar_client", unexpected_client)
    with TestClient(app) as client:
        response = client.get("/events", params={"limit": limit})
    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": "Invalid event limit"}
    }


@pytest.mark.parametrize("limit", [0, 101])
def test_application_rejects_invalid_list_limit(limit: int) -> None:
    with pytest.raises(InvalidInputError):
        list_events(limit, provider=ControlledEventProvider({}))


def test_http_list_provider_failure_uses_shared_response_and_operation_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider: EventProvider = ControlledEventProvider(
        {"failure": ProviderFailureError("synthetic private provider detail")}
    )
    monkeypatch.setitem(app.dependency_overrides, get_event_provider, lambda: provider)
    with TestClient(app) as client:
        response = client.get("/events")
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_error",
            "message": "Calendar provider request failed",
        }
    }
    records = [record for record in caplog.records if record.name == "app.http_errors"]
    assert len(records) == 1
    assert records[0].__dict__["operation"] == "list_events"
    assert "synthetic private provider detail" not in caplog.text
