import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from concert_scout.app import create_app
from concert_scout.config import Settings
from tests.conftest import tm_body, tm_record

ALLOWED_ORIGIN = "http://localhost:3000"

Handler = Callable[[httpx.Request], httpx.Response]


def ticketmaster_returns(body: dict[str, Any]) -> Handler:
    return lambda _: httpx.Response(200, json=body)


def api_for(handler: Handler) -> httpx.AsyncClient:
    settings = Settings(tm_key=SecretStr("test-key"), cors_origins=[ALLOWED_ORIGIN])
    app = create_app(settings, httpx.MockTransport(handler))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    async with api_for(ticketmaster_returns(tm_body(tm_record()))) as client:
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


async def test_search_streams_status_then_poster_then_done(api: httpx.AsyncClient) -> None:
    response = await api.post("/search", json={"city": "  Chicago "})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "poster", "done"]
    assert events[0][1] == {"step": "pool", "message": "Looking for Concerts in Chicago"}
    assert events[1][1]["recommendations"][0]["concert"] == {
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
    assert events[2][1] == {}


async def test_missing_facts_are_left_out_of_the_stream() -> None:
    record = tm_record()
    del record["priceRanges"]
    record["dates"]["start"]["timeTBA"] = True

    async with api_for(ticketmaster_returns(tm_body(record))) as api:
        response = await api.post("/search", json={"city": "Chicago"})

    concert = parse_sse(response.text)[1][1]["recommendations"][0]["concert"]
    assert "time" not in concert
    assert "price" not in concert


async def test_a_city_with_no_listings_streams_an_empty_poster() -> None:
    async with api_for(ticketmaster_returns(tm_body())) as api:
        response = await api.post("/search", json={"city": "Nowhere"})

    assert parse_sse(response.text)[1] == ("poster", {"recommendations": []})


async def test_a_ticketmaster_failure_streams_a_safe_error() -> None:
    async with api_for(lambda _: httpx.Response(500)) as api:
        response = await api.post("/search", json={"city": "Chicago"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "error", "done"]
    assert events[1][1] == {
        "code": "ticketmaster_unavailable",
        "message": "Ticketmaster is not responding. Try again in a minute.",
    }
    assert "test-key" not in response.text


@pytest.mark.parametrize("body", [{}, {"city": "   "}, {"city": "x" * 501}])
async def test_an_invalid_search_gets_a_code_and_message(
    api: httpx.AsyncClient, body: dict[str, str]
) -> None:
    response = await api.post("/search", json=body)

    assert response.status_code == 422
    assert response.json() == {"code": "invalid_search", "message": "Enter a city."}


async def test_cors_allows_only_listed_origins(api: httpx.AsyncClient) -> None:
    allowed = await api.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    refused = await api.get("/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-origin" not in refused.headers
