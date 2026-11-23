"""Product-specific tools that reach providers only through Team 2's API."""

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from calendar_contract import Event
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from agent_service.contracts import Proposal, ToolCall, ToolDefinition, ToolObservation
from app.workflows import ProjectKickoffRequest

_MAX_API_RESPONSE_BYTES = 64_000


class ToolRejectedError(ValueError):
    """A tool name or argument set failed deterministic validation."""


class ApiToolError(RuntimeError):
    """A sanitized API-service failure safe to return to the model."""

    def __init__(
        self, *, code: str, retryable: bool, status: int | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.status = status


class CalendarEventArguments(BaseModel):
    """Arguments for reading one event through Team 2's API service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: StrictStr = Field(min_length=1, max_length=1_024, pattern=r"\S")


class CalendarEventResult(BaseModel):
    """Bounded provider-independent event returned to the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Event


class ProposalResult(BaseModel):
    """Structured result of proposing, but not executing, a composed write."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal: Proposal
    execution_status: str = "not_executed_approval_required"


class ApiServiceClient(Protocol):
    """Agent-facing API operations; never a provider implementation."""

    def get_event(self, event_id: str) -> Event:
        """Read one event through the API service."""


class HttpApiServiceClient:
    """Small HTTP client for the API service's existing public contract."""

    def __init__(
        self, base_url: str, *, timeout_seconds: float, service_key: str | None = None
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AGENT_API_BASE_URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("AGENT_API_BASE_URL must not contain credentials")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._service_key = service_key

    def get_event(self, event_id: str) -> Event:
        """Retrieve one event without exposing headers or provider responses."""
        headers = {"Accept": "application/json"}
        if self._service_key is not None:
            headers["X-Service-Key"] = self._service_key
        request = Request(
            f"{self._base_url}/events/{quote(event_id, safe='')}",
            headers=headers,
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                payload = response.read(_MAX_API_RESPONSE_BYTES + 1)
        except HTTPError as error:
            raise ApiToolError(
                code="api_rejected_request",
                status=error.code,
                retryable=error.code >= 500,
            ) from None
        except (URLError, TimeoutError, OSError):
            raise ApiToolError(code="api_unavailable", retryable=True) from None
        if len(payload) > _MAX_API_RESPONSE_BYTES:
            raise ApiToolError(code="api_response_too_large", retryable=False)
        try:
            return Event.model_validate_json(payload)
        except (ValidationError, ValueError):
            raise ApiToolError(code="invalid_api_response", retryable=False) from None


@dataclass(frozen=True)
class ToolExecution:
    """Validated observation and optional write proposal from one tool call."""

    observation: ToolObservation
    proposal: Proposal | None = None


class ToolRegistry:
    """Explicit allowlist for the agent's two product-level tools."""

    def __init__(self, api: ApiServiceClient) -> None:
        self._api = api
        self._definitions = {
            "read_calendar_event": ToolDefinition(
                name="read_calendar_event",
                purpose="Read one known Calendar event by its stable identifier.",
                arguments_schema=CalendarEventArguments.model_json_schema(),
                result_schema=CalendarEventResult.model_json_schema(),
                preconditions=("The caller already knows the event identifier.",),
                effects=("Performs one read through Team 2's API service.",),
                failure_behavior=(
                    "Invalid arguments are rejected before an API call.",
                    "API failures return a sanitized structured result.",
                ),
                requires_approval=False,
            ),
            "propose_project_kickoff": ToolDefinition(
                name="propose_project_kickoff",
                purpose=(
                    "Propose the exact Calendar, Storage, and Issue Tracker changes "
                    "for one project kickoff."
                ),
                arguments_schema=ProjectKickoffRequest.model_json_schema(),
                result_schema=ProposalResult.model_json_schema(),
                preconditions=(
                    "All event, document, and issue fields are explicit and unambiguous.",
                    "The proposal has not already been approved or executed.",
                ),
                effects=(
                    "Creates no provider records.",
                    "Produces an exact digest-bound proposal for human approval.",
                    "Approved execution will use the API service's composed workflow.",
                ),
                failure_behavior=(
                    "Missing or invalid fields are rejected before any API/provider call.",
                    "Changed arguments produce a different proposal digest and need approval.",
                ),
                requires_approval=True,
            ),
        }

    def definitions(self) -> list[ToolDefinition]:
        """Return stable model-visible definitions in name order."""
        return [self._definitions[name] for name in sorted(self._definitions)]

    def execute(self, call: ToolCall) -> ToolExecution:
        """Validate and dispatch one registered call without trusting model fields."""
        if call.name not in self._definitions:
            raise ToolRejectedError("unknown_tool")
        if call.name == "read_calendar_event":
            return self._read_event(call)
        if call.name == "propose_project_kickoff":
            return self._propose_kickoff(call)
        raise AssertionError("Registered tool has no dispatcher")

    def _read_event(self, call: ToolCall) -> ToolExecution:
        try:
            arguments = CalendarEventArguments.model_validate(call.arguments)
        except ValidationError:
            raise ToolRejectedError("invalid_tool_arguments") from None
        try:
            result = CalendarEventResult(event=self._api.get_event(arguments.event_id))
        except ApiToolError as error:
            observation = ToolObservation(
                call_id=call.call_id,
                tool_name=call.name,
                outcome="failed",
                result={
                    "code": error.code,
                    "retryable": error.retryable,
                    "status": error.status,
                },
            )
            return ToolExecution(observation=observation)
        observation = ToolObservation(
            call_id=call.call_id,
            tool_name=call.name,
            outcome="succeeded",
            result=result.model_dump(mode="json"),
        )
        return ToolExecution(observation=observation)

    def _propose_kickoff(self, call: ToolCall) -> ToolExecution:
        try:
            request = ProjectKickoffRequest.model_validate(call.arguments)
        except ValidationError:
            raise ToolRejectedError("invalid_tool_arguments") from None
        exact_changes = request.model_dump(mode="json")
        digest_source = {
            "method": "POST",
            "target": "/workflows/project-kickoff",
            "changes": exact_changes,
        }
        digest = hashlib.sha256(
            json.dumps(
                digest_source, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        proposal = Proposal(
            proposal_id=f"proposal-{uuid4().hex}",
            digest=digest,
            tool_name=call.name,
            method="POST",
            target="/workflows/project-kickoff",
            exact_changes=exact_changes,
            effects=(
                "Create one storage document.",
                "Create one issue-tracker issue.",
                "Create one calendar event.",
            ),
        )
        result = ProposalResult(proposal=proposal)
        return ToolExecution(
            observation=ToolObservation(
                call_id=call.call_id,
                tool_name=call.name,
                outcome="succeeded",
                result=result.model_dump(mode="json"),
            ),
            proposal=proposal,
        )
