"""Own OpenTelemetry providers and isolate optional telemetry failures."""

import json
import logging
import os
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from contextvars import ContextVar
from time import perf_counter

import anyio
from calendar_contract import CalendarError
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogRecordExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

OPERATIONS = ("Create", "Get", "Replace", "Delete")
QUEUE_SIZE = 512
BATCH_SIZE = 64
EXPORT_TIMEOUT_SECONDS = 2
CURRENT: ContextVar["Telemetry | None"] = ContextVar("calendar_telemetry", default=None)


@contextmanager
def isolated() -> Iterator[None]:
    """Keep SDK/exporter bugs from affecting service behavior.

    Broad catches are intentional only around telemetry, never application code.
    Diagnostics omit exception text because exporter errors can contain secrets.
    """
    try:
        yield
    except Exception:
        try:
            logging.getLogger("calendar.telemetry").warning("telemetry_failure")
        except Exception:
            pass  # A failing log handler must not break the application either.


class Telemetry:
    """Per-process providers; export happens on bounded background workers."""

    def __init__(
        self,
        release: str,
        *,
        endpoint: str = "",
        metric_readers: tuple[MetricReader, ...] = (),
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", release):
            raise ValueError("CALENDAR_RELEASE must be a bounded release identifier")
        self.release = release
        # Do not auto-detect host, command-line, or arbitrary resource attributes.
        resource = Resource(
            {"service.name": "team2-calendar", "service.version": release}
        )
        self.traces = TracerProvider(resource=resource, sampler=ALWAYS_ON)
        self.logs = LoggerProvider(resource=resource)
        readers = list(metric_readers)
        if endpoint:
            endpoint = endpoint.rstrip("/")
            self.traces.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=endpoint + "/v1/traces", timeout=EXPORT_TIMEOUT_SECONDS
                    ),
                    max_queue_size=QUEUE_SIZE,
                    max_export_batch_size=BATCH_SIZE,
                    export_timeout_millis=2000,
                )
            )
            self.logs.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(
                        endpoint=endpoint + "/v1/logs", timeout=EXPORT_TIMEOUT_SECONDS
                    ),
                    max_queue_size=QUEUE_SIZE,
                    max_export_batch_size=BATCH_SIZE,
                    export_timeout_millis=2000,
                )
            )
            readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=endpoint + "/v1/metrics",
                        timeout=EXPORT_TIMEOUT_SECONDS,
                    ),
                    export_interval_millis=10000,
                    export_timeout_millis=3000,
                )
            )
        else:
            self.logs.add_log_record_processor(
                BatchLogRecordProcessor(
                    ConsoleLogRecordExporter(
                        formatter=lambda record: str(record.log_record.body) + "\n"
                    ),
                    max_queue_size=QUEUE_SIZE,
                    max_export_batch_size=BATCH_SIZE,
                )
            )
        self.metrics = MeterProvider(
            resource=resource,
            metric_readers=readers,
            views=[
                *[
                    View(instrument_name=name, aggregation_cardinality_limit=256)
                    for name in (
                        "calendar.requests",
                        "calendar.errors",
                        "calendar.worker.*",
                    )
                ],
                View(
                    instrument_name="calendar.request.duration",
                    aggregation=ExplicitBucketHistogramAggregation(
                        [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30]
                    ),
                    aggregation_cardinality_limit=256,
                ),
            ],
        )
        self.tracer = self.traces.get_tracer("team2.calendar")
        self.logger = self.logs.get_logger("team2.calendar")
        meter = self.metrics.get_meter("team2.calendar")
        self.requests = meter.create_counter("calendar.requests", unit="{request}")
        self.errors = meter.create_counter("calendar.errors", unit="{error}")
        self.duration = meter.create_histogram("calendar.request.duration", unit="s")
        self.limiter: anyio.CapacityLimiter | None = None
        meter.create_observable_gauge(
            "calendar.worker.utilization", callbacks=[self.worker_utilization], unit="1"
        )
        meter.create_observable_gauge(
            "calendar.worker.capacity",
            callbacks=[self.worker_capacity],
            unit="{worker}",
        )

    def worker_utilization(self, _options: object) -> list[Observation]:
        """Measure occupied sync workers relative to the real AnyIO limit."""
        if self.limiter is None:
            return []
        return [
            Observation(
                self.limiter.borrowed_tokens / self.limiter.total_tokens,
                {"release": self.release},
            )
        ]

    def worker_capacity(self, _options: object) -> list[Observation]:
        """Expose the denominator without changing the service's worker limit."""
        if self.limiter is None:
            return []
        return [Observation(self.limiter.total_tokens, {"release": self.release})]

    def emit(self, fields: dict[str, str | int | float]) -> None:
        """Emit only caller-selected bounded metadata, never exception contents."""
        self.logger.emit(
            body=json.dumps(fields),
            attributes=fields,
            severity_number=SeverityNumber.INFO,
        )

    def record_request(
        self,
        operation: str,
        status: int,
        outcome: str,
        duration: float,
        request_id: str,
    ) -> None:
        """Record a single completed request with fixed metric dimensions."""
        labels = {"operation": operation, "release": self.release, "outcome": outcome}
        # Isolate signals individually so a failed metric does not suppress logs.
        with isolated():
            self.requests.add(1, labels)
        with isolated():
            self.duration.record(duration, labels)
        if outcome != "success":
            with isolated():
                self.errors.add(1, labels)
        with isolated():
            context = trace.get_current_span().get_span_context()
            self.emit(
                {
                    "operation": operation,
                    "outcome": outcome,
                    "status": status,
                    "release": self.release,
                    "request_id": request_id,
                    "trace_id": format(context.trace_id, "032x"),
                    "duration": duration,
                }
            )

    def shutdown(self) -> None:
        """Release background workers without flushing on request threads."""
        for provider in (self.metrics, self.logs, self.traces):
            with isolated():
                provider.shutdown()


@asynccontextmanager
async def telemetry_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize once after the worker event loop exists; fail open on telemetry."""
    telemetry = None
    with isolated():
        telemetry = Telemetry(
            os.getenv("CALENDAR_RELEASE", "development"),
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        )
        telemetry.limiter = anyio.to_thread.current_default_thread_limiter()
    app.state.telemetry = telemetry
    try:
        yield
    finally:
        if telemetry is not None:
            await anyio.to_thread.run_sync(telemetry.shutdown)


@contextmanager
def provider_span(operation: str) -> Iterator[None]:
    """Time the provider boundary without recording inputs or exception text.

    The request's OTel context propagates into FastAPI's sync worker. Application
    exceptions pass through unchanged and are never retried here.
    """
    telemetry = CURRENT.get()
    span = None
    stack = ExitStack()
    started = perf_counter()
    outcome = "success"
    with isolated():
        if telemetry is not None and operation in OPERATIONS:
            span = telemetry.tracer.start_span(
                "google.calendar." + operation,
                kind=trace.SpanKind.CLIENT,
                attributes={"operation": operation, "release": telemetry.release},
            )
            stack.enter_context(
                trace.use_span(
                    span, record_exception=False, set_status_on_exception=False
                )
            )
    try:
        yield
    except BaseException as error:
        outcome = "provider_error"
        with isolated():
            if isinstance(error, CalendarError):
                category = error.code.value
                if category in {
                    "invalid_input",
                    "not_found",
                    "access_denied",
                    "provider_error",
                    "provider_unavailable",
                }:
                    outcome = category
            if span is not None:
                span.set_status(trace.StatusCode.ERROR)
        raise
    finally:
        with isolated():
            if span is not None:
                span.set_attribute("outcome", outcome)
            if telemetry is not None and outcome != "success":
                telemetry.emit(
                    {
                        "operation": operation,
                        "outcome": outcome,
                        "release": telemetry.release,
                        "trace_id": format(
                            trace.get_current_span().get_span_context().trace_id, "032x"
                        ),
                        "duration": perf_counter() - started,
                    }
                )
        with isolated():
            stack.close()
        with isolated():
            if span is not None:
                span.end()
