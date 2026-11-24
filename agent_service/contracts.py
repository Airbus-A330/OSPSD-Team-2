"""Provider-independent contracts for the agent loop and its HTTP boundary."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictStr,
    model_validator,
)


class ConversationMessage(BaseModel):
    """One bounded user-visible conversation message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: StrictStr = Field(min_length=1, max_length=4_000)


class AgentRequest(BaseModel):
    """Natural-language goal and bounded conversation context from an interface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: StrictStr = Field(min_length=1, max_length=4_000, pattern=r"\S")
    conversation_id: StrictStr | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    conversation: list[ConversationMessage] = Field(default_factory=list, max_length=20)


class ToolDefinition(BaseModel):
    """Model-visible contract for one narrowly scoped application tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr
    purpose: StrictStr
    arguments_schema: dict[str, JsonValue]
    result_schema: dict[str, JsonValue]
    preconditions: tuple[str, ...]
    effects: tuple[str, ...]
    failure_behavior: tuple[str, ...]
    requires_approval: bool


class ModelUsage(BaseModel):
    """Usage reported by one model call when the provider supplies it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class ToolCall(BaseModel):
    """A model-selected tool and its untrusted arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: StrictStr = Field(min_length=1, max_length=128)
    name: StrictStr = Field(min_length=1, max_length=128)
    arguments: dict[str, JsonValue]


class ModelDecision(BaseModel):
    """One inspectable model decision in the explicit loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["tool_call", "clarification", "complete", "blocked"]
    message: StrictStr = Field(min_length=1, max_length=4_000)
    tool_call: ToolCall | None = None
    usage: ModelUsage = Field(default_factory=ModelUsage)

    @model_validator(mode="after")
    def require_action_fields(self) -> "ModelDecision":
        """Require a tool call only for the tool-call action."""
        if (self.action == "tool_call") != (self.tool_call is not None):
            raise ValueError("tool_call must be present exactly for action=tool_call")
        return self


class ToolObservation(BaseModel):
    """Bounded tool feedback kept separate from trusted instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: StrictStr
    tool_name: StrictStr
    outcome: Literal["succeeded", "rejected", "failed"]
    result: dict[str, JsonValue]
    trust: Literal["untrusted_tool_data"] = "untrusted_tool_data"


class ModelContext(BaseModel):
    """Inputs supplied to a model without credentials or acting-user fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: StrictStr
    conversation: list[ConversationMessage]
    tools: list[ToolDefinition]
    observations: list[ToolObservation]
    prompt_version: StrictStr


class Proposal(BaseModel):
    """Exact write proposal that requires approval outside the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: StrictStr
    digest: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
    tool_name: StrictStr
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    target: StrictStr
    exact_changes: dict[str, JsonValue]
    effects: tuple[str, ...]


class TraceEntry(BaseModel):
    """Sanitized execution event without prompts or private reasoning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    category: Literal["model", "tool", "policy", "stop"]
    name: StrictStr
    outcome: StrictStr
    duration_ms: int = Field(ge=0)
    details: dict[str, JsonValue] = Field(default_factory=dict)


RunStatus = Literal[
    "completed",
    "needs_clarification",
    "approval_required",
    "blocked",
    "limit_exhausted",
    "cancelled",
    "failed",
]
TraceCategory = Literal["model", "tool", "policy", "stop"]


class AgentRunResult(BaseModel):
    """User-visible run result and sanitized inspection data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: StrictStr
    conversation_id: StrictStr
    status: RunStatus
    message: StrictStr
    model_provider: StrictStr
    model_version: StrictStr
    prompt_version: StrictStr
    proposal: Proposal | None = None
    trace: list[TraceEntry]
    usage: ModelUsage


class StoredRun(BaseModel):
    """Durable state needed to inspect or resume a stopped run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: AgentRequest
    result: AgentRunResult | None = None
    cancelled: bool = False
