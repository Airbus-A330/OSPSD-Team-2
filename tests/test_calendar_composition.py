"""Exercise configured Calendar composition with only the SDK controlled."""

from unittest.mock import Mock

import pytest
from calendar_contract import (
    CalendarError,
    CalendarService,
    CreateEvent,
    ErrorCode,
    Event,
)
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]

from app.composition import open_calendar_service
from app.errors import ProviderUnavailableError
from app.event_cache import EventCache


@pytest.fixture
def request_event() -> CreateEvent:
    return CreateEvent(
        title="  Composition meeting  ",
        start="2030-01-15T10:00:00Z",
        end="2030-01-15T10:30:00Z",
    )


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch, request_event: CreateEvent) -> Mock:
    client = Mock()
    client.events.return_value.insert.return_value.execute.return_value = {
        "id": "created-event",
        "summary": request_event.title,
        "start": {"dateTime": request_event.start},
        "end": {"dateTime": request_event.end},
    }
    monkeypatch.delenv("CALENDAR_IMPLEMENTATION", raising=False)
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "controlled-calendar")
    monkeypatch.setattr("app.composition.build_google_calendar_client", lambda: client)
    monkeypatch.setattr("app.composition.event_cache", EventCache())
    return client


def create_calendar_step(calendar: CalendarService, request: CreateEvent) -> Event:
    """A workflow step consumes only the shared interface and domain models."""
    return calendar.create(request)


@pytest.mark.parametrize("implementation", [None, "team2"])
def test_configured_calendar_creates_through_team2_provider(
    implementation: str | None,
    monkeypatch: pytest.MonkeyPatch,
    sdk: Mock,
    request_event: CreateEvent,
) -> None:
    if implementation is not None:
        monkeypatch.setenv("CALENDAR_IMPLEMENTATION", implementation)

    with open_calendar_service() as calendar:
        event = create_calendar_step(calendar, request_event)
        assert event == Event(id="created-event", **request_event.model_dump())
        sdk.close.assert_not_called()

    sdk.events.return_value.insert.assert_called_once_with(
        calendarId="controlled-calendar",
        body={
            "summary": request_event.title,
            "start": {"dateTime": request_event.start},
            "end": {"dateTime": request_event.end},
        },
    )
    sdk.close.assert_called_once_with()


@pytest.mark.parametrize("implementation", ["", "team7", " team2 "])
def test_invalid_selection_fails_before_client_construction(
    implementation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_client = Mock(side_effect=AssertionError("Must not construct a client"))
    monkeypatch.setattr("app.composition.build_google_calendar_client", build_client)
    monkeypatch.setenv("CALENDAR_IMPLEMENTATION", implementation)

    with pytest.raises(ValueError, match="^CALENDAR_IMPLEMENTATION must be team2$"):
        with open_calendar_service():
            pytest.fail("Invalid selection must not yield a service")

    build_client.assert_not_called()


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (403, ErrorCode.ACCESS_DENIED, False),
        (404, ErrorCode.NOT_FOUND, False),
        (429, ErrorCode.PROVIDER_UNAVAILABLE, True),
        (500, ErrorCode.PROVIDER_ERROR, False),
    ],
)
def test_calendar_step_propagates_shared_failure_and_closes_client(
    status: int,
    code: ErrorCode,
    retryable: bool,
    sdk: Mock,
    request_event: CreateEvent,
) -> None:
    execute = sdk.events.return_value.insert.return_value.execute
    execute.side_effect = HttpError(
        Response({"status": str(status)}), b'{"error":{"message":"private detail"}}'
    )

    with pytest.raises(CalendarError) as caught:
        with open_calendar_service() as calendar:
            create_calendar_step(calendar, request_event)

    assert caught.value.code is code
    assert caught.value.retryable is retryable
    assert "private detail" not in str(caught.value)
    execute.assert_called_once_with()
    sdk.close.assert_called_once_with()


def test_uncertain_create_is_not_repeated_or_rolled_back(
    sdk: Mock, request_event: CreateEvent
) -> None:
    records: list[CreateEvent] = []

    def create_then_lose_response() -> None:
        records.append(request_event)
        raise TimeoutError("Response lost after write")

    sdk.events.return_value.insert.return_value.execute.side_effect = (
        create_then_lose_response
    )

    with pytest.raises(CalendarError) as caught:
        with open_calendar_service() as calendar:
            create_calendar_step(calendar, request_event)

    assert caught.value.code is ErrorCode.PROVIDER_ERROR
    assert caught.value.retryable is False
    assert records == [request_event]
    sdk.events.return_value.delete.assert_not_called()
    sdk.close.assert_called_once_with()


def test_later_workflow_failure_preserves_created_event(
    sdk: Mock, request_event: CreateEvent
) -> None:
    later_failure = RuntimeError("Controlled later step failure")
    with pytest.raises(RuntimeError) as caught:
        with open_calendar_service() as calendar:
            event = create_calendar_step(calendar, request_event)
            raise later_failure

    assert caught.value is later_failure
    assert event == Event(id="created-event", **request_event.model_dump())
    sdk.events.return_value.insert.return_value.execute.assert_called_once_with()
    sdk.events.return_value.delete.assert_not_called()
    sdk.close.assert_called_once_with()


def test_direct_consumer_retains_id_validation(sdk: Mock) -> None:
    with pytest.raises(CalendarError) as caught:
        with open_calendar_service() as calendar:
            calendar.get(" \t\n")

    assert caught.value.code is ErrorCode.INVALID_INPUT
    sdk.events.assert_not_called()
    sdk.close.assert_called_once_with()


def test_setup_failure_propagates_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ProviderUnavailableError("Controlled authorization transport failure")
    build_client = Mock(side_effect=error)
    monkeypatch.setenv("CALENDAR_IMPLEMENTATION", "team2")
    monkeypatch.setattr("app.composition.build_google_calendar_client", build_client)

    with pytest.raises(CalendarError) as caught:
        with open_calendar_service():
            pytest.fail("Failed setup must not yield a service")

    assert caught.value is error
    build_client.assert_called_once_with()


def test_each_workflow_owns_a_separate_client(monkeypatch: pytest.MonkeyPatch) -> None:
    clients = [Mock(), Mock()]
    build_client = Mock(side_effect=clients)
    monkeypatch.setenv("CALENDAR_IMPLEMENTATION", "team2")
    monkeypatch.setattr("app.composition.build_google_calendar_client", build_client)

    for _ in clients:
        with open_calendar_service():
            pass

    assert build_client.call_count == 2
    for client in clients:
        client.close.assert_called_once_with()
