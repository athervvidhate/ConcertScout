import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout.app import create_app
from concert_scout.config import Settings
from tests.conftest import geoapify_result, interpretation, model_returning, tm_body, tm_record

ALLOWED_ORIGIN = "http://localhost:3000"

Handler = Callable[[httpx.Request], httpx.Response]


def routed(
    ticketmaster: dict[str, Any] | None = None,
    geoapify: dict[str, Any] | None = None,
    tm_status: int = 200,
    geo_status: int = 200,
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.geoapify.com":
            return httpx.Response(geo_status, json=geoapify or {"results": [geoapify_result()]})
        return httpx.Response(tm_status, json=ticketmaster or tm_body(tm_record()))

    return handler


def api_for(handler: Handler, model: Model | None = None) -> httpx.AsyncClient:
    settings = Settings(
        tm_key=SecretStr("test-key"),
        anthropic_api_key=SecretStr("test-key"),
        geoapify_key=SecretStr("test-key"),
        cors_origins=[ALLOWED_ORIGIN],
    )
    model = model or model_returning(interpretation(place="Chicago"))
    app = create_app(settings, httpx.MockTransport(handler), FakeAsyncRedis(), model)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    async with api_for(routed()) as client:
        yield client


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_health(api: httpx.AsyncClient) -> None:
    response = await api.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_search_streams_each_step_then_the_poster() -> None:
    fields = interpretation(
        artists=["Khruangbin"], place="Chicago", start="2026-11-06", end="2026-11-15"
    )
    requests: list[httpx.Request] = []
    respond = routed()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    async with api_for(handler, model_returning(fields)) as api:
        response = await api.post(
            "/search", json={"text": "  Something like Khruangbin in Chicago, next two weekends "}
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == [
        "status",
        "interpreted",
        "status",
        "status",
        "poster",
        "done",
    ]
    assert [data["step"] for name, data in events if name == "status"] == [
        "interpret",
        "resolve",
        "pool",
    ]
    assert events[1][1] == {
        "place": "Chicago",
        "start": "2026-11-06",
        "end": "2026-11-15",
        "artists": ["Khruangbin"],
    }
    assert events[3][1] == {
        "step": "pool",
        "message": "Looking for Concerts near Chicago, IL, United States of America",
    }
    assert events[4][1]["recommendations"][0]["concert"] == {
        "id": "vvG18Z_ueUZbii",
        "name": "Khruangbin: The Ether Tour",
        "url": "https://www.ticketmaster.com/event/040064D0B6018B2C",
        "artists": ["Khruangbin", "Men I Trust"],
        "date": "2026-11-20",
        "time": "19:30:00",
        "venue": "The Salt Shed",
        "city": "Chicago",
        "region": "IL",
        "price": {"min": 45.5, "max": 120.0, "currency": "USD"},
    }
    assert events[5][1] == {}
    ticketmaster_params = requests[1].url.params
    assert ticketmaster_params["geoPoint"] == "dp3wnp1yf"
    assert ticketmaster_params["localStartDateTime"] == "2026-11-06T00:00:00,2026-11-15T23:59:59"


async def test_missing_facts_are_left_out_of_the_stream() -> None:
    record = tm_record()
    del record["priceRanges"]
    record["dates"]["start"]["timeTBA"] = True

    async with api_for(routed(tm_body(record))) as api:
        response = await api.post("/search", json={"text": "Chicago"})

    concert = dict(parse_sse(response.text))["poster"]["recommendations"][0]["concert"]
    assert "time" not in concert
    assert "price" not in concert


async def test_a_missing_place_or_date_is_left_out_of_the_interpreted_event() -> None:
    model = model_returning(interpretation(artists=["Khruangbin"]))
    async with api_for(routed(), model) as api:
        response = await api.post("/search", json={"text": "Khruangbin"})

    assert dict(parse_sse(response.text))["interpreted"] == {"artists": ["Khruangbin"]}


async def test_a_place_with_no_listings_streams_an_empty_poster() -> None:
    async with api_for(routed(tm_body())) as api:
        response = await api.post("/search", json={"text": "Nowhere"})

    assert dict(parse_sse(response.text))["poster"] == {"recommendations": []}


async def test_a_search_with_no_taste_and_no_place_asks_for_one_and_calls_no_source() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no source should be called")

    async with api_for(handler, model_returning(interpretation())) as api:
        response = await api.post("/search", json={"text": "hello there"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "interpreted", "error", "done"]
    assert events[2][1] == {
        "code": "needs_taste_or_place",
        "message": "Tell us an Artist, a style or a place.",
    }


async def test_a_taste_with_no_place_asks_for_a_place() -> None:
    model = model_returning(interpretation(descriptors=["dreamy guitar"]))
    async with api_for(routed(), model) as api:
        response = await api.post("/search", json={"text": "dreamy guitar"})

    assert dict(parse_sse(response.text))["error"]["code"] == "needs_place"


async def test_a_place_the_geocoder_cannot_find_says_so() -> None:
    model = model_returning(interpretation(place="Atlantis"))
    async with api_for(routed(geoapify={"results": []}), model) as api:
        response = await api.post("/search", json={"text": "Atlantis"})

    events = parse_sse(response.text)
    assert [name for name, _ in events][-2:] == ["error", "done"]
    assert events[-2][1] == {
        "code": "place_not_found",
        "message": "We could not find Atlantis. Check the spelling.",
    }


async def test_an_interpreter_failure_streams_a_safe_error() -> None:
    def fail(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("not json")])

    async with api_for(routed(), FunctionModel(fail)) as api:
        response = await api.post("/search", json={"text": "my secret Search"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "error", "done"]
    assert events[1][1]["code"] == "interpreter_unavailable"
    assert "my secret Search" not in response.text


async def test_a_geocoder_failure_streams_a_safe_error() -> None:
    async with api_for(routed(geo_status=500)) as api:
        response = await api.post("/search", json={"text": "Chicago"})

    events = parse_sse(response.text)
    assert dict(events)["error"]["code"] == "geocoder_unavailable"
    assert "test-key" not in response.text


async def test_a_ticketmaster_failure_streams_a_safe_error() -> None:
    async with api_for(routed(tm_status=500)) as api:
        response = await api.post("/search", json={"text": "Chicago"})

    events = parse_sse(response.text)
    assert [name for name, _ in events][-2:] == ["error", "done"]
    assert dict(events)["error"] == {
        "code": "ticketmaster_unavailable",
        "message": "Ticketmaster is not responding. Try again in a minute.",
    }
    assert "test-key" not in response.text


@pytest.mark.parametrize("body", [{}, {"text": "   "}, {"text": "x" * 501}])
async def test_an_invalid_search_gets_a_code_and_message(
    api: httpx.AsyncClient, body: dict[str, str]
) -> None:
    response = await api.post("/search", json=body)

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_search",
        "message": "Tell us an Artist, a style or a place.",
    }


async def test_cors_allows_only_listed_origins(api: httpx.AsyncClient) -> None:
    allowed = await api.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    refused = await api.get("/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-origin" not in refused.headers
