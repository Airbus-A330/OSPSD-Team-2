"""Behavioral checks at HTTP, SDK, and export boundaries without credentials."""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import anyio
import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from app.main import app
from app.event_cache import EventCache
from app.telemetry.http import CalendarTelemetryMiddleware, operation_for, outcome_for
from app.telemetry.runtime import Telemetry, provider_span, telemetry_lifespan


@pytest.fixture
def signals() -> Iterator[
    tuple[
        Telemetry, InMemoryMetricReader, InMemorySpanExporter, InMemoryLogRecordExporter
    ]
]:
    reader = InMemoryMetricReader()
    telemetry = Telemetry("test-release", metric_readers=(reader,))
    spans = InMemorySpanExporter()
    logs = InMemoryLogRecordExporter()
    telemetry.traces.add_span_processor(SimpleSpanProcessor(spans))
    telemetry.logs.add_log_record_processor(SimpleLogRecordProcessor(logs))
    yield telemetry, reader, spans, logs
    telemetry.shutdown()


def controlled_app(telemetry: Telemetry) -> FastAPI:
    application = FastAPI()
    application.state.telemetry = telemetry
    application.add_middleware(CalendarTelemetryMiddleware)

    @application.api_route("/events", methods=["POST"], status_code=201)
    @application.api_route("/events/{event_id}", methods=["GET", "PUT", "DELETE"])
    def operation(
        request: Request, response: Response, event_id: str = "", status: int = 200
    ) -> dict[str, str]:
        if status >= 400:
            raise HTTPException(status)
        if request.method == "DELETE":
            response.status_code = 204
        with provider_span(operation_for(request.method, request.url.path) or "Get"):
            return {"result": "ok"}

    return application


@pytest.mark.parametrize(
    ("method", "path", "operation"),
    [
        ("POST", "/events", "Create"),
        ("GET", "/events/private-id", "Get"),
        ("PUT", "/events/private-id", "Replace"),
        ("DELETE", "/events/private-id", "Delete"),
    ],
)
def test_shared_operations_emit_counts_histograms_and_correlated_logs(
    signals, method: str, path: str, operation: str
) -> None:
    telemetry, reader, spans, logs = signals
    with TestClient(controlled_app(telemetry)) as client:
        response = client.request(method, path)
    assert response.is_success
    metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
    by_name = {metric.name: metric for metric in metrics}
    labels = {"operation": operation, "release": "test-release", "outcome": "success"}
    count = by_name["calendar.requests"].data.data_points[0]
    assert count.value == 1
    assert count.attributes == labels
    latency = by_name["calendar.request.duration"].data.data_points[0]
    assert latency.count == 1
    assert latency.sum > 0
    assert latency.attributes == labels
    assert "calendar.errors" not in by_name
    record = json.loads(logs.get_finished_logs()[0].log_record.body)
    server_span = next(
        span for span in spans.get_finished_spans() if span.kind == SpanKind.SERVER
    )
    assert (
        record.items()
        >= {
            "operation": operation,
            "outcome": "success",
            "status": response.status_code,
            "release": "test-release",
            "trace_id": format(server_span.context.trace_id, "032x"),
        }.items()
    )
    assert len(record["request_id"]) == 32
    assert response.headers["x-request-id"] == record["request_id"]
    assert len(metrics) == len(by_name)  # No overlapping views duplicate instruments.


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (400, "invalid_input"),
        (422, "invalid_input"),
        (403, "access_denied"),
        (404, "not_found"),
        (502, "provider_error"),
        (503, "provider_unavailable"),
        (500, "application_error"),
        (405, "client_error"),
    ],
)
@pytest.mark.parametrize(
    "method,path,operation",
    [
        ("POST", "/events", "Create"),
        ("GET", "/events/id", "Get"),
        ("PUT", "/events/id", "Replace"),
        ("DELETE", "/events/id", "Delete"),
    ],
)
def test_error_metrics_use_bounded_categories(
    signals, status, outcome, method, path, operation
) -> None:
    telemetry, reader, _, logs = signals
    with TestClient(controlled_app(telemetry)) as client:
        assert (
            client.request(method, path, params={"status": status}).status_code
            == status
        )
    metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
    error = next(metric for metric in metrics if metric.name == "calendar.errors")
    assert error.data.data_points[0].value == 1
    assert error.data.data_points[0].attributes == {
        "operation": operation,
        "release": "test-release",
        "outcome": outcome,
    }
    assert json.loads(logs.get_finished_logs()[0].log_record.body)["outcome"] == outcome


def test_invalid_request_is_traced_before_validation_without_provider_call(
    signals,
) -> None:
    telemetry, _, spans, logs = signals
    with TestClient(controlled_app(telemetry)) as client:
        response = client.get("/events/id?status=not-an-integer")
    assert response.status_code == 422
    assert [span.name for span in spans.get_finished_spans()] == ["calendar.Get"]
    assert (
        json.loads(logs.get_finished_logs()[0].log_record.body)["outcome"]
        == "invalid_input"
    )


@pytest.mark.parametrize("failure", [False, True])
def test_real_http_to_google_boundary_has_nested_spans_without_sensitive_data(
    signals, failure
) -> None:
    telemetry, reader, spans, logs = signals
    google_client = MagicMock()
    execute = google_client.events.return_value.get.return_value.execute
    secret = "SECRET-calendar-content-token"
    if failure:
        execute.side_effect = RuntimeError(secret)
    else:
        execute.return_value = {
            "id": "private-id",
            "summary": secret,
            "start": {"dateTime": "2026-11-01T10:00:00Z"},
            "end": {"dateTime": "2026-11-01T11:00:00Z"},
        }
    with (
        patch(
            "app.composition.build_google_calendar_client", return_value=google_client
        ),
        patch("app.composition.event_cache", EventCache()),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        app.state.telemetry = telemetry
        response = client.get(
            "/events/private-id?private-query=secret",
            headers={
                "authorization": "Bearer " + secret,
                "baggage": "secret=" + secret,
                "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
            },
        )
    assert response.status_code == (500 if failure else 200)
    child, parent = spans.get_finished_spans()
    assert child.name == "google.calendar.Get"
    assert child.kind == SpanKind.CLIENT
    assert child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id
    assert parent.context.trace_id == int("1234567890abcdef1234567890abcdef", 16)
    assert parent.start_time <= child.start_time <= child.end_time <= parent.end_time
    assert child.status.status_code == (
        StatusCode.ERROR if failure else StatusCode.UNSET
    )
    assert child.events == ()  # Automatic exception messages/stacks are disabled.
    exported = repr(
        [
            (span.attributes, span.events, span.status.description)
            for span in (child, parent)
        ]
    )
    exported += repr([record.log_record.body for record in logs.get_finished_logs()])
    exported += repr(reader.get_metrics_data())
    for private in (secret, "private-id", "private-query", "authorization", "baggage"):
        assert private not in exported
    outcome_logs = [
        entry
        for entry in logs.get_finished_logs()
        if "status" in json.loads(entry.log_record.body)
    ]
    assert len(outcome_logs) == 1
    execute.assert_called_once_with()


def test_worker_saturation_uses_the_actual_capacity_limit(signals) -> None:
    telemetry, reader, _, _ = signals

    async def measure() -> None:
        telemetry.limiter = anyio.CapacityLimiter(2)
        async with telemetry.limiter:
            metrics = (
                reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
            )
            values = {
                metric.name: metric.data.data_points[0].value for metric in metrics
            }
            assert values["calendar.worker.utilization"] == 0.5
            assert values["calendar.worker.capacity"] == 2

    anyio.run(measure)


@pytest.mark.parametrize(
    "signal", ["requests", "duration", "errors", "logger", "tracer"]
)
def test_instrumentation_failure_preserves_success_and_error_responses(
    signals, signal
) -> None:
    telemetry, _, _, _ = signals
    broken = MagicMock()
    for method in ("add", "record", "emit", "start_span"):
        getattr(broken, method).side_effect = RuntimeError("telemetry backend failed")
    setattr(telemetry, signal, broken)
    with TestClient(controlled_app(telemetry)) as client:
        assert client.get("/events/id").json() == {"result": "ok"}
        assert client.get("/events/id?status=503").status_code == 503


def test_unmatched_routes_do_not_create_unbounded_metric_dimensions(signals) -> None:
    telemetry, _, spans, logs = signals
    application = controlled_app(telemetry)

    with TestClient(application, raise_server_exceptions=False) as client:
        assert client.get("/unmatched/private-value").status_code == 404
    assert not spans.get_finished_spans()
    assert not logs.get_finished_logs()


def test_release_identifier_is_validated() -> None:
    with pytest.raises(ValueError, match="bounded release identifier"):
        Telemetry("release\nwith-untrusted-data")


def test_unknown_status_has_explicit_category() -> None:
    assert outcome_for(504) == "application_error"
    assert outcome_for(401) == "client_error"


@pytest.mark.parametrize(
    "method,operation,expected_status",
    [
        ("POST", "Create", 201),
        ("GET", "Get", 200),
        ("PUT", "Replace", 200),
        ("DELETE", "Delete", 204),
    ],
)
@pytest.mark.parametrize("status", [200, 201, 204, 301, 307])
def test_only_contract_success_status_is_counted_as_success(
    signals, method: str, operation: str, expected_status: int, status: int
) -> None:
    telemetry, reader, spans, logs = signals
    application = FastAPI()
    application.state.telemetry = telemetry
    application.add_middleware(CalendarTelemetryMiddleware)

    def unexpected_response() -> Response:
        return Response(status_code=status)

    path = "/events" if method == "POST" else "/events/id"
    application.add_api_route(path, unexpected_response, methods=[method])
    with TestClient(application) as client:
        assert (
            client.request(method, path, follow_redirects=False).status_code == status
        )
    outcome = "success" if status == expected_status else "unexpected_status"
    assert json.loads(logs.get_finished_logs()[0].log_record.body)["outcome"] == outcome
    metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
    points = {metric.name: metric.data.data_points[0] for metric in metrics}
    assert points["calendar.requests"].attributes["outcome"] == outcome
    assert ("calendar.errors" in points) == (outcome != "success")
    assert spans.get_finished_spans()[0].attributes["outcome"] == outcome


def test_bad_telemetry_configuration_does_not_prevent_startup(monkeypatch) -> None:
    monkeypatch.setenv("CALENDAR_RELEASE", "invalid\nrelease")
    application = FastAPI(lifespan=telemetry_lifespan)
    application.add_middleware(CalendarTelemetryMiddleware)

    @application.get("/events/{event_id}")
    def read(event_id: str) -> dict[str, str]:
        return {"result": "ok"}

    with TestClient(application) as client:
        assert client.get("/events/id").json() == {"result": "ok"}
        assert application.state.telemetry is None


def test_lifespan_observes_the_running_fastapi_worker_pool(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("CALENDAR_RELEASE", "worker-test")
    application = FastAPI(lifespan=telemetry_lifespan)
    with TestClient(application):
        limiter = application.state.telemetry.limiter
        assert limiter.total_tokens > 0
        assert limiter.borrowed_tokens == 0


def test_host_lifespan_can_preserve_telemetry_startup_and_shutdown(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("CALENDAR_RELEASE", "host-lifecycle-test")
    application = FastAPI(lifespan=telemetry_lifespan)
    original_lifespan = application.router.lifespan_context

    @asynccontextmanager
    async def hosted_lifespan(host: FastAPI) -> AsyncIterator[None]:
        async with original_lifespan(host):
            host.state.host_ready = True
            try:
                yield
            finally:
                host.state.host_ready = False

    application.router.lifespan_context = hosted_lifespan
    application.add_middleware(CalendarTelemetryMiddleware)

    @application.get("/events/{event_id}")
    def read(event_id: str) -> dict[str, str | bool]:
        return {
            "release": application.state.telemetry.release,
            "host_ready": application.state.host_ready,
        }

    with TestClient(application) as client:
        assert client.get("/events/id").json() == {
            "release": "host-lifecycle-test",
            "host_ready": True,
        }
    assert application.state.host_ready is False


def test_outer_telemetry_records_host_access_rejection(signals) -> None:
    telemetry, reader, spans, logs = signals
    application = FastAPI()
    application.state.telemetry = telemetry

    @application.middleware("http")
    async def access_check(request, call_next):
        return Response(status_code=403)

    application.add_middleware(CalendarTelemetryMiddleware)
    with TestClient(application) as client:
        assert client.get("/events/id").status_code == 403
    assert (
        json.loads(logs.get_finished_logs()[0].log_record.body)["outcome"]
        == "access_denied"
    )
    assert [span.name for span in spans.get_finished_spans()] == ["calendar.Get"]
    metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
    count = next(metric for metric in metrics if metric.name == "calendar.requests")
    assert count.data.data_points[0].attributes["outcome"] == "access_denied"
