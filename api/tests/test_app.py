import datetime as dt
import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage
from redis.exceptions import ConnectionError as RedisConnectionError

from concert_scout import limits, pipeline
from concert_scout.app import create_app
from concert_scout.config import Settings
from concert_scout.interpreter import InterpreterError
from concert_scout.matching import SHORTLIST_SIZE
from concert_scout.telemetry import record_usage
from tests.conftest import (
    CHICAGO,
    TYLER_MBID,
    UPCOMING,
    geoapify_result,
    interpretation,
    lastfm_similar,
    lb_metadata,
    lb_similar,
    mb_artist,
    model_returning,
    tm_body,
    tm_record,
    upcoming_record,
)

TOKEN = "turnstile-token"
ALLOWED_ORIGIN = "http://localhost:3000"

Handler = Callable[[httpx.Request], httpx.Response]


def routed(
    ticketmaster: dict[str, Any] | None = None,
    geoapify: dict[str, Any] | None = None,
    tm_status: int = 200,
    geo_status: int = 200,
    musicbrainz: dict[str, Any] | None = None,
    similar: list[dict[str, Any]] | None = None,
    tags: list[dict[str, Any]] | None = None,
    listenbrainz_status: int = 200,
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.geoapify.com":
            return httpx.Response(geo_status, json=geoapify or {"results": [geoapify_result()]})
        if request.url.host == "musicbrainz.org":
            return httpx.Response(200, json=musicbrainz or {"artists": []})
        if request.url.host == "labs.api.listenbrainz.org":
            return httpx.Response(listenbrainz_status, json=similar or [])
        if request.url.host == "api.listenbrainz.org":
            return httpx.Response(listenbrainz_status, json=tags or [])
        return httpx.Response(tm_status, json=ticketmaster or tm_body(upcoming_record()))

    return handler


def settings_with(**overrides: Any) -> Settings:
    return Settings(
        tm_key=SecretStr("test-key"),
        anthropic_api_key=SecretStr("test-key"),
        geoapify_key=SecretStr("test-key"),
        cors_origins=[ALLOWED_ORIGIN],
        **overrides,
    )


def bot_check_passes(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"success": True})


def api_for(
    handler: Handler,
    model: Model | None = None,
    redis: FakeAsyncRedis | None = None,
    lastfm_key: str | None = None,
    settings: Settings | None = None,
    bot_check: Handler = bot_check_passes,
) -> httpx.AsyncClient:
    def route(request: httpx.Request) -> httpx.Response:
        return (bot_check if request.url.host == "challenges.cloudflare.com" else handler)(request)

    if lastfm_key:
        settings = settings_with(lastfm_key=SecretStr(lastfm_key))
    settings = settings or settings_with()
    model = model or model_returning(interpretation(place="Chicago"))
    app = create_app(settings, httpx.MockTransport(route), redis or FakeAsyncRedis(), model)
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
        artists=["Khruangbin"], place="Chicago", start=str(UPCOMING), end=str(UPCOMING)
    )
    requests: list[httpx.Request] = []
    respond = routed()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    async with api_for(handler, model_returning(fields)) as api:
        response = await api.post(
            "/search",
            json={
                "text": "  Something like Khruangbin in Chicago, next two weekends ",
                "token": TOKEN,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == [
        "status",
        "interpreted",
        "status",
        "status",
        "status",
        "pool",
        "status",
        "candidates",
        "status",
        "poster",
        "done",
    ]
    assert [data["step"] for name, data in events if name == "status"] == [
        "interpret",
        "resolve",
        "resolve",
        "pool",
        "match",
        "rank",
    ]
    assert events[1][1] == {
        "place": "Chicago",
        "start": str(UPCOMING),
        "end": str(UPCOMING),
        "artists": ["Khruangbin"],
    }
    assert events[3][1]["message"] == "Finding Artists like Khruangbin"
    assert events[4][1] == {
        "step": "pool",
        "message": "Looking for Concerts near Chicago, IL, United States of America",
    }
    assert events[5][1] == {"total": 1}
    assert events[7][1] == {"names": ["Khruangbin"], "total": 1}
    assert events[9][1]["recommendations"][0]["concert"] == {
        "id": "vvG18Z_ueUZbii",
        "name": "Khruangbin: The Ether Tour",
        "url": "https://www.ticketmaster.com/event/040064D0B6018B2C",
        "artists": [{"name": "Khruangbin"}, {"name": "Men I Trust"}],
        "date": str(UPCOMING),
        "time": "19:30:00",
        "venue": "The Salt Shed",
        "city": "Chicago",
        "region": "IL",
        "price": {"min": 45.5, "max": 120.0, "currency": "USD"},
    }
    assert events[10][1] == {}
    params = [r.url.params for r in requests if r.url.host == "app.ticketmaster.com"]
    assert sorted("keyword" in p for p in params) == [False, True]
    assert all(p["geoPoint"] == "dp3wn" for p in params)


async def test_a_repeat_search_makes_no_ticketmaster_calls() -> None:
    fields = interpretation(artists=["Khruangbin"], place="Chicago")
    ticketmaster_calls = 0
    respond = routed()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ticketmaster_calls
        ticketmaster_calls += request.url.host == "app.ticketmaster.com"
        return respond(request)

    async with api_for(handler, model_returning(fields, fields)) as api:
        first = await api.post("/search", json={"text": "Khruangbin in Chicago", "token": TOKEN})
        calls_after_first = ticketmaster_calls
        second = await api.post("/search", json={"text": "Khruangbin in Chicago", "token": TOKEN})

    assert calls_after_first == 8  # seven months of the default window and one Artist
    assert ticketmaster_calls == calls_after_first
    assert dict(parse_sse(second.text))["poster"] == dict(parse_sse(first.text))["poster"]


async def test_the_shortlist_cuts_the_pool_while_the_pool_event_counts_everything() -> None:
    records = [concert_of(str(n), attraction(f"Artist {n}", f"mbid-{n}")) for n in range(120)]

    async with api_for(routed(tm_body(*records))) as api:
        response = await api.post("/search", json={"text": "Chicago", "token": TOKEN})

    events = dict(parse_sse(response.text))
    assert events["pool"] == {"total": 120}
    assert events["candidates"]["total"] == SHORTLIST_SIZE
    assert len(events["poster"]["recommendations"]) == 8


async def test_a_search_with_no_taste_calls_no_similarity_source() -> None:
    hosts: set[str] = set()
    respond = routed()

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.add(request.url.host)
        return respond(request)

    async with api_for(handler) as api:
        response = await api.post("/search", json={"text": "Chicago", "token": TOKEN})

    assert hosts == {"api.geoapify.com", "app.ticketmaster.com"}
    steps = [data["step"] for name, data in parse_sse(response.text) if name == "status"]
    assert "match" not in steps
    assert "rank" not in steps
    assert len(dict(parse_sse(response.text))["poster"]["recommendations"]) == 0


def attraction(name: str, mbid: str | None = None, subgenre: str | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {"name": name}
    if mbid:
        fields["externalLinks"] = {"musicbrainz": [{"id": mbid}]}
    if subgenre:
        fields["classifications"] = [{"subGenre": {"name": subgenre}}]
    return fields


def concert_of(id: str, *attractions: dict[str, Any]) -> dict[str, Any]:
    record = upcoming_record(id=id, name=f"Concert {id}")
    record["_embedded"]["attractions"] = list(attractions)
    return record


def poster_ids(events: list[tuple[str, Any]]) -> list[str]:
    return [r["concert"]["id"] for r in dict(events)["poster"]["recommendations"]]


TYLER_SEARCH = interpretation(artists=["Tyler Childers"], place="Chicago")
TYLER_POOL = tm_body(
    concert_of("radio", attraction("Generic Radio Act", "radio-mbid")),
    concert_of("tagged", attraction("The Jayhawks", "jayhawks-mbid")),
    concert_of("similar", attraction("Hiss Golden Messenger", "hiss-mbid")),
    concert_of("by-name", attraction("Colter Wall")),
    concert_of("unrelated", attraction("Unrelated")),
)


async def test_a_taste_orders_the_shortlist_and_fills_candidates() -> None:
    similar = lb_similar(("Hiss Golden Messenger", "hiss-mbid"), ("Colter Wall", "colter-mbid"))
    respond = routed(
        TYLER_POOL,
        musicbrainz={"artists": [mb_artist()]},
        similar=similar,
        tags=lb_metadata(
            **{
                "jayhawks-mbid": ["alternative country", "americana", "2020s"],
                "radio-mbid": ["country", "seen live"],
                "hiss-mbid": ["americana"],
                "other": ["pop"],
            }
        ),
    )

    async with api_for(respond, model_returning(TYLER_SEARCH)) as api:
        response = await api.post(
            "/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN}
        )

    events = parse_sse(response.text)
    ids = poster_ids(events)
    assert ids[:2] == ["similar", "by-name"]
    assert "radio" not in ids and "unrelated" not in ids
    assert dict(events)["candidates"]["names"][0] == "Hiss Golden Messenger"
    assert dict(events)["candidates"]["total"] == 5


async def test_with_listenbrainz_down_a_search_still_shortlists() -> None:
    respond = routed(
        tm_body(
            concert_of("seed", attraction("Tyler Childers", subgenre="Americana")),
            concert_of("genre", attraction("Lydia Loveless", subgenre="Americana")),
            concert_of("other", attraction("Unrelated", subgenre="Metal")),
        ),
        musicbrainz={"artists": [mb_artist()]},
        listenbrainz_status=404,
    )

    async with api_for(respond, model_returning(TYLER_SEARCH)) as api:
        response = await api.post(
            "/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN}
        )

    events = parse_sse(response.text)
    assert "error" not in dict(events)
    assert poster_ids(events) == ["seed"]


async def test_with_listenbrainz_down_last_fm_supplies_the_neighbours() -> None:
    respond = routed(TYLER_POOL, musicbrainz={"artists": [mb_artist()]}, listenbrainz_status=404)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "ws.audioscrobbler.com":
            return httpx.Response(200, json=lastfm_similar("Colter Wall"))
        return respond(request)

    model = model_returning(TYLER_SEARCH)
    async with api_for(handler, model, lastfm_key="lastfm-key") as api:
        response = await api.post(
            "/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN}
        )

    assert poster_ids(parse_sse(response.text))[0] == "by-name"
    assert "lastfm-key" not in response.text


async def test_with_musicbrainz_down_the_seed_still_joins_by_name() -> None:
    respond = routed(tm_body(concert_of("seed", attraction("Tyler Childers"))))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "musicbrainz.org":
            return httpx.Response(404)
        return respond(request)

    async with api_for(handler, model_returning(TYLER_SEARCH)) as api:
        response = await api.post(
            "/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN}
        )

    events = parse_sse(response.text)
    assert "error" not in dict(events)
    assert dict(events)["candidates"]["names"] == ["Tyler Childers"]


async def test_a_repeat_search_asks_no_similarity_source_again() -> None:
    calls: list[str] = []
    respond = routed(
        TYLER_POOL,
        musicbrainz={"artists": [mb_artist()]},
        similar=lb_similar(("Colter Wall", "colter-mbid")),
        tags=lb_metadata(**{"jayhawks-mbid": ["americana"]}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return respond(request)

    model = model_returning(TYLER_SEARCH, TYLER_SEARCH)
    async with api_for(handler, model) as api:
        await api.post("/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN})
        first = len(calls)
        await api.post("/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN})

    assert len(calls) == first


async def test_a_taste_with_no_place_looks_up_the_top_fifteen_similar_artists() -> None:
    similar = lb_similar(*((f"Artist {n}", f"m{n}") for n in range(20)))
    requests: list[httpx.Request] = []
    respond = routed(tm_body(), musicbrainz={"artists": [mb_artist()]}, similar=similar)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    model = model_returning(interpretation(artists=["Tyler Childers"]))
    async with api_for(handler, model) as api:
        response = await api.post("/search", json={"text": "Tyler Childers", "token": TOKEN})

    keywords = [r.url.params["keyword"] for r in requests if r.url.host == "app.ticketmaster.com"]
    assert sorted(keywords) == sorted(["Tyler Childers", *(f"Artist {n}" for n in range(15))])
    assert len(requests) == 1 + 16 + len(keywords)  # MusicBrainz, every hop, then Ticketmaster
    assert "error" not in dict(parse_sse(response.text))


async def test_the_app_starts_and_serves_with_no_last_fm_key() -> None:
    respond = routed(TYLER_POOL, musicbrainz={"artists": [mb_artist(id=TYLER_MBID)]})

    async with api_for(respond, model_returning(TYLER_SEARCH)) as api:
        response = await api.post(
            "/search", json={"text": "Tyler Childers in Chicago", "token": TOKEN}
        )

    assert "error" not in dict(parse_sse(response.text))


POOL_MESSAGE = "Looking for Concerts by Khruangbin and similar Artists"


async def test_an_artist_with_no_place_is_looked_up_directly_anywhere() -> None:
    requests: list[httpx.Request] = []
    respond = routed()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    model = model_returning(interpretation(artists=["Khruangbin"]))
    async with api_for(handler, model) as api:
        response = await api.post("/search", json={"text": "Khruangbin", "token": TOKEN})

    events = parse_sse(response.text)
    assert [name for name, _ in events][-3:] == ["status", "poster", "done"]
    assert ("status", {"step": "pool", "message": POOL_MESSAGE}) in events
    assert dict(events)["pool"] == {"total": 1}
    ticketmaster = [r for r in requests if r.url.host == "app.ticketmaster.com"]
    assert len(ticketmaster) == 1
    assert "geoPoint" not in ticketmaster[0].url.params


async def test_the_daily_limit_says_when_to_come_back_and_calls_ticketmaster_no_more() -> None:
    redis = FakeAsyncRedis()
    await redis.set(f"ticketmaster:calls:{dt.datetime.now(dt.UTC).date()}", limits.DAILY_CALLS)
    requests: list[httpx.Request] = []
    respond = routed()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    async with api_for(handler, redis=redis) as api:
        response = await api.post("/search", json={"text": "Chicago", "token": TOKEN})

    error = dict(parse_sse(response.text))["error"]
    assert error["code"] == "ticketmaster_limit"
    assert 0 < error["retry_after"] <= 86400
    assert all(request.url.host == "api.geoapify.com" for request in requests)


async def test_missing_facts_are_left_out_of_the_stream() -> None:
    record = upcoming_record()
    record["_embedded"]["attractions"][0]["externalLinks"] = {"musicbrainz": [{"id": "mbid"}]}
    del record["priceRanges"]
    record["dates"]["start"]["timeTBA"] = True

    async with api_for(routed(tm_body(record))) as api:
        response = await api.post("/search", json={"text": "Chicago", "token": TOKEN})

    concert = dict(parse_sse(response.text))["poster"]["recommendations"][0]["concert"]
    assert "time" not in concert
    assert "price" not in concert


async def test_a_missing_place_or_date_is_left_out_of_the_interpreted_event() -> None:
    model = model_returning(interpretation(artists=["Khruangbin"]))
    async with api_for(routed(), model) as api:
        response = await api.post("/search", json={"text": "Khruangbin", "token": TOKEN})

    assert dict(parse_sse(response.text))["interpreted"] == {"artists": ["Khruangbin"]}


async def test_a_place_with_no_listings_streams_an_empty_poster() -> None:
    async with api_for(routed(tm_body())) as api:
        response = await api.post("/search", json={"text": "Nowhere", "token": TOKEN})

    assert dict(parse_sse(response.text))["poster"] == {"recommendations": []}


async def test_a_search_with_no_taste_and_no_place_asks_for_one_and_calls_no_source() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no source should be called")

    async with api_for(handler, model_returning(interpretation())) as api:
        response = await api.post("/search", json={"text": "hello there", "token": TOKEN})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "interpreted", "error", "done"]
    assert events[2][1] == {
        "code": "needs_taste_or_place",
        "message": "Tell us an Artist, a style or a place.",
    }


async def test_a_style_with_no_artist_and_no_place_asks_for_one() -> None:
    model = model_returning(interpretation(descriptors=["dreamy guitar"]))
    async with api_for(routed(), model) as api:
        response = await api.post("/search", json={"text": "dreamy guitar", "token": TOKEN})

    assert dict(parse_sse(response.text))["error"]["code"] == "needs_place"


async def test_a_place_the_geocoder_cannot_find_says_so() -> None:
    model = model_returning(interpretation(place="Atlantis"))
    async with api_for(routed(geoapify={"results": []}), model) as api:
        response = await api.post("/search", json={"text": "Atlantis", "token": TOKEN})

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
        response = await api.post("/search", json={"text": "my secret Search", "token": TOKEN})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "error", "done"]
    assert events[1][1]["code"] == "interpreter_unavailable"
    assert "my secret Search" not in response.text


async def test_a_geocoder_failure_streams_a_safe_error() -> None:
    async with api_for(routed(geo_status=500)) as api:
        response = await api.post("/search", json={"text": "Chicago", "token": TOKEN})

    events = parse_sse(response.text)
    assert dict(events)["error"]["code"] == "geocoder_unavailable"
    assert "test-key" not in response.text


async def test_a_ticketmaster_failure_streams_a_safe_error() -> None:
    async with api_for(routed(tm_status=500)) as api:
        response = await api.post("/search", json={"text": "Chicago", "token": TOKEN})

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


NOTABLE = {"externalLinks": {"musicbrainz": [{"id": TYLER_MBID}]}, "name": "Khruangbin"}


def nearby_record() -> dict[str, Any]:
    return upcoming_record(
        _embedded={**tm_record()["_embedded"], "attractions": [NOTABLE]},
    )


async def test_nearby_returns_notable_concerts_and_never_calls_a_model() -> None:
    async def fail(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("the home page must not call a model")

    handler = routed(ticketmaster=tm_body(nearby_record()))
    async with api_for(handler, FunctionModel(fail)) as api:
        response = await api.get("/nearby", params={"lat": 41.87, "lon": -87.62})

    assert response.status_code == 200
    concert = response.json()["concerts"][0]
    assert concert["name"] == "Khruangbin: The Ether Tour"
    assert "time" in concert
    assert concert["artists"][0]["name"] == "Khruangbin"


async def test_nearby_never_falls_back_on_the_client_ip(api: httpx.AsyncClient) -> None:
    response = await api.get("/nearby", headers={"X-Forwarded-For": "8.8.8.8"})

    assert response.status_code == 422
    assert response.json() == {"code": "invalid_place", "message": "Choose a place."}


@pytest.mark.parametrize("params", [{"lat": 91, "lon": 0}, {"lat": 0, "lon": 181}])
async def test_nearby_refuses_impossible_coordinates(
    api: httpx.AsyncClient, params: dict[str, int]
) -> None:
    assert (await api.get("/nearby", params=params)).status_code == 422


async def test_a_ticketmaster_failure_on_nearby_gets_a_safe_error() -> None:
    async with api_for(routed(tm_status=500)) as api:
        response = await api.get("/nearby", params={"lat": 41.87, "lon": -87.62})

    assert response.status_code == 503
    assert response.json()["code"] == "ticketmaster_unavailable"
    assert "test-key" not in response.text


async def test_places_lists_matches_and_keeps_the_key_on_the_server() -> None:
    async with api_for(routed()) as api:
        response = await api.get("/places", params={"text": "Chi"})

    assert response.json()["places"][0]["lat"] == CHICAGO.lat
    assert "test-key" not in response.text


async def test_a_geocoder_failure_on_places_gets_a_safe_error() -> None:
    async with api_for(routed(geo_status=500)) as api:
        response = await api.get("/places", params={"text": "Chi"})

    assert response.status_code == 503
    assert response.json()["code"] == "geocoder_unavailable"


class BrokenRedis(FakeAsyncRedis):
    async def execute_command(self, *_: object, **__: object) -> None:
        raise RedisConnectionError("down")


def many_searches() -> Model:
    return model_returning(*[interpretation(place="Chicago")] * (limits.SEARCHES_PER_HOUR + 1))


def search_json(text: str = "Chicago") -> dict[str, str]:
    return {"text": text, "token": TOKEN}


async def test_each_client_gets_its_own_search_limit() -> None:
    settings = settings_with(client_ip_header="x-real-ip")
    async with api_for(routed(), many_searches(), settings=settings) as api:
        for _ in range(limits.SEARCHES_PER_HOUR):
            allowed = await api.post(
                "/search", json=search_json(), headers={"x-real-ip": "1.1.1.1"}
            )
            assert allowed.status_code == 200

        over = await api.post("/search", json=search_json(), headers={"x-real-ip": "1.1.1.1"})
        other = await api.post("/search", json=search_json(), headers={"x-real-ip": "2.2.2.2"})

    assert over.status_code == 429
    assert over.json()["code"] == "visitor_limit"
    assert over.json()["retry_after"] > 0
    assert other.status_code == 200


async def test_an_untrusted_forwarding_header_cannot_dodge_the_limit() -> None:
    async with api_for(routed(), many_searches()) as api:
        for n in range(limits.SEARCHES_PER_HOUR):
            headers = {"X-Forwarded-For": f"10.0.0.{n}"}
            await api.post("/search", json=search_json(), headers=headers)

        over = await api.post(
            "/search", json=search_json(), headers={"X-Forwarded-For": "10.0.1.1"}
        )

    assert over.status_code == 429


async def test_the_last_address_counts_because_a_visitor_can_write_the_earlier_ones() -> None:
    settings = settings_with(client_ip_header="x-forwarded-for")
    async with api_for(routed(), many_searches(), settings=settings) as api:
        for n in range(limits.SEARCHES_PER_HOUR):
            headers = {"X-Forwarded-For": f"10.0.0.{n}, 1.1.1.1"}
            await api.post("/search", json=search_json(), headers=headers)

        over = await api.post(
            "/search", json=search_json(), headers={"X-Forwarded-For": "10.0.1.1, 1.1.1.1"}
        )

    assert over.status_code == 429


async def test_at_the_spend_cap_searches_stop_and_the_home_page_keeps_working() -> None:
    redis = FakeAsyncRedis()
    await limits.record_spend(redis, limits.DAILY_SPEND)
    handler = routed(ticketmaster=tm_body(nearby_record()))

    async with api_for(handler, redis=redis) as api:
        search = await api.post("/search", json=search_json())
        nearby = await api.get("/nearby", params={"lat": 41.87, "lon": -87.62})

    assert search.status_code == 503
    assert search.json()["code"] == "budget_reached"
    assert nearby.status_code == 200
    assert nearby.json()["concerts"]


async def test_a_finished_search_adds_its_real_cost_to_the_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def costly(*_: Any) -> Any:
        record_usage(RunUsage(input_tokens=100, output_tokens=20, cost=Decimal("0.25")))
        raise InterpreterError("failed after spending")

    monkeypatch.setattr(pipeline, "interpret", costly)
    redis = FakeAsyncRedis()

    async with api_for(routed(), redis=redis) as api:
        await api.post("/search", json=search_json())

    assert await redis.get(f"spend:day:{dt.datetime.now(dt.UTC).date()}") == b"250000"


async def test_the_kill_switch_stops_searches_and_not_the_home_page() -> None:
    handler = routed(ticketmaster=tm_body(nearby_record()))
    async with api_for(handler, settings=settings_with(search_enabled=False)) as api:
        search = await api.post("/search", json=search_json())
        nearby = await api.get("/nearby", params={"lat": 41.87, "lon": -87.62})

    assert search.status_code == 503
    assert search.json()["code"] == "search_off"
    assert nearby.status_code == 200


async def test_a_disallowed_origin_is_refused_on_the_server() -> None:
    async with api_for(routed()) as api:
        refused = await api.post(
            "/search", json=search_json(), headers={"Origin": "https://evil.example"}
        )
        preflight = await api.options(
            "/search",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert refused.status_code == 403
    assert refused.json()["code"] == "origin_refused"
    assert preflight.status_code == 400


async def test_a_failed_bot_check_stops_the_search_before_any_model_call() -> None:
    async def fail(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        raise AssertionError("a failed bot check must not reach a model")

    def bot_check(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    async with api_for(routed(), FunctionModel(fail), bot_check=bot_check) as api:
        response = await api.post("/search", json=search_json())

    assert response.status_code == 403
    assert response.json()["code"] == "bot_check_failed"


async def test_a_search_without_a_token_is_refused(api: httpx.AsyncClient) -> None:
    response = await api.post("/search", json={"text": "Chicago"})

    assert response.status_code == 422


async def test_turnstile_gets_the_secret_and_token_and_an_outage_stays_safe() -> None:
    forms: list[bytes] = []

    def outage(request: httpx.Request) -> httpx.Response:
        forms.append(request.content)
        return httpx.Response(500)

    async with api_for(routed(), bot_check=outage) as api:
        response = await api.post("/search", json=search_json())

    assert response.status_code == 503
    assert response.json()["code"] == "bot_check_unavailable"
    assert b"response=turnstile-token" in forms[0]
    assert b"secret=" in forms[0]
    assert "secret" not in response.text


async def test_without_redis_search_refuses_and_the_home_page_keeps_working() -> None:
    redis = BrokenRedis()
    handler = routed(ticketmaster=tm_body(nearby_record()))

    async with api_for(handler, redis=redis) as api:
        search = await api.post("/search", json=search_json())
        nearby = await api.get("/nearby", params={"lat": 41.87, "lon": -87.62})

    assert search.status_code == 503
    assert search.json()["code"] == "limits_unavailable"
    assert nearby.status_code == 200


async def test_nearby_and_places_have_their_own_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "NEARBY_PER_HOUR", 1)
    monkeypatch.setattr(limits, "PLACES_PER_HOUR", 1)
    handler = routed(ticketmaster=tm_body(nearby_record()))

    async with api_for(handler) as api:
        params = {"lat": 41.87, "lon": -87.62}
        await api.get("/nearby", params=params)
        nearby = await api.get("/nearby", params=params)
        await api.get("/places", params={"text": "Chi"})
        places = await api.get("/places", params={"text": "Chi"})

    assert (nearby.status_code, places.status_code) == (429, 429)
    assert nearby.json()["code"] == "visitor_limit"


async def test_every_response_carries_the_security_headers(api: httpx.AsyncClient) -> None:
    response = await api.get("/health")

    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "max-age" in response.headers["strict-transport-security"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def steps_of(response: httpx.Response) -> list[str]:
    return [data["step"] for name, data in parse_sse(response.text) if name == "status"]


def lastfm_top(*names: str) -> dict[str, Any]:
    return {"topartists": {"artist": [{"name": name, "playcount": "9"} for name in names]}}


def lastfm_api(status: int, body: dict[str, Any]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handler


async def test_a_lastfm_import_returns_top_artists_and_keeps_nothing() -> None:
    redis = FakeAsyncRedis()
    handler = lastfm_api(200, lastfm_top("Khruangbin", "Tyler Childers"))

    async with api_for(handler, redis=redis, lastfm_key="key") as api:
        response = await api.post("/taste/lastfm", json={"username": "someone"})

    assert response.json() == {"artists": ["Khruangbin", "Tyler Childers"]}
    assert await redis.dbsize() == 1  # pyright: ignore[reportUnknownMemberType]


async def test_a_listenbrainz_import_returns_top_artists() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = {"payload": {"artists": [{"artist_name": "Röyksopp", "listen_count": 9}]}}
        return httpx.Response(200, json=body)

    async with api_for(handler) as api:
        response = await api.post("/taste/listenbrainz", json={"username": "a/b"})

    assert response.json() == {"artists": ["Röyksopp"]}
    assert requests[0].url.raw_path.startswith(b"/1/stats/user/a%2Fb/artists")


@pytest.mark.parametrize(
    ("source", "status", "body", "expected_status", "code"),
    [
        ("lastfm", 404, {"error": 6, "message": "User not found"}, 404, "taste_user_not_found"),
        ("lastfm", 403, {"error": 17, "message": "Login required"}, 403, "taste_private"),
        ("lastfm", 500, {"error": 8, "message": "Backend"}, 503, "taste_unavailable"),
        ("lastfm", 200, lastfm_top(), 404, "taste_empty"),
        ("listenbrainz", 404, {}, 404, "taste_user_not_found"),
        ("listenbrainz", 500, {}, 503, "taste_unavailable"),
    ],
)
async def test_a_failed_import_says_why_and_never_echoes_the_username(
    source: str, status: int, body: dict[str, Any], expected_status: int, code: str
) -> None:
    async with api_for(lastfm_api(status, body), lastfm_key="key") as api:
        response = await api.post(f"/taste/{source}", json={"username": "private-person"})

    assert response.status_code == expected_status
    assert response.json()["code"] == code
    assert "private-person" not in response.text


async def test_a_listenbrainz_account_without_stats_yet_has_nothing_to_import() -> None:
    async with api_for(lambda _: httpx.Response(204)) as api:
        response = await api.post("/taste/listenbrainz", json={"username": "new"})

    assert response.json()["code"] == "taste_empty"


async def test_a_blank_username_is_refused(api: httpx.AsyncClient) -> None:
    response = await api.post("/taste/listenbrainz", json={"username": "  "})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_username"


async def test_lastfm_import_without_a_key_is_unavailable(api: httpx.AsyncClient) -> None:
    response = await api.post("/taste/lastfm", json={"username": "someone"})

    assert response.status_code == 503
    assert response.json()["code"] == "taste_unavailable"


async def test_an_import_changes_the_poster_for_a_search_with_only_a_place() -> None:
    handler = routed(musicbrainz={"artists": []})
    place_only = interpretation(place="Chicago")

    async with api_for(handler, model_returning(place_only, place_only)) as api:
        response_without = await api.post("/search", json=search_json())
        response_with = await api.post("/search", json={**search_json(), "taste": ["Khruangbin"]})

    assert "match" not in steps_of(response_without)
    assert "match" in steps_of(response_with)
    assert dict(parse_sse(response_with.text))["interpreted"]["artists"] == ["Khruangbin"]


async def test_a_typed_taste_beats_the_import() -> None:
    model = model_returning(interpretation(place="Chicago", tags=["jazz"]))

    async with api_for(routed(tm_body()), model) as api:
        response = await api.post("/search", json={**search_json(), "taste": ["Khruangbin"]})

    assert dict(parse_sse(response.text))["interpreted"] == {"place": "Chicago", "artists": []}


async def test_only_the_top_of_a_long_import_costs_lookups() -> None:
    requests: list[httpx.Request] = []
    respond = routed(tm_body(), musicbrainz={"artists": []})

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    names = [f"Artist {n}" for n in range(50)]
    async with api_for(handler) as api:
        await api.post("/search", json={**search_json(), "taste": names})

    hits = [r for r in requests if r.url.host == "musicbrainz.org"]
    assert len(hits) == pipeline.IMPORTED_SEEDS


async def test_a_taste_over_the_cap_is_refused(api: httpx.AsyncClient) -> None:
    names = [f"Artist {n}" for n in range(101)]

    response = await api.post("/search", json={**search_json(), "taste": names})

    assert response.status_code == 422
