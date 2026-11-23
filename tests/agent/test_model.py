"""The real model adapter keeps transport/provider details behind the model protocol."""

import json
from unittest.mock import patch

import pytest

from agent_service.contracts import ModelContext
from agent_service.model import ModelClientError, OpenAIResponsesModel, PROMPT_VERSION
from agent_service.tools import ToolRegistry
from tests.agent.conftest import ControlledApi


class ControlledResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self._payload = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "ControlledResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self._payload


def context() -> ModelContext:
    return ModelContext(
        goal="Prepare a kickoff",
        conversation=[],
        tools=ToolRegistry(ControlledApi()).definitions(),
        observations=[],
        prompt_version=PROMPT_VERSION,
    )


def response_body(text: str) -> dict[str, object]:
    return {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
    }


def test_openai_adapter_sends_structured_context_and_parses_decision() -> None:
    model = OpenAIResponsesModel(
        api_key="secret-model-key",
        model="controlled-model",
        timeout_seconds=2,
    )
    body = response_body(
        json.dumps(
            {
                "action": "clarification",
                "message": "Which project?",
                "tool_call": None,
            }
        )
    )
    with patch(
        "agent_service.model.urlopen", return_value=ControlledResponse(body)
    ) as send:
        decision = model.decide(context())

    request = send.call_args.args[0]
    payload = json.loads(request.data)
    assert request.get_header("Authorization") == "Bearer secret-model-key"
    assert "secret-model-key" not in json.dumps(payload)
    assert payload["model"] == "controlled-model"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert decision.action == "clarification"
    assert decision.usage.total_tokens == 30


@pytest.mark.parametrize("text", ["not-json", "{}"])
def test_invalid_real_model_output_is_sanitized(text: str) -> None:
    model = OpenAIResponsesModel(
        api_key="secret", model="controlled", timeout_seconds=2
    )
    with patch(
        "agent_service.model.urlopen",
        return_value=ControlledResponse(response_body(text)),
    ):
        with pytest.raises(ModelClientError) as caught:
            model.decide(context())

    assert caught.value.code == "invalid_model_response"
    assert caught.value.retryable is False


def test_model_endpoint_must_be_https() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAIResponsesModel(
            api_key="secret",
            model="controlled",
            timeout_seconds=2,
            endpoint="http://model.example.test/v1/responses",
        )
