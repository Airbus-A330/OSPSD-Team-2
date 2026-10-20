"""Deterministic behavior tests for successful event retrieval caching."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)
from app.event_cache import CachedEventProvider, EventCache
from app.events import get_event
from app.main import app, get_event_provider
from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
from app.providers import EventProvider


@dataclass
class ControlledProvider:
    """Return a configurable outcome and record provider calls."""

    outcome: Event | ServiceError
    calls: list[str] = field(default_factory=list)

    def get_event(self, event_id: str) -> Event:
        self.calls.append(event_id)
        if isinstance(self.outcome, ServiceError):
            raise self.outcome
        return self.outcome

    def list_events(self, limit: int) -> list[Event]:
        raise AssertionError("Retrieval cache tests must not list events")

    def create_event(self, event: CreateEventRequest) -> Event:
        raise AssertionError("Retrieval cache tests must not create events")

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        raise AssertionError("Retrieval cache tests must not replace events")

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        raise AssertionError("Retrieval cache tests must not patch events")

    def delete_event(self, event_id: str) -> None:
        raise AssertionError("Retrieval cache tests must not delete events")


@pytest.fixture
def event() -> Event:
    return Event(
        id="event-123",
        title="Cached event",
        start="2026-10-19T09:00:00-04:00",
        end="2026-10-19T10:00:00-04:00",
    )


def test_cache_miss_then_hit_calls_provider_once(event: Event) -> None:
    provider = ControlledProvider(event)
    cached_provider = CachedEventProvider(
        provider,
        cache=EventCache(),
        namespace="primary",
    )

    assert cached_provider.get_event(event.id) == event
    assert cached_provider.get_event(event.id) == event
    assert provider.calls == [event.id]


def test_expired_entry_is_refreshed_without_sleeping(event: Event) -> None:
    current_time = 0.0
    cache = EventCache(ttl_seconds=60.0, clock=lambda: current_time)
    provider = ControlledProvider(event)
    cached_provider = CachedEventProvider(
        provider,
        cache=cache,
        namespace="primary",
    )

    assert cached_provider.get_event(event.id) == event
    current_time = 59.9
    assert cached_provider.get_event(event.id) == event

    refreshed_event = event.model_copy(update={"title": "Refreshed event"})
    provider.outcome = refreshed_event
    current_time = 60.0
    assert cached_provider.get_event(event.id) == refreshed_event
    assert provider.calls == [event.id, event.id]


def test_same_event_id_is_cached_separately_per_calendar(event: Event) -> None:
    cache = EventCache()
    primary_provider = ControlledProvider(event)
    team_event = event.model_copy(update={"title": "Team calendar event"})
    team_provider = ControlledProvider(team_event)
    cached_primary = CachedEventProvider(
        primary_provider,
        cache=cache,
        namespace="primary",
    )
    cached_team = CachedEventProvider(
        team_provider,
        cache=cache,
        namespace="team@example.com",
    )

    assert cached_primary.get_event(event.id) == event
    assert cached_team.get_event(event.id) == team_event
    assert primary_provider.calls == [event.id]
    assert team_provider.calls == [event.id]


def test_cache_evicts_oldest_entry_when_capacity_is_reached(event: Event) -> None:
    cache = EventCache(max_entries=2)
    second_event = event.model_copy(update={"id": "event-456"})
    third_event = event.model_copy(update={"id": "event-789"})

    cache.put("primary", event.id, event)
    cache.put("primary", second_event.id, second_event)
    cache.put("primary", third_event.id, third_event)

    assert cache.get("primary", event.id) is None
    assert cache.get("primary", second_event.id) == second_event
    assert cache.get("primary", third_event.id) == third_event


@pytest.mark.parametrize("max_entries", [0, -1])
def test_cache_rejects_nonpositive_capacity(max_entries: int) -> None:
    with pytest.raises(ValueError, match="max_entries must be at least 1"):
        EventCache(max_entries=max_entries)


@pytest.mark.parametrize(
    "error",
    [NotFoundError(), PermissionDeniedError(), ProviderFailureError()],
)
def test_service_failures_are_not_cached(error: ServiceError) -> None:
    provider = ControlledProvider(error)
    cached_provider = CachedEventProvider(
        provider,
        cache=EventCache(),
        namespace="primary",
    )

    for _ in range(2):
        with pytest.raises(type(error)):
            cached_provider.get_event("event-123")

    assert provider.calls == ["event-123", "event-123"]


def test_invalid_input_is_rejected_before_cache_or_provider(event: Event) -> None:
    provider = ControlledProvider(event)
    cached_provider = CachedEventProvider(
        provider,
        cache=EventCache(),
        namespace="primary",
    )

    for _ in range(2):
        with pytest.raises(InvalidInputError):
            get_event("   ", provider=cached_provider)

    assert provider.calls == []


def test_create_caches_returned_event(event: Event) -> None:
    provider = MagicMock(spec=EventProvider)
    provider.create_event.return_value = event
    cached_provider = CachedEventProvider(
        provider,
        cache=EventCache(),
        namespace="primary",
    )
    request = CreateEventRequest(title=event.title, start=event.start, end=event.end)

    assert cached_provider.create_event(request) == event
    assert cached_provider.get_event(event.id) == event
    provider.create_event.assert_called_once_with(request)
    provider.get_event.assert_not_called()


def test_replace_refreshes_cached_event(event: Event) -> None:
    provider = MagicMock(spec=EventProvider)
    replacement = EventReplacement(
        title="Replacement",
        start=event.start,
        end=event.end,
    )
    replaced = event.model_copy(update={"title": replacement.title})
    provider.replace_event.return_value = replaced
    cache = EventCache()
    cache.put("primary", event.id, event)
    cached_provider = CachedEventProvider(
        provider,
        cache=cache,
        namespace="primary",
    )

    assert cached_provider.replace_event(event.id, replacement) == replaced
    assert cached_provider.get_event(event.id) == replaced
    provider.get_event.assert_not_called()


def test_patch_refreshes_cached_event(event: Event) -> None:
    provider = MagicMock(spec=EventProvider)
    changes = EventPatch(title="Patched")
    patched = event.model_copy(update={"title": changes.title})
    provider.patch_event.return_value = patched
    cache = EventCache()
    cache.put("primary", event.id, event)
    cached_provider = CachedEventProvider(
        provider,
        cache=cache,
        namespace="primary",
    )

    assert cached_provider.patch_event(event.id, changes) == patched
    assert cached_provider.get_event(event.id) == patched
    provider.get_event.assert_not_called()


def test_failed_delete_does_not_leave_stale_cached_event(event: Event) -> None:
    provider = MagicMock(spec=EventProvider)
    provider.delete_event.side_effect = ProviderFailureError("lost response")
    provider.get_event.side_effect = NotFoundError()
    cache = EventCache()
    cache.put("primary", event.id, event)
    cached_provider = CachedEventProvider(
        provider,
        cache=cache,
        namespace="primary",
    )

    with pytest.raises(ProviderFailureError):
        cached_provider.delete_event(event.id)
    with pytest.raises(NotFoundError):
        cached_provider.get_event(event.id)

    provider.delete_event.assert_called_once_with(event.id)
    provider.get_event.assert_called_once_with(event.id)


def test_listing_bypasses_single_event_cache(event: Event) -> None:
    provider = MagicMock(spec=EventProvider)
    provider.list_events.return_value = [event]
    cached_provider = CachedEventProvider(
        provider,
        cache=EventCache(),
        namespace="primary",
    )

    assert cached_provider.list_events(10) == [event]
    provider.list_events.assert_called_once_with(10)


def test_repeated_http_requests_return_cached_public_event(
    event: Event, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = ControlledProvider(event)
    cached_provider = CachedEventProvider(
        provider,
        cache=EventCache(),
        namespace="primary",
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        get_event_provider,
        lambda: cached_provider,
    )

    with TestClient(app) as client:
        first_response = client.get(f"/events/{event.id}")
        second_response = client.get(f"/events/{event.id}")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json() == event.model_dump()
    assert second_response.json() == event.model_dump()
    assert provider.calls == [event.id]


def test_production_composition_reuses_cache_across_requests(
    event: Event, monkeypatch: pytest.MonkeyPatch
) -> None:
    google_clients = [MagicMock(), MagicMock()]
    for google_client in google_clients:
        google_client.events.return_value.get.return_value.execute.return_value = {
            "id": event.id,
            "summary": event.title,
            "start": {"dateTime": event.start},
            "end": {"dateTime": event.end},
        }
    build_client = MagicMock(side_effect=google_clients)
    monkeypatch.setattr("app.main.build_google_calendar_client", build_client)
    monkeypatch.setattr("app.main.event_cache", EventCache())
    monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)

    with TestClient(app) as client:
        first_response = client.get(f"/events/{event.id}")
        second_response = client.get(f"/events/{event.id}")

    assert first_response.json() == event.model_dump()
    assert second_response.json() == event.model_dump()
    assert build_client.call_count == 2
    google_clients[0].events.return_value.get.assert_called_once_with(
        calendarId="primary", eventId=event.id
    )
    google_clients[1].events.return_value.get.assert_not_called()
    for google_client in google_clients:
        google_client.close.assert_called_once_with()
