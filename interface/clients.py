"""HTTP workflow client and small handoff contracts for unfinished services."""

from dataclasses import dataclass, field
from typing import Literal, Protocol
from urllib.parse import urlsplit

import httpx
from calendar_contract import ErrorCode
from pydantic import ValidationError

from app.workflows import (
    ProjectKickoffFailureResult,
    ProjectKickoffRequest,
    ProjectKickoffResult,
    WorkflowErrorResponse,
)

State = Literal[
    "preparing",
    "retrieving context",
    "awaiting approval",
    "executing",
    "succeeded",
    "partially succeeded",
    "failed",
    "uncertain",
    "not attempted",
]
Decision = Literal["approve", "reject", "change"]


@dataclass(frozen=True)
class StepView:
    """Presentation of one backend-confirmed outcome."""

    name: str
    state: str
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionView:
    """Safe result for rendering, with retained references for reconciliation."""

    state: State
    message: str
    guidance: str
    steps: tuple[StepView, ...]
    code: str = ""


STEP_LABELS = {
    "storage": "Save document",
    "issue_tracker": "Create follow-up issue",
    "calendar": "Schedule event",
}
GUIDANCE = {
    "invalid_input": "Review the entered fields and correct the request before starting a new run.",
    "access_denied": "Check your service access or ask the account owner to reconnect the affected service.",
    "not_found": "Ask the account owner to check the configured destination and access.",
    "conflict": "The document path already exists. Keep that path and ask the account owner to compare its contents and earlier results before proceeding.",
    "provider_error": "The service could not confirm the operation. Ask the account owner to check what was created before trying again.",
    "provider_unavailable": "The service is unavailable. Check the outcomes below before deciding whether a new run is safe.",
}


def uncertain_result() -> ExecutionView:
    """A lost/unreadable HTTP response is not proof that no writes happened."""
    return ExecutionView(
        "uncertain",
        "We could not confirm the result with the service.",
        "Do not submit again. Keep the document path and request details; ask the account owner to reconcile all three services first.",
        tuple(StepView(label, "uncertain") for label in STEP_LABELS.values()),
        "response_unconfirmed",
    )


def workflow_response(response: httpx.Response) -> ExecutionView:
    """Render only the documented response shapes, never arbitrary error pages."""
    try:
        payload = response.json()
        if response.status_code == 201:
            result = ProjectKickoffResult.model_validate(payload)
            steps = result.model_dump()
            state: State = "succeeded"
            message, guidance, code = (
                "Your kickoff is ready.",
                "Keep the references below for your records.",
                "",
            )
        elif response.status_code in {400, 403, 404, 409, 422, 502, 503}:
            if isinstance(payload, dict) and "failed_step" in payload:
                failure = ProjectKickoffFailureResult.model_validate(payload)
                steps = failure.steps.model_dump()
                state = (
                    "uncertain"
                    if any(s["outcome"] == "uncertain" for s in steps.values())
                    else (
                        "partially succeeded"
                        if any(s["outcome"] == "succeeded" for s in steps.values())
                        else "failed"
                    )
                )
                error = failure.error
                message = f"{STEP_LABELS.get(failure.failed_step, 'Service setup')}: {error.message}"
            else:
                error = WorkflowErrorResponse.model_validate(payload).error
                steps = {name: {"outcome": "not_attempted"} for name in STEP_LABELS}
                state, message = "failed", error.message
            code = error.code.value if isinstance(error.code, ErrorCode) else error.code
            guidance = GUIDANCE.get(
                code, "Ask the account owner to investigate before starting a new run."
            )
            if any(s["outcome"] in {"succeeded", "uncertain"} for s in steps.values()):
                guidance += " Earlier work is not rolled back. Do not replay the workflow; retain the references and reconcile first."
        else:
            return uncertain_result()
        views = []
        for name, label in STEP_LABELS.items():
            step = steps[name]
            details = step.get("event", step.get("document", step.get("issue", {})))
            views.append(
                StepView(
                    label,
                    step["outcome"].replace("_", " "),
                    {
                        key: str(value)
                        for key, value in details.items()
                        if value is not None
                    },
                )
            )
        return ExecutionView(state, message, guidance, tuple(views), code)
    except (ValueError, ValidationError):
        return uncertain_result()


class WorkflowClient(Protocol):
    """The interface calls Team 2's API rather than executing workflow code."""

    async def kickoff(self, request: ProjectKickoffRequest) -> ExecutionView: ...


class HTTPWorkflowClient:
    """One non-retrying HTTP request to the configured Team 2 API."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        url = urlsplit(base_url)
        if (
            url.username
            or url.password
            or url.query
            or url.fragment
            or not url.hostname
        ):
            raise ValueError(
                "INTERFACE_API_URL must be a service URL without credentials, query or fragment"
            )
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError(
                "Use HTTPS for the API, or HTTP on loopback for local development"
            )
        self.base_url, self.token, self.transport = (
            base_url.rstrip("/"),
            token,
            transport,
        )

    async def kickoff(self, request: ProjectKickoffRequest) -> ExecutionView:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            async with httpx.AsyncClient(
                timeout=90,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/workflows/project-kickoff",
                    json=request.model_dump(),
                    headers=headers,
                )
            return workflow_response(response)
        except httpx.HTTPError:
            return uncertain_result()


@dataclass(frozen=True)
class ProposedChange:
    """Exact service-supplied action; strings are untrusted display data."""

    operation: Literal["create", "update", "delete"]
    provider: str
    target: str
    before: dict[str, str]
    after: dict[str, str]


@dataclass(frozen=True)
class Proposal:
    """Immutable proposal revision that the backend must enforce on decision."""

    id: str
    revision: str
    changes: tuple[ProposedChange, ...]


@dataclass(frozen=True)
class AgentView:
    """Agent-owned run state; the UI does not infer authorization from messages."""

    run_id: str
    state: State
    message: str
    proposal: Proposal | None = None
    result: ExecutionView | None = None
    can_request_change: bool = False


class AgentClient(Protocol):
    """Provisional adapter contract, not a claim that HTTP endpoints exist."""

    async def submit(self, message: str) -> AgentView: ...
    async def refresh(self, run_id: str) -> AgentView: ...
    async def decide(
        self,
        run_id: str,
        proposal_id: str,
        revision: str,
        decision: Decision,
        clarification: str,
    ) -> AgentView: ...


@dataclass(frozen=True)
class ConnectionView:
    """Provider status reported by the account service, without credentials."""

    provider: str
    state: Literal["connected", "disconnected", "attention", "unavailable"]
    message: str = ""


@dataclass(frozen=True)
class AccountView:
    """Verified identity/status must come from the future account adapter."""

    signed_in: bool
    label: str
    connections: tuple[ConnectionView, ...] = ()


class AccountClient(Protocol):
    """Per-browser account adapter supplied by the authentication owner."""

    async def status(self) -> AccountView: ...
    async def act(
        self, action: Literal["sign_in", "reconnect", "disconnect"], provider: str
    ) -> AccountView: ...
