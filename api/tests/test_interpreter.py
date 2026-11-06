import datetime as dt
import json
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from concert_scout.interpreter import MODEL_NAME, Interpretation, InterpreterError, interpret
from tests.conftest import interpretation, model_returning

TODAY = dt.date(2026, 11, 5)
KHRUANGBIN = "Something like Khruangbin in Chicago, next two weekends"


async def test_interpret_returns_the_models_structured_output() -> None:
    model = model_returning(
        interpretation(
            artists=["Khruangbin"], place="Chicago", start="2026-11-06", end="2026-11-15"
        )
    )

    result = await interpret(KHRUANGBIN, TODAY, model)

    assert result == Interpretation(
        artists=["Khruangbin"],
        descriptors=[],
        tags=[],
        place="Chicago",
        start=dt.date(2026, 11, 6),
        end=dt.date(2026, 11, 15),
    )


async def test_the_prompt_gets_todays_date_from_code_and_the_agent_has_no_tools() -> None:
    seen: list[AgentInfo] = []

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        return ModelResponse(parts=[TextPart(json.dumps(interpretation()))])

    await interpret(KHRUANGBIN, TODAY, FunctionModel(respond))

    assert seen[0].instructions is not None
    assert "Today is Thursday, 2026-11-05." in seen[0].instructions
    assert seen[0].function_tools == []
    assert seen[0].output_tools == []


async def test_dates_in_the_wrong_order_are_sent_back_to_the_model() -> None:
    model = model_returning(
        interpretation(start="2026-11-15", end="2026-11-06"),
        interpretation(start="2026-11-06", end="2026-11-15"),
    )

    result = await interpret(KHRUANGBIN, TODAY, model)

    assert result.start == dt.date(2026, 11, 6)


async def test_a_model_that_never_answers_properly_is_an_interpreter_error() -> None:
    bad = interpretation(start="2026-11-15", end="2026-11-06")

    with pytest.raises(InterpreterError) as caught:
        await interpret(KHRUANGBIN, TODAY, model_returning(bad, bad, bad))

    assert "Khruangbin" not in str(caught.value)


def anthropic_model(handler: Any) -> AnthropicModel:
    client = anthropic.AsyncAnthropic(
        api_key="test-key", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    )
    return AnthropicModel(MODEL_NAME, provider=AnthropicProvider(anthropic_client=client))


async def test_the_request_to_anthropic_is_haiku_with_a_schema_and_no_tools() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": MODEL_NAME,
                "content": [{"type": "text", "text": json.dumps(interpretation(place="Chicago"))}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10},
            },
        )

    with models.override_allow_model_requests(True):
        result = await interpret("Chicago", TODAY, anthropic_model(handler))

    assert result.place == "Chicago"
    body = bodies[0]
    assert body["model"] == "claude-haiku-5-5"
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "tools" not in body
    assert "temperature" not in body


async def test_a_request_anthropic_refuses_is_an_interpreter_error() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"type": "error"})

    with models.override_allow_model_requests(True), pytest.raises(InterpreterError):
        await interpret("Chicago", TODAY, anthropic_model(handler))


async def test_common_shorthand_is_normalized_without_another_model_call() -> None:
    result = await interpret(
        "UKG in SF",
        TODAY,
        model_returning(interpretation(descriptors=["UKG"], tags=["ukg"], place="SF")),
    )
    assert result.place == "San Francisco, California, United States"
    assert "uk garage" in result.tags
