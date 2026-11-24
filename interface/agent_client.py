"""HTTP adapter for the separate agent service's implemented contract."""

import json
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictStr, ValidationError

from interface.clients import (
    AgentView,
    Decision,
    Proposal,
    ProposedChange,
    State,
    validate_service_url,
)


class _AgentProposal(BaseModel):
    """Exact proposal payload published by the separate agent service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: StrictStr
    digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    tool_name: StrictStr
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    target: StrictStr
    exact_changes: dict[str, JsonValue]
    effects: tuple[str, ...]


class _AgentRun(BaseModel):
    """Fields the interface consumes from an agent run response."""

    model_config = ConfigDict(extra="allow", frozen=True)

    run_id: StrictStr
    status: Literal[
        "completed",
        "needs_clarification",
        "approval_required",
        "blocked",
        "limit_exhausted",
        "cancelled",
        "failed",
    ]
    message: StrictStr
    proposal: _AgentProposal | None = None


class _StoredAgentRun(BaseModel):
    """Durable status envelope returned by the agent run endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: dict[str, JsonValue]
    result: _AgentRun | None
    cancelled: bool


class _Cancellation(BaseModel):
    """Agent cancellation acknowledgement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: StrictStr
    cancelled: Literal[True]


class HTTPAgentClient:
    """Call the agent request/status/cancel endpoints without provider access."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        validate_service_url(base_url, "INTERFACE_AGENT_URL")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport
        self._proposals: dict[str, tuple[str, str]] = {}

    async def submit(self, message: str) -> AgentView:
        """Submit a natural-language goal without supplying identity."""
        response = await self._request(
            "POST", "/agent/requests", json_body={"goal": message}
        )
        return self._view(_validate_response(response, _AgentRun))

    async def refresh(self, run_id: str) -> AgentView:
        """Read durable agent status without rerunning model or tools."""
        response = await self._request("GET", f"/agent/runs/{quote(run_id, safe='')}")
        stored = _validate_response(response, _StoredAgentRun)
        if stored.cancelled:
            return AgentView(run_id, "cancelled", "This agent run was cancelled.")
        if stored.result is None:
            return AgentView(run_id, "preparing", "The agent run is still preparing.")
        if stored.result.run_id != run_id:
            raise httpx.DecodingError(
                "Agent status returned the wrong run", request=response.request
            )
        return self._view(stored.result)

    async def decide(
        self,
        run_id: str,
        proposal_id: str,
        digest: str,
        decision: Decision,
        clarification: str,
    ) -> AgentView:
        """Reject the exact proposal; approval/change await the execution API."""
        del clarification
        if self._proposals.get(run_id) != (proposal_id, digest):
            raise ValueError("The proposal changed; refresh before deciding")
        if decision != "reject":
            raise ValueError("Authenticated approval execution is not available")
        response = await self._request(
            "POST", f"/agent/runs/{quote(run_id, safe='')}/cancel"
        )
        cancellation = _validate_response(response, _Cancellation)
        if cancellation.run_id != run_id:
            raise httpx.DecodingError(
                "Agent cancellation returned the wrong run",
                request=response.request,
            )
        self._proposals.pop(run_id, None)
        return AgentView(run_id, "cancelled", "Proposal rejected; nothing executed.")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, JsonValue] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=False,
            transport=self.transport,
            trust_env=False,
        ) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                json=json_body,
                headers=headers,
            )
        response.raise_for_status()
        return response

    def _view(self, run: _AgentRun) -> AgentView:
        proposal = _proposal_view(run.proposal) if run.proposal is not None else None
        if proposal is not None:
            self._proposals[run.run_id] = (proposal.proposal_id, proposal.digest)
        decisions: tuple[Decision, ...] = ("reject",) if proposal is not None else ()
        return AgentView(
            run.run_id,
            _agent_state(run.status),
            run.message,
            proposal=proposal,
            available_decisions=decisions,
        )


def _validate_response[ModelType: BaseModel](
    response: httpx.Response, model: type[ModelType]
) -> ModelType:
    try:
        return model.model_validate(response.json())
    except (ValueError, ValidationError):
        raise httpx.DecodingError(
            "Agent service returned an invalid response", request=response.request
        ) from None


def _proposal_view(proposal: _AgentProposal) -> Proposal:
    changes = proposal.exact_changes
    displayed: tuple[ProposedChange, ...]
    if proposal.tool_name == "propose_project_kickoff":
        event = changes.get("event")
        event_fields = event if isinstance(event, dict) else {}
        displayed = (
            ProposedChange(
                "create",
                "Cloud Storage",
                str(changes.get("document_path", "Configured document destination")),
                {},
                {
                    "path": str(changes.get("document_path", "")),
                    "content": str(changes.get("document_content", "")),
                },
            ),
            ProposedChange(
                "create",
                "Issue Tracker",
                "Configured issue-tracker destination",
                {},
                {"title": str(changes.get("issue_title", ""))},
            ),
            ProposedChange(
                "create",
                "Calendar",
                "Configured calendar",
                {},
                {
                    key: str(event_fields.get(key, ""))
                    for key in ("title", "start", "end")
                },
            ),
        )
    else:
        displayed = (
            ProposedChange(
                _operation(proposal.method),
                "Team 2 API",
                proposal.target,
                {},
                {
                    "exact changes": json.dumps(
                        proposal.exact_changes, sort_keys=True, ensure_ascii=False
                    )
                },
            ),
        )
    return Proposal(
        proposal.proposal_id,
        proposal.digest,
        proposal.method,
        proposal.target,
        proposal.effects,
        displayed,
    )


def _operation(method: str) -> Literal["create", "update", "delete"]:
    if method == "POST":
        return "create"
    if method == "DELETE":
        return "delete"
    return "update"


def _agent_state(status: str) -> State:
    if status == "completed":
        return "succeeded"
    if status == "needs_clarification":
        return "needs clarification"
    if status == "approval_required":
        return "awaiting approval"
    if status == "cancelled":
        return "cancelled"
    return "failed"
