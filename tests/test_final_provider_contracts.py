"""Issue #57: exercise the real composition with only the Google SDK controlled."""

from copy import deepcopy
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from httpx import Response as HTTPResponse
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]

import app.main as main
from app.event_cache import EventCache
from app.models import Event

BODY = {
    "title": " Meeting 会議 ",
    "start": "2026-10-22T10:00:00Z",
    "end": "2026-10-22T11:00:00Z",
}
RAW: dict[str, object] = {
    "id": "opaque-id",
    "summary": BODY["title"],
    "start": {"dateTime": BODY["start"]},
    "end": {"dateTime": BODY["end"]},
}
OPERATIONS = [
    ("GET", "get"),
    ("LIST", "list"),
    ("POST", "insert"),
    ("PUT", "update"),
    ("PATCH", "patch"),
]


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock()
    for name in ("get", "insert", "update", "patch"):
        getattr(
            client.events.return_value, name
        ).return_value.execute.return_value = deepcopy(RAW)
    client.events.return_value.list.return_value.execute.return_value = {
        "items": [deepcopy(RAW)]
    }
    monkeypatch.setattr(main, "build_google_calendar_client", lambda: client)
    monkeypatch.setattr(main, "event_cache", EventCache())
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "primary")
    return client.events.return_value


def request(operation: str) -> HTTPResponse:
    with TestClient(main.app, raise_server_exceptions=False) as client:
        if operation == "LIST":
            return client.get("/events")
        path = "/events" if operation == "POST" else "/events/opaque-id"
        if operation in ("POST", "PUT", "PATCH"):
            return client.request(operation, path, json=BODY)
        return client.request(operation, path)


@pytest.mark.parametrize("operation,sdk_method", OPERATIONS)
@pytest.mark.parametrize(
    "result", [None, [], "private-invalid", 42, {}, {"items": None}]
)
def test_malformed_sdk_response_is_sanitized_502(
    operation: str,
    sdk_method: str,
    result: object,
    sdk: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # An empty list response object is Google's valid empty page.
    if operation == "LIST" and result == {}:
        result = {"items": "invalid"}
    getattr(sdk, sdk_method).return_value.execute.return_value = result
    response = request(operation)
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_error",
            "message": "Calendar provider request failed",
        }
    }
    assert "private-invalid" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("operation,sdk_method", OPERATIONS)
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", ""),
        ("id", "   "),
        ("summary", None),
        ("summary", ""),
        ("summary", "   "),
        ("summary", 42),
        ("start", None),
        ("end", {}),
        ("start", {"date": "2026-10-22"}),
        ("start", {"dateTime": "not-a-time"}),
        ("end", {"dateTime": "2026-02-30T11:00:00Z"}),
        ("end", {"dateTime": BODY["start"]}),
    ],
)
def test_unsupported_provider_event_is_502(
    operation: str, sdk_method: str, field: str, value: object, sdk: Mock
) -> None:
    result = deepcopy(RAW)
    result[field] = value
    getattr(sdk, sdk_method).return_value.execute.return_value = (
        {"items": [result]} if operation == "LIST" else result
    )
    assert request(operation).status_code == 502


@pytest.mark.parametrize(
    "operation,sdk_method", [("GET", "get"), ("PUT", "update"), ("PATCH", "patch")]
)
def test_wrong_resource_identity_is_not_returned(
    operation: str, sdk_method: str, sdk: Mock
) -> None:
    getattr(sdk, sdk_method).return_value.execute.return_value = {
        **RAW,
        "id": "different-id",
    }
    assert request(operation).status_code == 502


@pytest.mark.parametrize(
    "method,changes",
    [
        ("PUT", BODY),
        ("PATCH", {"title": "New"}),
        ("PATCH", {"start": BODY["start"]}),
        ("PATCH", {"end": BODY["end"]}),
        ("PATCH", {"start": BODY["start"], "end": BODY["end"]}),
    ],
)
def test_cancelled_fresh_state_blocks_writes_even_with_cached_active_event(
    method: str, changes: dict[str, str], sdk: Mock
) -> None:
    main.event_cache.put("primary", "opaque-id", Event(id="opaque-id", **BODY))
    sdk.get.return_value.execute.return_value = {
        "id": "opaque-id",
        "status": "cancelled",
    }
    with TestClient(main.app) as client:
        response = client.request(method, "/events/opaque-id", json=changes)
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Event not found"}
    }
    sdk.get.assert_called_once_with(calendarId="primary", eventId="opaque-id")
    sdk.update.assert_not_called()
    sdk.patch.assert_not_called()


@pytest.mark.parametrize(
    "operation,sdk_method", [("PUT", "update"), ("PATCH", "patch")]
)
def test_cancelled_write_response_is_never_success(
    operation: str, sdk_method: str, sdk: Mock
) -> None:
    getattr(sdk, sdk_method).return_value.execute.return_value = {
        **RAW,
        "status": "cancelled",
    }
    assert request(operation).status_code == 404
    getattr(sdk, sdk_method).assert_called_once()


@pytest.mark.parametrize("operation,sdk_method", OPERATIONS + [("DELETE", "delete")])
@pytest.mark.parametrize(
    "status,expected", [(404, 404), (403, 403), (500, 502), (503, 502), (0, 502)]
)
def test_all_operations_keep_service_error_mapping(
    operation: str,
    sdk_method: str,
    status: int,
    expected: int,
    sdk: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = (
        HttpError(
            Response({"status": status}),
            json.dumps({"error": {"message": "private-provider-detail"}}).encode(),
        )
        if status
        else ConnectionError("private-provider-detail")
    )
    getattr(sdk, sdk_method).return_value.execute.side_effect = error
    response = request(operation)
    assert response.status_code == expected
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message"}
    assert "private-provider-detail" not in response.text + caplog.text


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize("status,expected", [(404, 404), (403, 403), (500, 502)])
def test_failed_preflight_never_attempts_write(
    method: str, status: int, expected: int, sdk: Mock
) -> None:
    sdk.get.return_value.execute.side_effect = HttpError(
        Response({"status": status}), b'{"error":{"message":"private"}}'
    )
    assert request(method).status_code == expected
    sdk.update.assert_not_called()
    sdk.patch.assert_not_called()


def test_one_sided_patch_rechecks_interval_against_fresh_provider_state(
    sdk: Mock,
) -> None:
    main.event_cache.put(
        "primary",
        "opaque-id",
        Event(id="opaque-id", **{**BODY, "end": "2026-10-22T13:00:00Z"}),
    )
    with TestClient(main.app) as client:
        response = client.patch(
            "/events/opaque-id", json={"start": "2026-10-22T12:00:00Z"}
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"
    sdk.patch.assert_not_called()


@pytest.mark.parametrize("result", [None, "", {}])
def test_delete_has_no_event_response_assumption(result: object, sdk: Mock) -> None:
    sdk.delete.return_value.execute.return_value = result
    response = request("DELETE")
    assert response.status_code == 204
    assert response.content == b""


def test_empty_google_list_page_is_valid(sdk: Mock) -> None:
    sdk.list.return_value.execute.return_value = {}
    response = request("LIST")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("operation,sdk_method", [("POST", "insert"), ("LIST", "list")])
def test_cancelled_creation_or_collection_item_is_unsupported(
    operation: str, sdk_method: str, sdk: Mock
) -> None:
    result = {**RAW, "status": "cancelled"}
    getattr(sdk, sdk_method).return_value.execute.return_value = (
        {"items": [result]} if operation == "LIST" else result
    )
    assert request(operation).status_code == 502
