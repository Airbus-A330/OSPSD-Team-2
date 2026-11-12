"""Focused evidence for the temporary Assignment 2 game-day fault."""

import json
from unittest.mock import Mock

from calendar_contract import CreateEvent, Event, ReplaceEvent
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.calendar_service import CalendarServiceAdapter
from app.composition import get_calendar_service
from app import hosting
from app.main import create_app
from app.providers import EventProvider
from app.telemetry.runtime import Telemetry

EVENT_VALUES = {
    "title": "Game day fixture",
    "start": "2030-01-07T15:00:00Z",
    "end": "2030-01-07T16:00:00Z",
}


def test_shared_get_returns_observable_provider_unavailable() -> None:
    provider = Mock(spec=EventProvider)
    application = create_app()
    application.dependency_overrides[get_calendar_service] = lambda: (
        CalendarServiceAdapter(provider, validate_get=False)
    )
    reader = InMemoryMetricReader()
    telemetry = Telemetry("game-day-test", metric_readers=(reader,))
    logs = InMemoryLogRecordExporter()
    spans = InMemorySpanExporter()
    telemetry.logs.add_log_record_processor(SimpleLogRecordProcessor(logs))
    telemetry.traces.add_span_processor(SimpleSpanProcessor(spans))
    try:
        with TestClient(application) as client:
            application.state.telemetry = telemetry
            response = client.get("/events/disposable-event")

        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "provider_unavailable",
                "message": "Calendar provider is unavailable",
                "retryable": True,
            }
        }
        provider.get_event.assert_not_called()
        data = reader.get_metrics_data()
        assert data is not None
        metrics = data.resource_metrics[0].scope_metrics[0].metrics
        points = {metric.name: metric.data.data_points[0] for metric in metrics}
        assert points["calendar.requests"].attributes == {
            "operation": "Get",
            "outcome": "provider_unavailable",
            "release": "game-day-test",
        }
        error_point = points["calendar.errors"]
        assert isinstance(error_point, NumberDataPoint)
        assert error_point.value == 1
        server_span = spans.get_finished_spans()[0]
        assert server_span.name == "calendar.Get"
        assert server_span.attributes is not None
        assert server_span.attributes["outcome"] == "provider_unavailable"
        body = logs.get_finished_logs()[0].log_record.body
        assert isinstance(body, str)
        record = json.loads(body)
        assert (
            record.items()
            >= {
                "operation": "Get",
                "outcome": "provider_unavailable",
                "status": 503,
                "release": "game-day-test",
            }.items()
        )
    finally:
        telemetry.shutdown()


def test_fault_does_not_deliberately_break_shared_writes() -> None:
    provider = Mock(spec=EventProvider)
    event = Event(id="disposable-event", **EVENT_VALUES)
    provider.create_event.return_value = event
    provider.replace_event.return_value = event
    service = CalendarServiceAdapter(provider)

    assert service.create(CreateEvent(**EVENT_VALUES)) == event
    assert service.replace(event.id, ReplaceEvent(**EVENT_VALUES)) == event
    service.delete(event.id)

    provider.create_event.assert_called_once()
    provider.replace_event.assert_called_once()
    provider.delete_event.assert_called_once_with(event.id)


def test_health_and_readiness_remain_available(monkeypatch) -> None:
    api_token = "game-day-test-token-" + "x" * 32
    monkeypatch.setattr(hosting, "prepare_runtime", lambda: api_token)
    application = hosting.create_hosted_app()
    application.dependency_overrides[get_calendar_service] = lambda: (
        CalendarServiceAdapter(Mock(spec=EventProvider), validate_get=False)
    )

    with TestClient(application) as client:
        assert client.get("/healthz").json() == {"status": "alive"}
        assert client.get("/readyz").json() == {"status": "ready"}
        response = client.get(
            "/events/disposable-event",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 503
        assert client.get("/readyz").status_code == 200
