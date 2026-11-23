"""FastAPI boundary and environment composition for the separate agent service."""

from functools import lru_cache
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict

from agent_service.contracts import AgentRequest, AgentRunResult, StoredRun
from agent_service.model import OpenAIResponsesModel
from agent_service.service import AgentLimits, AgentService
from agent_service.store import SQLiteRunStore
from agent_service.tools import HttpApiServiceClient, ToolRegistry


class AgentConfigurationError(RuntimeError):
    """Sanitized invalid agent runtime configuration."""


class CancellationResult(BaseModel):
    """Interface-visible cancellation acknowledgement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    cancelled: bool


def _float_setting(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        raise AgentConfigurationError(f"{name} must be numeric") from None


def _int_setting(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        raise AgentConfigurationError(f"{name} must be an integer") from None


@lru_cache(maxsize=1)
def build_agent_service() -> AgentService:
    """Build the real model/API/store composition without provider SDK access."""
    provider = os.getenv("AGENT_MODEL_PROVIDER", "openai")
    if provider != "openai":
        raise AgentConfigurationError("AGENT_MODEL_PROVIDER must be openai")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AgentConfigurationError("OPENAI_API_KEY is required")
    model_name = os.getenv("AGENT_MODEL")
    if not model_name:
        raise AgentConfigurationError("AGENT_MODEL is required")
    timeout = _float_setting("AGENT_MODEL_TIMEOUT_SECONDS", 20)
    api_timeout = _float_setting("AGENT_API_TIMEOUT_SECONDS", 10)
    max_cost = os.getenv("AGENT_MAX_COST_USD")
    try:
        limits = AgentLimits(
            max_steps=_int_setting("AGENT_MAX_STEPS", 8),
            max_duration_seconds=_float_setting("AGENT_MAX_DURATION_SECONDS", 30),
            max_tokens=_int_setting("AGENT_MAX_TOKENS", 20_000),
            max_cost_usd=float(max_cost) if max_cost else None,
        )
        model = OpenAIResponsesModel(
            api_key=api_key,
            model=model_name,
            timeout_seconds=timeout,
            endpoint=os.getenv(
                "OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses"
            ),
        )
        api = HttpApiServiceClient(
            os.getenv("AGENT_API_BASE_URL", "http://127.0.0.1:8000"),
            timeout_seconds=api_timeout,
            service_key=os.getenv("AGENT_API_SERVICE_KEY"),
        )
    except ValueError as error:
        raise AgentConfigurationError(str(error)) from None
    database = Path(os.getenv("AGENT_STATE_DATABASE", ".agent-state/agent.sqlite3"))
    return AgentService(
        model=model,
        tools=ToolRegistry(api),
        store=SQLiteRunStore(database),
        limits=limits,
    )


def create_agent_app(service: AgentService | None = None) -> FastAPI:
    """Create the standalone agent HTTP service with injectable controlled behavior."""
    application = FastAPI(title="Team 2 Agent Service")

    def configured_service() -> AgentService:
        if service is not None:
            return service
        try:
            return build_agent_service()
        except AgentConfigurationError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "agent_configuration_error",
                    "message": "Agent service configuration is incomplete",
                    "retryable": False,
                },
            ) from None

    @application.get("/healthz")
    def health() -> dict[str, str]:
        """Report process readiness without contacting a model or provider."""
        return {"status": "ok"}

    @application.post("/agent/requests", response_model=AgentRunResult)
    def submit(request: AgentRequest) -> AgentRunResult:
        """Accept one natural-language goal from an interface."""
        return configured_service().run(request)

    @application.get("/agent/runs/{run_id}", response_model=StoredRun)
    def get_run(run_id: str) -> StoredRun:
        """Return persisted status without rerunning model or tools."""
        run = configured_service().get_run(run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return run

    @application.post("/agent/runs/{run_id}/cancel", response_model=CancellationResult)
    def cancel(run_id: str) -> CancellationResult:
        """Persist cancellation so the loop stops at its next boundary."""
        if not configured_service().cancel(run_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return CancellationResult(run_id=run_id, cancelled=True)

    return application


app = create_agent_app()
