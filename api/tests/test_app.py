"""API contracts: real routing/pipeline/assembly, typed adapter seams, no vendor JSON fakes."""

import datetime as dt
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic_ai.usage import RunUsage
from redis.exceptions import ConnectionError as RedisConnectionError

from concert_scout import clock, limits, pipeline, pool
from concert_scout.app import create_app
from concert_scout.interpreter import InterpreterError
from concert_scout.sources import geocoder, ticketmaster
from concert_scout.telemetry import record_usage
from tests.contracts import (
    CONCERTS,
    PLACE,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)

TOKEN = "test-token"


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def api_for(redis: FakeAsyncRedis | None = None, **settings: Any) -> httpx.AsyncClient:
    app = create_app(
        settings_with(**settings),
        httpx.MockTransport(forbidden_http),
        redis if redis is not None else FakeAsyncRedis(),
        contract_model(),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


@pytest.fixture(autouse=True)
def domain_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    async with api_for() as client:
        yield client


async def test_sse_terminates_and_every_fact_comes_from_its_source(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/search", json={"text": "UKG in SF", "token": TOKEN, "time_zone": "UTC"}
    )
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert events[-1] == ("done", {})
    assert sum(name == "poster" for name, _ in events) == 1
    data = dict(events)
    assert data["interpreted"]["place"].startswith("San Francisco")
    source = {c.id: c.model_dump(mode="json", exclude_none=True) for c in CONCERTS}
    picks = data["poster"]["recommendations"]
    assert [p["concert"]["id"] for p in picks] == ["contract-one", "contract-two"]
    assert picks[0]["also"] == [source["contract-three"]]
    for pick in picks:
        assert pick["concert"] == source[pick["concert"]["id"]]
    assert "price" not in picks[1]["concert"] and "time" not in picks[1]["concert"]


async def test_a_search_with_no_place_uses_the_shared_location(api: httpx.AsyncClient) -> None:
    near = {"lat": 32.7, "lon": -117.1}
    response = await api.post(
        "/search", json={"text": "rap near me", "token": TOKEN, "time_zone": "UTC", "near": near}
    )
    data = dict(parse_sse(response.text))
    assert "place" not in data["interpreted"]
    assert len(data["poster"]["recommendations"]) == 2
    place = cast(AsyncMock, pool.find_concerts).call_args.args[2]
    assert (place.lat, place.lon) == (32.7, -117.1)
    cast(AsyncMock, geocoder.geocode).assert_not_called()


async def test_a_typed_place_beats_the_shared_location(api: httpx.AsyncClient) -> None:
    near = {"lat": 32.7, "lon": -117.1}
    await api.post(
        "/search", json={"text": "UKG in SF", "token": TOKEN, "time_zone": "UTC", "near": near}
    )
    assert cast(AsyncMock, pool.find_concerts).call_args.args[2] == PLACE


async def test_a_style_with_no_place_asks_for_one(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/search", json={"text": "rap near me", "token": TOKEN, "time_zone": "UTC"}
    )
    assert dict(parse_sse(response.text))["error"]["code"] == "needs_place"


async def test_impossible_coordinates_are_refused(api: httpx.AsyncClient) -> None:
    near = {"lat": 300, "lon": 0}
    response = await api.post(
        "/search", json={"text": "rap", "token": TOKEN, "time_zone": "UTC", "near": near}
    )
    assert response.status_code == 422


async def test_artist_profile_survives_without_a_source(api: httpx.AsyncClient) -> None:
    response = await api.get("/artist", params={"name": "Son Volt"})
    assert response.status_code == 200
    assert response.json() == {
        "profiles": [{"name": "Son Volt", "tags": [], "top_tracks": [], "similar": []}]
    }


async def test_a_pipeline_failure_finishes_with_a_safe_error(
    api: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline.pool,
        "find_concerts",
        AsyncMock(side_effect=ticketmaster.TicketmasterError("status 503")),
    )
    response = await api.post(
        "/search", json={"text": "UKG in SF", "token": TOKEN, "time_zone": "UTC"}
    )
    events = parse_sse(response.text)
    assert events[-1] == ("done", {})
    assert dict(events)["error"]["code"] == "ticketmaster_unavailable"
    assert "unused-test-key" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": " "},
        {"text": "x" * 501},
        {"text": "SF"},
        {"text": "SF", "token": TOKEN, "time_zone": "UTC", "taste": ["x"] * 101},
    ],
)
async def test_invalid_input_is_refused_before_any_work(
    api: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    response = await api.post("/search", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_search"


async def test_origin_policy_is_enforced_on_the_server(api: httpx.AsyncClient) -> None:
    allowed = await api.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = await api.post(
        "/search",
        json={"text": "SF", "token": TOKEN, "time_zone": "UTC"},
        headers={"Origin": "https://evil.example"},
    )
    assert denied.status_code == 403 and denied.json()["code"] == "origin_refused"
    assert "access-control-allow-origin" not in denied.headers


async def test_a_failed_bot_check_never_reaches_the_pipeline(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    interpret = AsyncMock(side_effect=AssertionError("must not run"))
    monkeypatch.setattr(pipeline, "interpret", interpret)
    response = await api.post("/search", json={"text": "SF", "token": "reject", "time_zone": "UTC"})
    assert response.status_code == 403 and response.json()["code"] == "bot_check_failed"
    interpret.assert_not_awaited()


async def test_rate_limits_are_per_client_and_ignore_untrusted_forwarding() -> None:
    async with api_for(searches_per_hour=1, client_ip_header="x-real-ip") as api:
        body = {"text": "SF", "token": TOKEN, "time_zone": "UTC"}
        assert (
            await api.post("/search", json=body, headers={"x-real-ip": "1.1.1.1"})
        ).status_code == 200
        denied = await api.post(
            "/search", json=body, headers={"x-real-ip": "1.1.1.1", "x-forwarded-for": "3.3.3.3"}
        )
        other = await api.post("/search", json=body, headers={"x-real-ip": "2.2.2.2"})
    assert denied.status_code == 429 and denied.json()["retry_after"] > 0
    assert other.status_code == 200


@pytest.mark.parametrize("trusted_header", [None, "x-forwarded-for"])
async def test_forging_a_forwarding_chain_cannot_reset_the_limit(
    trusted_header: str | None,
) -> None:
    async with api_for(searches_per_hour=1, client_ip_header=trusted_header) as api:
        body = {"text": "SF", "token": TOKEN, "time_zone": "UTC"}
        await api.post("/search", json=body, headers={"x-forwarded-for": "fake-one, 1.1.1.1"})
        denied = await api.post(
            "/search", json=body, headers={"x-forwarded-for": "fake-two, 1.1.1.1"}
        )
    assert denied.status_code == 429


class BrokenRedis(FakeAsyncRedis):
    async def execute_command(self, *_: object, **__: object) -> None:
        raise RedisConnectionError("down")


@pytest.mark.parametrize("stop", ["spend", "kill", "redis"])
async def test_costly_search_fails_closed(stop: str) -> None:
    redis = BrokenRedis() if stop == "redis" else FakeAsyncRedis()
    if stop == "spend":
        await limits.record_spend(redis, limits.DAILY_SPEND)
    async with api_for(redis, search_enabled=stop != "kill") as api:
        search = await api.post("/search", json={"text": "SF", "token": TOKEN, "time_zone": "UTC"})
    assert search.status_code == 503
    assert (
        search.json()["code"]
        == {"spend": "budget_reached", "kill": "search_off", "redis": "limits_unavailable"}[stop]
    )


async def test_failed_model_usage_still_counts_toward_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def costly(*_: Any) -> Any:
        record_usage(RunUsage(input_tokens=100, output_tokens=20, cost=Decimal("0.25")))
        raise InterpreterError("failed after spending")

    monkeypatch.setattr(pipeline, "interpret", costly)
    redis = FakeAsyncRedis()
    async with api_for(redis) as api:
        await api.post("/search", json={"text": "SF", "token": TOKEN, "time_zone": "UTC"})
    assert await redis.get(f"spend:day:{dt.datetime.now(dt.UTC).date()}") == b"250000"


async def test_security_headers_cover_errors_too(api: httpx.AsyncClient) -> None:
    response = await api.get("/missing")
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "max-age" in response.headers["strict-transport-security"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


async def test_an_empty_poster_looks_elsewhere_with_one_lookup(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = CONCERTS[0].model_copy(update={"city": "Eugene", "region": "OR"})
    here = CONCERTS[1].model_copy(update={"city": PLACE.name.split(",")[0].upper()})
    lookup = AsyncMock(return_value=[other, here])
    monkeypatch.setattr(pool, "find_elsewhere", lookup)
    response = await api.post("/search", json={"text": "empty", "token": TOKEN, "time_zone": "UTC"})
    events = [event for event, _ in parse_sse(response.text)]
    assert events[-3:] == ["poster", "elsewhere", "done"]
    elsewhere = dict(parse_sse(response.text))["elsewhere"]
    assert elsewhere["keyword"] == "uk garage"
    assert [c["city"] for c in elsewhere["concerts"]] == ["Eugene"]
    lookup.assert_awaited_once()


async def test_a_full_poster_never_looks_elsewhere(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = AsyncMock()
    monkeypatch.setattr(pool, "find_elsewhere", lookup)
    await api.post("/search", json={"text": "UKG in SF", "token": TOKEN, "time_zone": "UTC"})
    lookup.assert_not_awaited()


async def test_a_failed_elsewhere_lookup_still_finishes_the_search(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = AsyncMock(side_effect=ticketmaster.TicketmasterError("down"))
    monkeypatch.setattr(pool, "find_elsewhere", lookup)
    response = await api.post("/search", json={"text": "empty", "token": TOKEN, "time_zone": "UTC"})
    events = [event for event, _ in parse_sse(response.text)]
    assert events[-2:] == ["poster", "done"] and "error" not in events


@pytest.mark.parametrize(
    ("zone", "day"),
    [
        ("Pacific/Pago_Pago", dt.date(2026, 11, 6)),
        ("Pacific/Kiritimati", dt.date(2026, 11, 7)),
        ("Not/A_Zone", dt.date(2026, 11, 7)),
    ],
)
async def test_a_search_reads_today_in_the_visitors_own_zone(
    api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, zone: str, day: dt.date
) -> None:
    moment = dt.datetime(2026, 11, 7, 3, tzinfo=dt.UTC)
    days: list[dt.date] = []

    class Frozen(dt.datetime):
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:
            return moment.astimezone(tz)

    async def interpret(text: str, today: dt.date, model: Any) -> None:
        days.append(today)
        raise InterpreterError("stop here")

    monkeypatch.setattr(clock.dt, "datetime", Frozen)
    monkeypatch.setattr(pipeline, "interpret", interpret)
    await api.post("/search", json={"text": "SF", "token": TOKEN, "time_zone": zone})
    assert days == [day]
