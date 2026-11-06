import datetime as dt
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

from concert_scout import limits
from concert_scout.app import create_app
from concert_scout.config import Settings
from concert_scout.matching import SHORTLIST_SIZE
from tests.conftest import (
    KHRUANGBIN_MBID,
    TYLER_MBID,
    UPCOMING,
    geoapify_result,
    interpretation,
    lastfm_similar,
    lb_metadata,
    lb_similar,
    mb_artist,
    model_returning,
    picks,
    tm_body,
    upcoming_record,
)

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


def api_for(
    handler: Handler,
    model: Model | None = None,
    redis: FakeAsyncRedis | None = None,
    lastfm_key: str | None = None,
) -> httpx.AsyncClient:
    settings = Settings(
        tm_key=SecretStr("test-key"),
        anthropic_api_key=SecretStr("test-key"),
        geoapify_key=SecretStr("test-key"),
        lastfm_key=SecretStr(lastfm_key) if lastfm_key else None,
        cors_origins=[ALLOWED_ORIGIN],
    )
    model = model or model_returning(interpretation(place="Chicago"))
    app = create_app(settings, httpx.MockTransport(handler), redis or FakeAsyncRedis(), model)
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

    model = model_returning(fields, picks(("vvG18Z_ueUZbii", 92, "The same patient groove")))
    async with api_for(handler, model) as api:
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
    assert events[9][1]["recommendations"][0]["reason"] == "The same patient groove"
    assert events[9][1]["recommendations"][0]["concert"] == {
        "id": "vvG18Z_ueUZbii",
        "name": "Khruangbin: The Ether Tour",
        "url": "https://www.ticketmaster.com/event/040064D0B6018B2C",
        "artists": [{"name": "Khruangbin", "mbid": KHRUANGBIN_MBID}, {"name": "Men I Trust"}],
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

    answer = picks(("vvG18Z_ueUZbii", 92, "The same patient groove"))
    async with api_for(handler, model_returning(fields, answer, fields, answer)) as api:
        first = await api.post("/search", json={"text": "Khruangbin in Chicago"})
        calls_after_first = ticketmaster_calls
        second = await api.post("/search", json={"text": "Khruangbin in Chicago"})

    assert calls_after_first == 8  # seven months of the default window and one Artist
    assert ticketmaster_calls == calls_after_first
    assert dict(parse_sse(second.text))["poster"] == dict(parse_sse(first.text))["poster"]


async def test_the_shortlist_cuts_the_pool_while_the_pool_event_counts_everything() -> None:
    records = [concert_of(str(n), attraction(f"Artist {n}", f"m{n}")) for n in range(120)]

    async with api_for(routed(tm_body(*records))) as api:
        response = await api.post("/search", json={"text": "Chicago"})

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
        response = await api.post("/search", json={"text": "Chicago"})

    assert hosts == {"api.geoapify.com", "app.ticketmaster.com"}
    steps = [data["step"] for name, data in parse_sse(response.text) if name == "status"]
    assert "match" not in steps
    assert "rank" not in steps
    assert len(dict(parse_sse(response.text))["poster"]["recommendations"]) == 1


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
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    candidates = dict(parse_sse(response.text))["candidates"]
    assert candidates["names"][:2] == ["Hiss Golden Messenger", "Colter Wall"]
    names = candidates["names"]
    assert names.index("The Jayhawks") < names.index("Generic Radio Act") < names.index("Unrelated")
    assert candidates["total"] == 5


TYLER_TAIL = routed(
    tm_body(
        concert_of("seed", attraction("Tyler Childers", TYLER_MBID, subgenre="Country")),
        concert_of("similar", attraction("Colter Wall", "colter-mbid", subgenre="Country")),
        concert_of("filler", attraction("Lady A", "lady-a-mbid", subgenre="Country")),
        concert_of("nothing", attraction("Unrelated", "unrelated-mbid", subgenre="Metal")),
    ),
    musicbrainz={"artists": [mb_artist()]},
    similar=lb_similar(("Colter Wall", "colter-mbid")),
)


async def test_the_poster_carries_the_rankers_reasons_and_no_value_of_its_own() -> None:
    model = model_returning(
        TYLER_SEARCH,
        picks(
            ("similar", 88, "The same dusty storytelling"),
            ("similar-corrupted", 99, "https://evil.example"),
            ("seed", 97, "The Artist you asked for"),
        ),
    )

    async with api_for(TYLER_TAIL, model) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    recommendations = dict(parse_sse(response.text))["poster"]["recommendations"]
    assert [(r["concert"]["id"], r["reason"]) for r in recommendations] == [
        ("seed", "The Artist you asked for"),
        ("similar", "The same dusty storytelling"),
    ]
    assert all(set(r) == {"concert", "reason"} for r in recommendations)
    assert "evil.example" not in response.text
    assert recommendations[0]["concert"]["url"] == upcoming_record()["url"]


async def test_a_ranker_failure_shows_strong_matches_with_neutral_reasons_and_no_padding() -> None:
    async with api_for(TYLER_TAIL, model_returning(TYLER_SEARCH)) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    events = parse_sse(response.text)
    assert "error" not in dict(events)
    assert [
        (r["concert"]["id"], r["reason"]) for r in dict(events)["poster"]["recommendations"]
    ] == [
        ("seed", "Tyler Childers is in your Search"),
        ("similar", "Colter Wall is similar to Tyler Childers"),
    ]


async def test_picks_that_all_name_unknown_ids_fall_back_too() -> None:
    model = model_returning(TYLER_SEARCH, picks(("made-up", 99, "Trust me")))

    async with api_for(TYLER_TAIL, model) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    assert poster_ids(parse_sse(response.text)) == ["seed", "similar"]


async def test_a_ranker_that_drops_everything_gives_an_empty_poster() -> None:
    model = model_returning(TYLER_SEARCH, picks())

    async with api_for(TYLER_TAIL, model) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    assert poster_ids(parse_sse(response.text)) == []


async def test_a_taste_with_no_concerts_makes_no_ranker_call() -> None:
    respond = routed(tm_body(), musicbrainz={"artists": [mb_artist()]})

    async with api_for(respond, model_returning(TYLER_SEARCH)) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    events = parse_sse(response.text)
    assert dict(events)["poster"] == {"recommendations": []}
    assert "rank" not in [data["step"] for name, data in events if name == "status"]


async def test_a_place_only_search_shows_notable_concerts_soonest_first_with_no_ranker() -> None:
    records = [
        concert_of("bar", attraction("Unlinked Bar Band")),
        concert_of("night-one", attraction("Touring Act", "touring-mbid")),
        concert_of("night-two", attraction("Touring Act", "touring-mbid")),
        concert_of("later", attraction("Next Act", "next-mbid")),
    ]

    async with api_for(routed(tm_body(*records))) as api:
        response = await api.post("/search", json={"text": "Chicago"})

    events = dict(parse_sse(response.text))
    assert events["pool"] == {"total": 4}
    assert [r["concert"]["id"] for r in events["poster"]["recommendations"]] == [
        "night-one",
        "later",
    ]
    assert {r["reason"] for r in events["poster"]["recommendations"]} == {"Coming up nearby"}


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
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    events = parse_sse(response.text)
    assert "error" not in dict(events)
    assert dict(events)["candidates"]["names"] == ["Tyler Childers", "Lydia Loveless", "Unrelated"]
    assert poster_ids(events) == ["seed"]


async def test_with_listenbrainz_down_last_fm_supplies_the_neighbours() -> None:
    respond = routed(TYLER_POOL, musicbrainz={"artists": [mb_artist()]}, listenbrainz_status=404)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "ws.audioscrobbler.com":
            return httpx.Response(200, json=lastfm_similar("Colter Wall"))
        return respond(request)

    model = model_returning(TYLER_SEARCH)
    async with api_for(handler, model, lastfm_key="lastfm-key") as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

    assert poster_ids(parse_sse(response.text))[0] == "by-name"
    assert "lastfm-key" not in response.text


async def test_with_musicbrainz_down_the_seed_still_joins_by_name() -> None:
    respond = routed(tm_body(concert_of("seed", attraction("Tyler Childers"))))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "musicbrainz.org":
            return httpx.Response(404)
        return respond(request)

    async with api_for(handler, model_returning(TYLER_SEARCH)) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

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

    model = model_returning(TYLER_SEARCH, picks(), TYLER_SEARCH, picks())
    async with api_for(handler, model) as api:
        await api.post("/search", json={"text": "Tyler Childers in Chicago"})
        first = len(calls)
        await api.post("/search", json={"text": "Tyler Childers in Chicago"})

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
        response = await api.post("/search", json={"text": "Tyler Childers"})

    keywords = [r.url.params["keyword"] for r in requests if r.url.host == "app.ticketmaster.com"]
    assert sorted(keywords) == sorted(["Tyler Childers", *(f"Artist {n}" for n in range(15))])
    assert len(requests) == 1 + 16 + len(keywords)  # MusicBrainz, every hop, then Ticketmaster
    assert "error" not in dict(parse_sse(response.text))


async def test_the_app_starts_and_serves_with_no_last_fm_key() -> None:
    respond = routed(TYLER_POOL, musicbrainz={"artists": [mb_artist(id=TYLER_MBID)]})

    async with api_for(respond, model_returning(TYLER_SEARCH)) as api:
        response = await api.post("/search", json={"text": "Tyler Childers in Chicago"})

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
        response = await api.post("/search", json={"text": "Khruangbin"})

    events = parse_sse(response.text)
    assert [name for name, _ in events][-4:] == ["candidates", "status", "poster", "done"]
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
        response = await api.post("/search", json={"text": "Chicago"})

    error = dict(parse_sse(response.text))["error"]
    assert error["code"] == "ticketmaster_limit"
    assert 0 < error["retry_after"] <= 86400
    assert all(request.url.host == "api.geoapify.com" for request in requests)


async def test_missing_facts_are_left_out_of_the_stream() -> None:
    record = upcoming_record()
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


async def test_a_style_with_no_artist_and_no_place_asks_for_one() -> None:
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
