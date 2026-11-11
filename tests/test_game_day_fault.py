"""Credential-free bounds and isolation checks for the opt-in exercise image."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.composition import get_calendar_service
from app.errors import NotFoundError
from app.hosting import create_hosted_app
from app.models import Event
from reliability import game_day_fault as fault

API_TOKEN = "synthetic-game-day-" + "x" * 32
HEADERS = {"Authorization": "Bearer " + API_TOKEN}


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, list[float]]:
    monkeypatch.setattr("app.hosting.prepare_runtime", lambda: API_TOKEN)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setenv("CALENDAR_RELEASE", "game-day-unit-test")
    clock = [100.0]
    monkeypatch.setattr(fault, "monotonic", lambda: clock[0])
    service = Mock()

    def get(event_id: str) -> Event:
        if event_id == fault.FAULT_EVENT_ID:
            raise NotFoundError()
        return Event(
            id=event_id,
            title="Synthetic event",
            start="2026-11-01T10:00:00Z",
            end="2026-11-01T11:00:00Z",
        )

    service.get.side_effect = get
    return service, clock


@pytest.fixture
def client(host: tuple[Mock, list[float]]) -> Iterator[TestClient]:
    application = fault.create_faulty_app()
    application.dependency_overrides[get_calendar_service] = lambda: host[0]
    with TestClient(application) as client:
        yield client


def test_fault_preserves_authentication_and_does_not_arm_for_rejected_requests(
    client: TestClient, host: tuple[Mock, list[float]]
) -> None:
    service, clock = host
    assert client.get(fault.FAULT_PATH).status_code == 403
    service.get.assert_not_called()
    clock[0] = 1000.0
    response = client.get(fault.FAULT_PATH, headers=HEADERS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    service.get.assert_not_called()


def test_fault_preserves_readiness_other_reads_and_write_routing(
    client: TestClient, host: tuple[Mock, list[float]]
) -> None:
    assert client.get("/readyz").json() == {"status": "ready"}
    assert client.get("/events/other-synthetic", headers=HEADERS).status_code == 200
    host[0].get.assert_called_once_with("other-synthetic")
    assert client.post(fault.FAULT_PATH, headers=HEADERS).status_code == 405
    host[0].create.assert_not_called()


def test_fault_expires_at_five_minutes_and_does_not_rearm(
    client: TestClient, host: tuple[Mock, list[float]]
) -> None:
    _, clock = host
    assert client.get(fault.FAULT_PATH, headers=HEADERS).status_code == 503
    clock[0] += fault.MAX_FAULT_SECONDS - 0.01
    assert client.get(fault.FAULT_PATH, headers=HEADERS).status_code == 503
    clock[0] += 0.01
    assert client.get(fault.FAULT_PATH, headers=HEADERS).status_code == 404
    clock[0] += 1000
    assert client.get(fault.FAULT_PATH, headers=HEADERS).status_code == 404


def test_normal_factory_never_enables_the_exercise_fault(
    host: tuple[Mock, list[float]],
) -> None:
    application = create_hosted_app()
    application.dependency_overrides[get_calendar_service] = lambda: host[0]
    with TestClient(application) as client:
        assert client.get(fault.FAULT_PATH, headers=HEADERS).status_code == 404
