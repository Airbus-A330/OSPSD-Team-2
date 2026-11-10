"""Run the complete tagged suite through Team 2 and a controlled Google SDK."""

from copy import deepcopy
from collections.abc import Iterator
from contextlib import ExitStack
from urllib.parse import quote
from unittest.mock import Mock

import pytest
from calendar_contract import (
    CalendarService,
    CalendarError,
    ErrorCode,
    Event,
    CreateEvent,
    ReplaceEvent,
)
from calendar_contract.conformance import (
    CalendarServiceConformance,
    FailingServiceFactory,
    ProviderFailure,
)
from fastapi.testclient import TestClient
from httpx import Response as HTTPResponse
from app.main import create_app
from app.composition import get_event_provider

from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]

from app.calendar_service import CalendarServiceAdapter
from app.event_cache import CachedEventProvider, EventCache
from app.google_calendar import GoogleCalendarProvider


def google_http_error(status: int) -> HttpError:
    return HttpError(Response({"status": str(status)}), b"{}")


@pytest.fixture
def sdk() -> Mock:
    """Keep provider state at the external SDK boundary, including tombstones."""
    client = Mock()
    records: dict[str, dict[str, object]] = {}
    next_id = 0

    def insert(*, calendarId: str, body: dict[str, object]) -> Mock:
        def execute() -> dict[str, object]:
            nonlocal next_id
            next_id += 1
            event_id = f"controlled-{next_id}"
            records[event_id] = {"id": event_id, **deepcopy(body)}
            return deepcopy(records[event_id])

        return Mock(execute=execute)

    def get(*, calendarId: str, eventId: str) -> Mock:
        def execute() -> dict[str, object]:
            if eventId not in records:
                raise google_http_error(404)
            return deepcopy(records[eventId])

        return Mock(execute=execute)

    def update(*, calendarId: str, eventId: str, body: dict[str, object]) -> Mock:
        def execute() -> dict[str, object]:
            if eventId not in records or records[eventId].get("status") == "cancelled":
                raise google_http_error(404)
            records[eventId] = {"id": eventId, **deepcopy(body)}
            return deepcopy(records[eventId])

        return Mock(execute=execute)

    def delete(*, calendarId: str, eventId: str) -> Mock:
        def execute() -> str:
            if eventId not in records or records[eventId].get("status") == "cancelled":
                raise google_http_error(404)
            records[eventId]["status"] = "cancelled"
            return ""

        return Mock(execute=execute)

    client.events.return_value.insert.side_effect = insert
    client.events.return_value.get.side_effect = get
    client.events.return_value.update.side_effect = update
    client.events.return_value.delete.side_effect = delete
    return client


class HTTPService:
    """Use the shared protocol over actual HTTP routes for upstream checks."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def _result(self, response: HTTPResponse, expected: int) -> Event | None:
        if response.is_error:
            payload = response.json()["error"]
            code = ErrorCode(payload["code"])
            assert (
                response.status_code
                == {
                    ErrorCode.INVALID_INPUT: 422,
                    ErrorCode.NOT_FOUND: 404,
                    ErrorCode.ACCESS_DENIED: 403,
                    ErrorCode.PROVIDER_ERROR: 502,
                    ErrorCode.PROVIDER_UNAVAILABLE: 503,
                }[code]
            )
            raise CalendarError(
                code=code, message=payload["message"], retryable=payload["retryable"]
            )
        assert response.status_code == expected
        if expected == 204:
            assert response.content == b""
            return None
        return Event.model_validate(response.json())

    def create(self, request: CreateEvent) -> Event:
        result = self._result(
            self.client.post("/events", json=request.model_dump()), 201
        )
        assert result is not None
        return result

    def get(self, event_id: str) -> Event:
        result = self._result(
            self.client.get("/events/" + quote(event_id, safe="")), 200
        )
        assert result is not None
        return result

    def replace(self, event_id: str, request: ReplaceEvent) -> Event:
        result = self._result(
            self.client.put(
                "/events/" + quote(event_id, safe=""), json=request.model_dump()
            ),
            200,
        )
        assert result is not None
        return result

    def delete(self, event_id: str) -> None:
        self._result(self.client.delete("/events/" + quote(event_id, safe="")), 204)


def controlled_service(sdk: Mock, boundary: str, stack: ExitStack) -> CalendarService:
    provider = CachedEventProvider(
        GoogleCalendarProvider(sdk, calendar_id="controlled"),
        cache=EventCache(),
        namespace="controlled",
    )
    if boundary == "python":
        return CalendarServiceAdapter(provider)
    application = create_app()
    application.dependency_overrides[get_event_provider] = lambda: provider
    return HTTPService(stack.enter_context(TestClient(application)))


@pytest.fixture(params=["python", "http"])
def boundary(request: pytest.FixtureRequest) -> str:
    return str(request.param)


class TestSharedCalendarConformance(CalendarServiceConformance):
    @pytest.fixture
    def service(self, sdk: Mock, boundary: str) -> Iterator[CalendarService]:
        with ExitStack() as stack:
            yield controlled_service(sdk, boundary, stack)

    @pytest.fixture
    def failing_service(self, boundary: str) -> Iterator[FailingServiceFactory]:
        with ExitStack() as stack:

            def build(failure: ProviderFailure) -> CalendarService:
                sdk = Mock()
                error: Exception
                if failure is ProviderFailure.ACCESS_DENIED:
                    error = google_http_error(403)
                elif failure is ProviderFailure.UNAVAILABLE:
                    # Quota rejection confirms refusal; a lost write response
                    # instead leaves remote state uncertain.
                    error = google_http_error(429)
                elif failure is ProviderFailure.UNCERTAIN_WRITE:
                    error = TimeoutError("synthetic lost write response")
                else:
                    error = google_http_error(418)
                for operation in ("get", "insert", "update", "delete"):
                    getattr(
                        sdk.events.return_value, operation
                    ).return_value.execute.side_effect = error
                if failure is ProviderFailure.UNCERTAIN_WRITE:
                    sdk.events.return_value.get.return_value.execute.side_effect = None
                    sdk.events.return_value.get.return_value.execute.return_value = {
                        "id": "conformance-event",
                        "summary": "Existing",
                        "start": {"dateTime": "2030-01-07T15:00:00Z"},
                        "end": {"dateTime": "2030-01-07T16:00:00Z"},
                    }
                return controlled_service(sdk, boundary, stack)

            yield build


@pytest.mark.parametrize(
    "method,sdk_method", [("POST", "insert"), ("PUT", "update"), ("DELETE", "delete")]
)
@pytest.mark.parametrize("status", [403, 429])
def test_confirmed_quota_rejection_is_unavailable_without_retry(
    method: str, sdk_method: str, status: int, sdk: Mock
) -> None:
    sdk.events.return_value.get.side_effect = None
    sdk.events.return_value.get.return_value.execute.return_value = {
        "id": "id",
        "summary": "Existing",
        "start": {"dateTime": "2030-01-07T15:00:00Z"},
        "end": {"dateTime": "2030-01-07T16:00:00Z"},
    }
    request = Mock()
    request.execute.side_effect = HttpError(
        Response({"status": str(status)}),
        b'{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}',
    )
    operation = getattr(sdk.events.return_value, sdk_method)
    operation.side_effect = None
    operation.return_value = request
    with ExitStack() as stack:
        service = controlled_service(sdk, "http", stack)
        with pytest.raises(CalendarError) as caught:
            if method == "POST":
                service.create(
                    CreateEvent(
                        title="Test",
                        start="2030-01-07T15:00:00Z",
                        end="2030-01-07T16:00:00Z",
                    )
                )
            elif method == "PUT":
                service.replace(
                    "id",
                    ReplaceEvent(
                        title="Test",
                        start="2030-01-07T15:00:00Z",
                        end="2030-01-07T16:00:00Z",
                    ),
                )
            else:
                service.delete("id")
    assert caught.value.code is ErrorCode.PROVIDER_UNAVAILABLE
    assert caught.value.retryable is True
    request.execute.assert_called_once_with()


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_lost_write_response_preserves_uncertainty_and_invalidates_cached_state(
    method: str, sdk: Mock
) -> None:
    original = CreateEvent(
        title="Original", start="2030-01-07T15:00:00Z", end="2030-01-07T16:00:00Z"
    )
    changed = ReplaceEvent(title="Changed", start=original.start, end=original.end)
    with ExitStack() as stack:
        service = controlled_service(sdk, "http", stack)
        if method == "PUT":
            event_id = service.create(original).id
            assert service.get(event_id).title == original.title
        else:
            event_id = "controlled-1"
        operation = (
            sdk.events.return_value.insert
            if method == "POST"
            else sdk.events.return_value.update
        )
        factory = operation.side_effect

        def lose_response(**kwargs: object) -> Mock:
            request = factory(**kwargs)

            def execute() -> None:
                request.execute()
                raise TimeoutError("response lost after mutation")

            return Mock(execute=execute)

        operation.side_effect = lose_response
        with pytest.raises(CalendarError) as caught:
            if method == "POST":
                service.create(original)
            else:
                service.replace(event_id, changed)
        assert caught.value.code is ErrorCode.PROVIDER_ERROR
        assert caught.value.retryable is False
        operation.assert_called_once()
        stored = service.get(event_id)
        assert stored.title == (original.title if method == "POST" else changed.title)
        service.delete(event_id)
