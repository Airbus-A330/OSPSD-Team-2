"""Exercise actual bounded exporters against controlled HTTP receivers."""

import json
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Event, Thread

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from app.telemetry.http import CalendarTelemetryMiddleware
from app.telemetry.runtime import BATCH_SIZE, QUEUE_SIZE, Telemetry, provider_span


def test_otlp_exports_success_invalid_and_provider_failure_without_sensitive_data(
    monkeypatch,
) -> None:
    received: Queue[tuple[str, bytes]] = Queue()

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            received.put(
                (self.path, self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_COMPRESSION", "none")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    telemetry = Telemetry(
        "export-test", endpoint=f"http://127.0.0.1:{server.server_port}"
    )
    application = FastAPI()
    application.state.telemetry = telemetry
    application.add_middleware(CalendarTelemetryMiddleware)

    @application.get("/events/{event_id}")
    def read(event_id: str, failure: bool = False) -> dict[str, str]:
        with provider_span("Get"):
            if failure:
                raise RuntimeError("SECRET provider body with OAuth token")
            return {"title": "SECRET calendar contents"}

    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            assert client.get("/events/private-id").status_code == 200
            assert client.get("/events/private-id?failure=bad").status_code == 422
            assert client.get("/events/private-id?failure=true").status_code == 500
        assert telemetry.traces.force_flush(timeout_millis=5000)
        assert telemetry.logs.force_flush(timeout_millis=5000)
        assert telemetry.metrics.force_flush(timeout_millis=5000)

        payloads = []
        while not received.empty():
            path, body = received.get_nowait()
            assert path in ("/v1/logs", "/v1/traces", "/v1/metrics")
            payloads.append(
                ExportLogsServiceRequest.FromString(body)
                if path == "/v1/logs"
                else ExportTraceServiceRequest.FromString(body)
                if path == "/v1/traces"
                else ExportMetricsServiceRequest.FromString(body)
            )
        exported = "\n".join(str(payload) for payload in payloads)
        assert "SECRET" not in exported
        assert "private-id" not in exported
        assert "exception.message" not in exported
        logs = [
            record
            for payload in payloads
            if isinstance(payload, ExportLogsServiceRequest)
            for resource in payload.resource_logs
            for scope in resource.scope_logs
            for record in scope.log_records
        ]
        spans = [
            span
            for payload in payloads
            if isinstance(payload, ExportTraceServiceRequest)
            for resource in payload.resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
        ]
        outcomes = [
            record
            for record in logs
            if "status" in json.loads(record.body.string_value)
        ]
        assert sorted(
            json.loads(record.body.string_value)["status"] for record in outcomes
        ) == [200, 422, 500]
        assert len(spans) == 5  # Three HTTP spans and two Google boundary spans.
        for record in outcomes:
            assert any(span.trace_id == record.trace_id for span in spans)
            assert (
                json.loads(record.body.string_value)["trace_id"]
                == record.trace_id.hex()
            )
        assert any(
            isinstance(payload, ExportMetricsServiceRequest) for payload in payloads
        )
    finally:
        telemetry.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_blocked_exporter_drops_overflow_without_blocking_http() -> None:
    started = Event()
    unblock = Event()
    exported: list[ReadableSpan] = []

    class BlockedExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            started.set()
            unblock.wait(timeout=10)
            exported.extend(spans)
            return SpanExportResult.SUCCESS

    telemetry = Telemetry("blocked-export-test")
    telemetry.traces.add_span_processor(
        BatchSpanProcessor(
            BlockedExporter(),
            max_queue_size=QUEUE_SIZE,
            max_export_batch_size=BATCH_SIZE,
            schedule_delay_millis=1,
        )
    )
    application = FastAPI()
    application.state.telemetry = telemetry
    application.add_middleware(CalendarTelemetryMiddleware)

    @application.get("/events/{event_id}")
    def read(event_id: str) -> dict[str, str]:
        return {"result": "ok"}

    try:
        telemetry.tracer.start_span("first").end()
        assert started.wait(timeout=2)
        for _ in range(QUEUE_SIZE * 2):
            telemetry.tracer.start_span("overflow").end()
        with TestClient(application) as client:
            assert client.get("/events/id").json() == {"result": "ok"}
        assert not unblock.is_set()
        unblock.set()
        assert telemetry.traces.force_flush(timeout_millis=5000)
        assert len(exported) <= QUEUE_SIZE + 1
    finally:
        unblock.set()
        telemetry.shutdown()


def test_unavailable_otlp_backend_preserves_normal_http_requests() -> None:
    # Bind but do not listen: the OS rejects exporter connections deterministically.
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), BaseHTTPRequestHandler, bind_and_activate=False
    )
    server.server_bind()
    telemetry = Telemetry(
        "backend-down-test", endpoint=f"http://127.0.0.1:{server.server_port}"
    )
    application = FastAPI()
    application.state.telemetry = telemetry
    application.add_middleware(CalendarTelemetryMiddleware)

    @application.get("/events/{event_id}")
    def read(event_id: str, number: int = 1) -> dict[str, int]:
        return {"number": number}

    try:
        with TestClient(application) as client:
            assert client.get("/events/id").json() == {"number": 1}
            assert client.get("/events/id?number=invalid").status_code == 422
        telemetry.traces.force_flush(timeout_millis=5000)
        telemetry.logs.force_flush(timeout_millis=5000)
        telemetry.metrics.force_flush(timeout_millis=5000)
        with TestClient(application) as client:
            assert client.get("/events/id").json() == {"number": 1}
    finally:
        telemetry.shutdown()
        server.server_close()
