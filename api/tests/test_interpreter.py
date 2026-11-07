import datetime as dt
import json

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout.interpreter import InterpreterError, interpret
from tests.conftest import interpretation, model_returning

TODAY = dt.date(2026, 11, 5)
KHRUANGBIN = "Something like Khruangbin in Chicago, next two weekends"


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


async def test_common_shorthand_is_normalized_without_another_model_call() -> None:
    result = await interpret(
        "UKG in SF",
        TODAY,
        model_returning(interpretation(descriptors=["UKG"], tags=["ukg"], place="SF")),
    )
    assert result.place == "San Francisco, California, United States"
    assert "uk garage" in result.tags
