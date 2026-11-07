"""A named area wider than a city stays that area from the interpreter to Ticketmaster."""

import datetime as dt
from typing import Any

import httpx
from fakeredis import FakeAsyncRedis
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import interpreter, pool
from concert_scout.models import MAX_RADIUS_MILES, Place
from concert_scout.sources import geocoder, ticketmaster

TODAY = dt.date(2026, 11, 6)
NOW = dt.datetime(2026, 11, 6, 12, tzinfo=dt.UTC)


def model_answering(**fields: Any) -> FunctionModel:
    import json

    defaults: dict[str, Any] = {
        "artists": [],
        "descriptors": [],
        "tags": [],
        "genres": [],
        "place": None,
        "region": None,
        "radius_miles": None,
        "start": None,
        "end": None,
    }
    answer = defaults | fields

    def respond(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(answer))])

    return FunctionModel(respond)


async def test_a_region_keeps_its_name_center_and_reach() -> None:
    read = await interpreter.interpret(
        "calvin harris in southern california",
        TODAY,
        model_answering(
            place="Los Angeles, California, United States",
            region="Southern California",
            radius_miles=150,
        ),
    )
    assert (read.place, read.region, read.radius_miles) == (
        "Los Angeles, California, United States",
        "Southern California",
        150,
    )


async def test_a_wild_radius_is_capped_and_a_radius_needs_a_place() -> None:
    wide = await interpreter.interpret(
        "x", TODAY, model_answering(place="Chicago", region="Everywhere", radius_miles=9000)
    )
    assert wide.radius_miles == MAX_RADIUS_MILES
    alone = await interpreter.interpret(
        "x", TODAY, model_answering(region="Somewhere", radius_miles=100)
    )
    assert (alone.region, alone.radius_miles) == (None, None)


def test_a_low_confidence_geocoder_guess_is_not_a_place() -> None:
    guess = {
        "formatted": "Southern Concord, Concord, CA",
        "lat": 37.9,
        "lon": -122.0,
        "result_type": "suburb",
        "rank": {"confidence": 0},
    }
    found = guess | {"formatted": "Los Angeles, CA", "rank": {"confidence": 1}}
    places = geocoder.parse_places({"results": [guess, found]})
    assert [p.name for p in places] == ["Los Angeles, CA"]


async def test_the_pool_asks_ticketmaster_for_the_region_and_caches_it_apart() -> None:
    radii: list[str] = []

    def source(request: httpx.Request) -> httpx.Response:
        radii.append(request.url.params["radius"])
        return httpx.Response(200, json={"page": {"totalElements": 0}})

    redis = FakeAsyncRedis()
    city = Place(name="Los Angeles", lat=34.05, lon=-118.24)
    region = city.model_copy(update={"radius_miles": 150})
    day = dt.timedelta(days=1)
    async with ticketmaster.make_client("key", httpx.MockTransport(source)) as client:
        await pool.find_concerts(client, redis, city, [], TODAY + day, TODAY + day, NOW)
        await pool.find_concerts(client, redis, region, [], TODAY + day, TODAY + day, NOW)
    assert radii == [str(ticketmaster.RADIUS_MILES), "150"]
