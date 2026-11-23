"""Framework-independent bounded model/tool loop."""

from collections.abc import Callable
from dataclasses import dataclass
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue

from agent_service.contracts import (
    AgentRequest,
    AgentRunResult,
    ModelContext,
    ModelUsage,
    Proposal,
    RunStatus,
    StoredRun,
    TraceCategory,
    ToolDefinition,
    ToolObservation,
    TraceEntry,
)
from agent_service.model import ModelClient, ModelClientError, PROMPT_VERSION
from agent_service.store import RunStore
from agent_service.tools import ToolRegistry, ToolRejectedError


class AgentLimits(BaseModel):
    """Deterministic limits enforced outside the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_steps: int = Field(default=8, ge=1, le=32)
    max_duration_seconds: float = Field(default=30, gt=0, le=300)
    max_tokens: int = Field(default=20_000, ge=1)
    max_cost_usd: float | None = Field(default=None, gt=0)


@dataclass
class _RunState:
    trace: list[TraceEntry]
    observations: list[ToolObservation]
    usage: ModelUsage


class AgentService:
    """Run one bounded agent while code retains policy and dispatch authority."""

    def __init__(
        self,
        *,
        model: ModelClient,
        tools: ToolRegistry,
        store: RunStore,
        limits: AgentLimits,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._model = model
        self._tools = tools
        self._store = store
        self._limits = limits
        self._monotonic = monotonic

    def run(self, request: AgentRequest) -> AgentRunResult:
        """Run until completion, clarification, approval, policy, or a limit stops it."""
        run_id = f"run-{uuid4().hex}"
        conversation_id = request.conversation_id or f"conversation-{uuid4().hex}"
        state = _RunState(trace=[], observations=[], usage=ModelUsage())
        self._store.save(run_id, StoredRun(request=request))
        started = self._monotonic()

        for _ in range(self._limits.max_steps):
            stopped = self._pre_step_stop(
                run_id, conversation_id, request, state, started
            )
            if stopped is not None:
                return stopped
            context = ModelContext(
                goal=request.goal,
                conversation=request.conversation,
                tools=self._tools.definitions(),
                observations=state.observations,
                prompt_version=PROMPT_VERSION,
            )
            call_started = self._monotonic()
            try:
                decision = self._model.decide(context)
            except ModelClientError as error:
                self._append_trace(
                    state,
                    category="model",
                    name="model_call",
                    outcome="failed",
                    duration_ms=self._duration_ms(call_started),
                    details={"code": error.code, "retryable": error.retryable},
                )
                return self._stop(
                    run_id,
                    conversation_id,
                    request,
                    state,
                    status="failed",
                    message=(
                        "The model is temporarily unavailable; retry this request later."
                        if error.retryable
                        else "The model returned an unusable response; revise the request."
                    ),
                )
            state.usage = _add_usage(state.usage, decision.usage)
            self._append_trace(
                state,
                category="model",
                name="model_call",
                outcome=decision.action,
                duration_ms=self._duration_ms(call_started),
                details={"model_version": self._model.model_version},
            )
            budget_stop = self._usage_stop(run_id, conversation_id, request, state)
            if budget_stop is not None:
                return budget_stop

            if decision.action == "clarification":
                return self._stop(
                    run_id,
                    conversation_id,
                    request,
                    state,
                    status="needs_clarification",
                    message=decision.message,
                )
            if decision.action == "complete":
                return self._stop(
                    run_id,
                    conversation_id,
                    request,
                    state,
                    status="completed",
                    message=decision.message,
                )
            if decision.action == "blocked":
                return self._stop(
                    run_id,
                    conversation_id,
                    request,
                    state,
                    status="blocked",
                    message=decision.message,
                )

            call = decision.tool_call
            if call is None:  # ModelDecision validation makes this unreachable.
                raise AssertionError("tool_call decision has no call")
            tool_started = self._monotonic()
            try:
                execution = self._tools.execute(call)
            except ToolRejectedError as error:
                observation = ToolObservation(
                    call_id=call.call_id,
                    tool_name=call.name,
                    outcome="rejected",
                    result={"code": str(error), "retryable": False},
                )
                state.observations.append(observation)
                self._append_trace(
                    state,
                    category="policy",
                    name="tool_validation",
                    outcome="rejected",
                    duration_ms=self._duration_ms(tool_started),
                    details={"tool_name": call.name, "code": str(error)},
                )
                continue

            state.observations.append(execution.observation)
            self._append_trace(
                state,
                category="tool",
                name=call.name,
                outcome=execution.observation.outcome,
                duration_ms=self._duration_ms(tool_started),
                details={"call_id": call.call_id},
            )
            if execution.proposal is not None:
                self._append_trace(
                    state,
                    category="policy",
                    name="write_approval",
                    outcome="approval_required",
                    duration_ms=0,
                    details={
                        "proposal_id": execution.proposal.proposal_id,
                        "proposal_digest": execution.proposal.digest,
                    },
                )
                return self._stop(
                    run_id,
                    conversation_id,
                    request,
                    state,
                    status="approval_required",
                    message="Review and approve the exact proposed changes before execution.",
                    proposal=execution.proposal,
                )

        return self._stop(
            run_id,
            conversation_id,
            request,
            state,
            status="limit_exhausted",
            message="The agent stopped after reaching its step limit.",
        )

    def cancel(self, run_id: str) -> bool:
        """Prevent further model/tool steps for a known run."""
        return self._store.cancel(run_id)

    def get_run(self, run_id: str) -> StoredRun | None:
        """Return durable state for interface status reporting."""
        return self._store.load(run_id)

    def tool_definitions(self) -> list[ToolDefinition]:
        """Return exact definitions for evaluation provenance."""
        return list(self._tools.definitions())

    def _pre_step_stop(
        self,
        run_id: str,
        conversation_id: str,
        request: AgentRequest,
        state: _RunState,
        started: float,
    ) -> AgentRunResult | None:
        if self._store.is_cancelled(run_id):
            return self._stop(
                run_id,
                conversation_id,
                request,
                state,
                status="cancelled",
                message="The run was cancelled; completed external actions are not undone.",
            )
        if self._monotonic() - started >= self._limits.max_duration_seconds:
            return self._stop(
                run_id,
                conversation_id,
                request,
                state,
                status="limit_exhausted",
                message="The agent stopped after reaching its time limit.",
            )
        return None

    def _usage_stop(
        self,
        run_id: str,
        conversation_id: str,
        request: AgentRequest,
        state: _RunState,
    ) -> AgentRunResult | None:
        if state.usage.total_tokens > self._limits.max_tokens:
            message = "The agent stopped after reaching its token limit."
        elif (
            self._limits.max_cost_usd is not None
            and state.usage.cost_usd is not None
            and state.usage.cost_usd > self._limits.max_cost_usd
        ):
            message = "The agent stopped after reaching its cost limit."
        else:
            return None
        return self._stop(
            run_id,
            conversation_id,
            request,
            state,
            status="limit_exhausted",
            message=message,
        )

    def _stop(
        self,
        run_id: str,
        conversation_id: str,
        request: AgentRequest,
        state: _RunState,
        *,
        status: RunStatus,
        message: str,
        proposal: Proposal | None = None,
    ) -> AgentRunResult:
        self._append_trace(
            state,
            category="stop",
            name="run_stopped",
            outcome=status,
            duration_ms=0,
        )
        result = AgentRunResult(
            run_id=run_id,
            conversation_id=conversation_id,
            status=status,
            message=message,
            model_provider=self._model.provider,
            model_version=self._model.model_version,
            prompt_version=PROMPT_VERSION,
            proposal=proposal,
            trace=state.trace,
            usage=state.usage,
        )
        self._store.save(
            run_id,
            StoredRun(request=request, result=result, cancelled=status == "cancelled"),
        )
        return result

    def _duration_ms(self, started: float) -> int:
        return max(0, round((self._monotonic() - started) * 1_000))

    @staticmethod
    def _append_trace(
        state: _RunState,
        *,
        category: TraceCategory,
        name: str,
        outcome: str,
        duration_ms: int,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        state.trace.append(
            TraceEntry(
                sequence=len(state.trace) + 1,
                category=category,
                name=name,
                outcome=outcome,
                duration_ms=duration_ms,
                details=details or {},
            )
        )


def _add_usage(total: ModelUsage, current: ModelUsage) -> ModelUsage:
    costs = [cost for cost in (total.cost_usd, current.cost_usd) if cost is not None]
    return ModelUsage(
        input_tokens=total.input_tokens + current.input_tokens,
        output_tokens=total.output_tokens + current.output_tokens,
        total_tokens=total.total_tokens + current.total_tokens,
        cost_usd=sum(costs) if costs else None,
    )
