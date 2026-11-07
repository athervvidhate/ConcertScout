import datetime as dt
import json
from typing import Any

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import limits, ranker
from concert_scout.models import Place

models.ALLOW_MODEL_REQUESTS = False
UPCOMING = dt.date.today() + dt.timedelta(days=14)
CHICAGO = Place(name="Chicago, IL, United States of America", lat=41.8755616, lon=-87.6244212)


@pytest.fixture(autouse=True)
def fast_limiter(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(limits, "SLOT_SECONDS", 0.001)
    monkeypatch.setattr(limits, "MUSICBRAINZ_GAP", dt.timedelta(milliseconds=1))


def interpretation(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "artists": [],
        "descriptors": [],
        "tags": [],
        "place": None,
        "start": None,
        "end": None,
    }
    return fields | overrides


def model_returning(*outputs: dict[str, Any]) -> FunctionModel:
    """A model that answers each request with the next output, without any network."""
    remaining = iter(outputs)

    def respond(_: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if info.instructions == ranker.INSTRUCTIONS:
            raise RuntimeError("ranker unavailable")
        return ModelResponse(parts=[TextPart(json.dumps(next(remaining)))])

    return FunctionModel(respond)
