"""The standalone agent HTTP boundary accepts interface requests and exposes status."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from agent_service.contracts import AgentRequest, ModelDecision
from agent_service.main import build_agent_service, create_agent_app
from agent_service.model import ScriptedModel
from tests.agent.conftest import ControlledApi, build_service


def test_interface_can_submit_natural_language_and_retrieve_run(tmp_path: Path) -> None:
    service = build_service(
        tmp_path,
        ScriptedModel(
            [
                ModelDecision(
                    action="clarification",
                    message="Which project should I prepare?",
                )
            ]
        ),
        ControlledApi(),
    )
    with TestClient(create_agent_app(service)) as client:
        response = client.post(
            "/agent/requests", json={"goal": "Prepare the project kickoff"}
        )
        stored = client.get(f"/agent/runs/{response.json()['run_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "needs_clarification"
    assert stored.status_code == 200
    assert stored.json()["request"] == AgentRequest(
        goal="Prepare the project kickoff"
    ).model_dump(mode="json")


def test_health_does_not_require_model_credentials() -> None:
    with TestClient(create_agent_app()) as client:
        response = client.get("/healthz")

    assert response.json() == {"status": "ok"}


def test_unknown_run_cancel_and_status_return_404(tmp_path: Path) -> None:
    service = build_service(tmp_path, ScriptedModel([]), ControlledApi())
    with TestClient(create_agent_app(service)) as client:
        assert client.get("/agent/runs/missing").status_code == 404
        assert client.post("/agent/runs/missing/cancel").status_code == 404


def test_incomplete_real_model_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "controlled-not-a-real-key")
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    build_agent_service.cache_clear()
    try:
        with TestClient(create_agent_app()) as client:
            response = client.post("/agent/requests", json={"goal": "Read an event"})
    finally:
        build_agent_service.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "agent_configuration_error",
            "message": "Agent service configuration is incomplete",
            "retryable": False,
        }
    }
