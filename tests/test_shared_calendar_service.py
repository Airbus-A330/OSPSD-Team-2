"""Verify the shared GET consumer path with controlled provider boundaries."""

from unittest.mock import Mock

import pytest
from calendar_contract import (
    CalendarError,
    CalendarService,
    CreateEvent,
    ErrorCode,
    Event,
    ReplaceEvent,
)
from calendar_contract.conformance import CREATE, CalendarServiceConformance
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]

from app.calendar_service import CalendarServiceAdapter
from app.composition import get_calendar_service
from app.errors import ProviderFailureError
from app.google_calendar import GoogleCalendarProvider
from app.main import create_app
from app.models import CreateEventRequest, EventReplacement
from app.providers import EventProvider


class TestSharedGetConformance:
    """Reuse upstream GET cases, seeding SDK state without create/delete calls."""

    test_get_returns_created_event = (
        CalendarServiceConformance.test_get_returns_created_event
    )
    test_get_missing_event_raises_not_found = (
        CalendarServiceConformance.test_get_missing_event_raises_not_found
    )

    @pytest.fixture
    def sdk(self) -> Mock:
        return Mock()

    @pytest.fixture
    def service(self, sdk: Mock) -> CalendarService:
        return CalendarServiceAdapter(GoogleCalendarProvider(sdk, calendar_id="test"))

    @pytest.fixture
    def created(self, sdk: Mock) -> Event:
        sdk.events.return_value.get.return_value.execute.return_value = {
            "id": "seeded-event",
            "summary": CREATE["title"],
            "start": {"dateTime": CREATE["start"]},
            "end": {"dateTime": CREATE["end"]},
        }
        return Event(id="seeded-event", **CREATE)

    @pytest.fixture
    def missing_id(self, sdk: Mock) -> str:
        sdk.events.return_value.get.return_value.execute.side_effect = HttpError(
            Response({"status": "404"}), b"{}"
        )
        return "missing-event"


def test_http_get_accepts_a_shared_service_without_local_provider_methods() -> None:
    """A shared-only implementation can replace the entire production GET path."""
    service = Mock(spec=CalendarService)
    event = Event(id="opaque-id", **CREATE)
    service.get.return_value = event
    application = create_app()
    application.dependency_overrides[get_calendar_service] = lambda: service

    with TestClient(application) as client:
        response = client.get("/events/opaque-id")

    assert response.status_code == 200
    assert response.json() == event.model_dump()
    service.get.assert_called_once_with("opaque-id")


def test_non_http_get_validates_before_calling_provider() -> None:
    provider = Mock(spec=EventProvider)
    service: CalendarService = CalendarServiceAdapter(provider)

    with pytest.raises(CalendarError) as caught:
        service.get("  ")

    assert caught.value.code is ErrorCode.INVALID_INPUT
    assert caught.value.retryable is False
    provider.get_event.assert_not_called()


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (403, ErrorCode.ACCESS_DENIED, False),
        (429, ErrorCode.PROVIDER_UNAVAILABLE, True),
        (500, ErrorCode.PROVIDER_UNAVAILABLE, True),
    ],
)
def test_shared_get_preserves_translated_provider_failures(
    status: int, code: ErrorCode, retryable: bool
) -> None:
    sdk = Mock()
    sdk.events.return_value.get.return_value.execute.side_effect = HttpError(
        Response({"status": str(status)}), b"{}"
    )
    service: CalendarService = CalendarServiceAdapter(
        GoogleCalendarProvider(sdk, calendar_id="test")
    )

    with pytest.raises(CalendarError) as caught:
        service.get("opaque-id")

    assert caught.value.code is code
    assert caught.value.retryable is retryable
    sdk.events.return_value.get.return_value.execute.assert_called_once_with()


def test_other_shared_methods_bridge_existing_operations() -> None:
    provider = Mock(spec=EventProvider)
    event = Event(id="opaque-id", **CREATE)
    provider.create_event.return_value = event
    provider.replace_event.return_value = event
    service: CalendarService = CalendarServiceAdapter(provider)

    assert service.create(CreateEvent(**CREATE)) == event
    assert service.replace(event.id, ReplaceEvent(**CREATE)) == event
    service.delete(event.id)

    provider.create_event.assert_called_once_with(CreateEventRequest(**CREATE))
    provider.replace_event.assert_called_once_with(event.id, EventReplacement(**CREATE))
    provider.delete_event.assert_called_once_with(event.id)


@pytest.mark.parametrize("operation", ["create", "replace"])
def test_adapter_never_retries_uncertain_writes(operation: str) -> None:
    provider = Mock(spec=EventProvider)
    error = ProviderFailureError("synthetic uncertain outcome")
    method = getattr(provider, f"{operation}_event")
    method.side_effect = error
    service: CalendarService = CalendarServiceAdapter(provider)

    with pytest.raises(CalendarError) as caught:
        if operation == "create":
            service.create(CreateEvent(**CREATE))
        else:
            service.replace("opaque-id", ReplaceEvent(**CREATE))

    assert caught.value is error
    assert caught.value.retryable is False
    assert method.call_count == 1
