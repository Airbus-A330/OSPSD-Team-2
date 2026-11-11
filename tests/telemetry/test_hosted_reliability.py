"""Verify the real hosted Get path supplies the reliability metric contract."""

import json
from functools import partial
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]
from httplib2 import Response  # type: ignore[import-untyped]
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
    NumberDataPoint,
)

from app import composition
from app.event_cache import EventCache
from app.hosting import create_hosted_app
from app.telemetry import runtime
from app.telemetry.runtime import Telemetry

API_TOKEN = "synthetic-hosted-reliability-" + "x" * 32


@pytest.fixture
def hosted_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[FastAPI, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    for key, value in {
        "GOOGLE_CALENDAR_ID": "synthetic-calendar",
        "GOOGLE_CALENDAR_NONINTERACTIVE": "1",
        "GOOGLE_CALENDAR_TOKEN_FILE": str(tmp_path / "token.json"),
        "GOOGLE_CALENDAR_TOKEN_JSON": json.dumps(
            {
                key: "synthetic-only"
                for key in ("client_id", "client_secret", "refresh_token")
            }
        ),
        "CALENDAR_API_TOKEN": API_TOKEN,
        "CALENDAR_RELEASE": "hosted-reliability-test",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        runtime, "Telemetry", partial(Telemetry, metric_readers=(reader,))
    )
    return create_hosted_app(), reader


@pytest.fixture
def google_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    sdk = Mock()
    sdk.events.return_value.get.return_value.execute.return_value = {
        "id": "synthetic-event",
        "summary": "Synthetic event",
        "start": {"dateTime": "2026-11-01T10:00:00Z"},
        "end": {"dateTime": "2026-11-01T11:00:00Z"},
    }
    monkeypatch.setattr(
        composition, "build_google_calendar_client", Mock(return_value=sdk)
    )
    monkeypatch.setattr(composition, "event_cache", EventCache())
    return sdk


@pytest.mark.parametrize(
    "case,status,outcome",
    [
        ("success", 200, "success"),
        ("missing", 404, "not_found"),
        ("access", 403, "access_denied"),
        ("unavailable", 503, "provider_unavailable"),
        ("bad_response", 502, "provider_error"),
        ("invalid", 422, "invalid_input"),
        ("unauthorized", 403, "access_denied"),
    ],
)
def test_hosted_get_exports_eligible_outcomes_and_latency(
    hosted_metrics: tuple[FastAPI, InMemoryMetricReader],
    google_client: Mock,
    case: str,
    status: int,
    outcome: str,
) -> None:
    application, reader = hosted_metrics
    execute = google_client.events.return_value.get.return_value.execute
    if case in {"missing", "access", "unavailable"}:
        execute.side_effect = HttpError(Response({"status": str(status)}), b"{}")
    if case == "bad_response":
        execute.return_value = {}
    with TestClient(application) as client:
        path = "/events/%20" if case == "invalid" else "/events/synthetic-event"
        headers = (
            {} if case == "unauthorized" else {"Authorization": f"Bearer {API_TOKEN}"}
        )
        response = client.get(path, headers=headers)
        assert response.status_code == status
        data = reader.get_metrics_data()
        assert data is not None
        metrics = {
            m.name: m.data.data_points[0]
            for m in data.resource_metrics[0].scope_metrics[0].metrics
        }
        count = metrics["calendar.requests"]
        latency = metrics["calendar.request.duration"]
        assert isinstance(count, NumberDataPoint)
        assert isinstance(latency, HistogramDataPoint)
        assert count.attributes == {
            "operation": "Get",
            "outcome": outcome,
            "release": "hosted-reliability-test",
        }
        assert count.value == latency.count == 1
        assert 1 in latency.explicit_bounds
        expected_calls = int(case not in {"invalid", "unauthorized"})
        assert execute.call_count == expected_calls
    assert application.state.ready is False
    assert application.state.api_token == ""
