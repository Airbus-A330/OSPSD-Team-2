"""Instrument existing CRUD routes through the real Google provider boundary."""

import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
    NumberDataPoint,
)
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from app.event_cache import EventCache
from app.main import app
from app.telemetry.runtime import Telemetry

REQUEST_BODY = {
    "title": "SECRET synthetic Calendar content",
    "start": "2026-11-01T10:00:00Z",
    "end": "2026-11-01T11:00:00Z",
}


@pytest.fixture
def google_client() -> Mock:
    """Supply valid SDK results while keeping all actual provider code active."""
    raw = {
        "id": "private-id",
        "summary": REQUEST_BODY["title"],
        "start": {"dateTime": REQUEST_BODY["start"]},
        "end": {"dateTime": REQUEST_BODY["end"]},
    }
    sdk = Mock()
    for name in ("get", "insert", "update"):
        getattr(sdk.events.return_value, name).return_value.execute.return_value = raw
    sdk.events.return_value.delete.return_value.execute.return_value = ""
    return sdk


@pytest.mark.parametrize(
    "method,operation,sdk_method,success_status",
    [
        ("POST", "Create", "insert", 201),
        ("GET", "Get", "get", 200),
        ("PUT", "Replace", "update", 200),
        ("DELETE", "Delete", "delete", 204),
    ],
)
@pytest.mark.parametrize(
    "case",
    [
        "success",
        "invalid",
        "provider_failure",
        "access_denied",
        "not_found",
        "quota_rejected",
    ],
)
def test_existing_crud_routes_export_metrics_logs_and_google_spans(
    method: str,
    operation: str,
    sdk_method: str,
    success_status: int,
    case: str,
    google_client: Mock,
) -> None:
    body = REQUEST_BODY
    secret = body["title"]
    sdk = google_client
    execute = getattr(sdk.events.return_value, sdk_method).return_value.execute
    provider_status = {
        "provider_failure": "503",
        "access_denied": "403",
        "not_found": "404",
        "quota_rejected": "429",
    }
    if case in provider_status:
        execute.side_effect = HttpError(
            Response({"status": provider_status[case]}), secret.encode()
        )
    reader = InMemoryMetricReader()
    telemetry = Telemetry("crud-integration", metric_readers=(reader,))
    spans = InMemorySpanExporter()
    logs = InMemoryLogRecordExporter()
    telemetry.traces.add_span_processor(SimpleSpanProcessor(spans))
    telemetry.logs.add_log_record_processor(SimpleLogRecordProcessor(logs))
    path = "/events" if method == "POST" else "/events/private-id"
    if case == "invalid" and method in {"GET", "DELETE"}:
        path = "/events/%20"
    try:
        with (
            patch(
                "app.composition.build_google_calendar_client", return_value=sdk
            ) as build,
            patch("app.composition.event_cache", EventCache()),
            TestClient(app) as client,
        ):
            app.state.telemetry = telemetry
            response = client.request(
                method, path, json={} if case == "invalid" else body
            )
        expected_status = {
            "success": success_status,
            "invalid": 422,
            "provider_failure": 503 if method == "GET" else 502,
            "access_denied": 403,
            "not_found": 404,
            "quota_rejected": 503,
        }[case]
        outcome = {
            "success": "success",
            "invalid": "invalid_input",
            "provider_failure": "provider_unavailable"
            if method == "GET"
            else "provider_error",
            "access_denied": "access_denied",
            "not_found": "not_found",
            "quota_rejected": "provider_unavailable",
        }[case]
        assert response.status_code == expected_status
        if case == "success":
            assert (
                response.content == b""
                if method == "DELETE"
                else response.json() == {"id": "private-id", **body}
            )
        finished = spans.get_finished_spans()
        parent = next(span for span in finished if span.kind == SpanKind.SERVER)
        assert parent.name == "calendar." + operation
        provider_spans = [span for span in finished if span.kind == SpanKind.CLIENT]
        if case == "invalid":
            build.assert_not_called()
            execute.assert_not_called()
            assert provider_spans == []
        else:
            execute.assert_called_once_with()
            build.assert_called_once_with()
            sdk.close.assert_called_once_with()
            call = next(
                span
                for span in provider_spans
                if span.name == "google.calendar." + operation
            )
            assert call.parent is not None
            assert call.parent.span_id == parent.context.span_id
            assert call.context.trace_id == parent.context.trace_id
            assert call.status.status_code == (
                StatusCode.ERROR if case in provider_status else StatusCode.UNSET
            )
            assert call.attributes is not None
            assert call.attributes["outcome"] == outcome
            if method == "PUT":
                assert [span.name for span in provider_spans] == [
                    "google.calendar.Get",
                    "google.calendar.Replace",
                ]
        records = []
        for record in logs.get_finished_logs():
            assert isinstance(record.log_record.body, str)
            records.append(json.loads(record.log_record.body))
        request_records = [record for record in records if "status" in record]
        assert len(request_records) == 1
        assert (
            request_records[0].items()
            >= {
                "operation": operation,
                "status": expected_status,
                "outcome": outcome,
            }.items()
        )
        assert request_records[0]["trace_id"] == format(parent.context.trace_id, "032x")
        data = reader.get_metrics_data()
        assert data is not None
        metrics = data.resource_metrics[0].scope_metrics[0].metrics
        points = {metric.name: metric.data.data_points[0] for metric in metrics}
        count = points["calendar.requests"]
        assert isinstance(count, NumberDataPoint)
        assert count.value == 1
        assert count.attributes == {
            "operation": operation,
            "outcome": outcome,
            "release": "crud-integration",
        }
        latency = points["calendar.request.duration"]
        assert isinstance(latency, HistogramDataPoint)
        assert latency.count == 1
        if case != "success":
            errors = points["calendar.errors"]
            assert isinstance(errors, NumberDataPoint)
            assert errors.value == 1
        exported = (
            repr(records)
            + repr(
                [
                    (span.attributes, span.events, span.status.description)
                    for span in finished
                ]
            )
            + repr(reader.get_metrics_data())
        )
        assert secret not in exported
        assert "private-id" not in exported
    finally:
        telemetry.shutdown()


@pytest.mark.parametrize(
    "method,sdk_method,status",
    [
        ("POST", "insert", 201),
        ("GET", "get", 200),
        ("PUT", "update", 200),
        ("DELETE", "delete", 204),
    ],
)
@pytest.mark.parametrize("failure", [False, True])
def test_telemetry_failures_preserve_actual_crud_responses(
    method: str, sdk_method: str, status: int, failure: bool, google_client: Mock
) -> None:
    body = REQUEST_BODY
    sdk = google_client
    execute = getattr(sdk.events.return_value, sdk_method).return_value.execute
    if failure:
        execute.side_effect = HttpError(Response({"status": "503"}), b"private")
    with (
        patch("app.composition.build_google_calendar_client", return_value=sdk),
        patch("app.composition.event_cache", EventCache()),
        TestClient(app) as client,
    ):
        telemetry = app.state.telemetry
        with (
            patch.object(
                telemetry.tracer, "start_span", side_effect=RuntimeError("span failure")
            ),
            patch.object(
                telemetry,
                "record_request",
                side_effect=RuntimeError("metric/log failure"),
            ),
        ):
            path = "/events" if method == "POST" else "/events/private-id"
            response = client.request(method, path, json=body)
    failure_status = 503 if method == "GET" else 502
    assert response.status_code == (failure_status if failure else status)
    if failure:
        expected_error: dict[str, object] = {
            "error": {
                "code": "provider_error",
                "message": "Calendar provider request failed",
                "retryable": False,
            }
        }
        if method == "GET":
            expected_error = {
                "error": {
                    "code": "provider_unavailable",
                    "message": "Calendar provider is unavailable",
                    "retryable": True,
                }
            }
        assert response.json() == expected_error
    elif method == "DELETE":
        assert response.content == b""
    else:
        assert response.json() == {"id": "private-id", **body}
    execute.assert_called_once_with()
    sdk.close.assert_called_once_with()


@pytest.mark.parametrize(
    "method,operation,sdk_method",
    [
        ("GET", "Get", "get"),
        ("POST", "Create", "insert"),
        ("PUT", "Replace", "update"),
    ],
)
def test_invalid_provider_response_marks_the_provider_span_as_failed(
    method: str, operation: str, sdk_method: str, google_client: Mock
) -> None:
    getattr(
        google_client.events.return_value, sdk_method
    ).return_value.execute.return_value = {}
    telemetry = Telemetry("invalid-provider-response")
    spans = InMemorySpanExporter()
    telemetry.traces.add_span_processor(SimpleSpanProcessor(spans))
    try:
        with (
            patch(
                "app.composition.build_google_calendar_client",
                return_value=google_client,
            ),
            patch("app.composition.event_cache", EventCache()),
            TestClient(app) as client,
        ):
            app.state.telemetry = telemetry
            path = "/events" if method == "POST" else "/events/private-id"
            response = client.request(method, path, json=REQUEST_BODY)
        assert response.status_code == 502
        call = next(
            span
            for span in spans.get_finished_spans()
            if span.name == "google.calendar." + operation
        )
        assert call.status.status_code == StatusCode.ERROR
        assert call.attributes is not None
        assert call.attributes["outcome"] == "provider_error"
    finally:
        telemetry.shutdown()


def test_restored_application_preserves_all_six_calendar_routes() -> None:
    paths = app.openapi()["paths"]
    assert {"get", "post"} <= paths["/events"].keys()
    assert {"get", "put", "delete", "patch"} <= paths["/events/{event_id}"].keys()
