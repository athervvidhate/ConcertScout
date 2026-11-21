"""Contract tests for typed Poster Refinements (Issue #92)."""

import datetime as dt
import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis.aioredis import FakeRedis as FakeAsyncRedis
from pydantic_ai.messages import ModelMessage, ModelResponse, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from concert_scout import limits, pool, ranker, refinement
from concert_scout.app import create_app
from concert_scout.models import Artist, Concert, Place, Price, Reading
from concert_scout.names import normalize
from concert_scout.sources import geocoder, jev, listenbrainz
from evals import cases
from tests.contracts import (
    contract_grades,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)

TOKEN = "valid-token"

# Explicit weekday dates in the future so weekend/Saturday filters are deterministic.
BASE_MONDAY = dt.date.today() + dt.timedelta(days=(7 - dt.date.today().weekday()) + 7)
WEDNESDAY = BASE_MONDAY + dt.timedelta(days=2)
FRIDAY = BASE_MONDAY + dt.timedelta(days=4)
SATURDAY = BASE_MONDAY + dt.timedelta(days=5)


@pytest.fixture(autouse=True)
def _sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


DEFAULT_PRICE = Price(min=35, max=50, currency="USD")


def _concert(
    cid: str,
    artist: str,
    *,
    date: dt.date | None = FRIDAY,
    city: str = "San Francisco",
    price: Price | None = DEFAULT_PRICE,
    venue: str = "Source Hall",
) -> Concert:
    return Concert(
        id=cid,
        name=f"{artist} Live",
        url=f"https://tickets.example/{cid}",
        artists=[Artist(name=artist, mbid=f"mbid-{normalize(artist)}")],
        date=date,
        time=dt.time(20, 0),
        time_zone="America/Los_Angeles",
        venue=venue,
        city=city,
        region="CA",
        price=price,
    )


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    name = ""
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and name:
            events.append((name, json.loads(line.removeprefix("data: "))))
            name = ""
    return events


def _seed_pool(monkeypatch: pytest.MonkeyPatch, concerts: list[Concert]) -> AsyncMock:
    mock_pool = AsyncMock(return_value=concerts)
    monkeypatch.setattr(pool, "find_concerts", mock_pool)
    tags = {a.mbid: ["uk garage"] for c in concerts for a in c.artists if a.mbid}
    monkeypatch.setattr(listenbrainz.TagFetch, "tags", AsyncMock(return_value=tags))
    return mock_pool


async def _initial_search(
    api: httpx.AsyncClient, text: str = "UKG in SF"
) -> tuple[str, dict[str, Any], list[str]]:
    resp = await api.post("/search", json={"text": text, "token": TOKEN, "time_zone": "UTC"})
    assert resp.status_code == 200
    events = dict(_parse_sse(resp.text))
    search_id = events["shareable"]["search_id"]
    reading = events["reading"]
    artists = [r["concert"]["artists"][0]["name"] for r in events["poster"]["recommendations"]]
    return search_id, reading, artists


async def test_filter_only_refinements_make_zero_ranker_and_zero_pool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'Only weekends' and 'cheaper' reuse cached shortlist and grades with zero ranker calls."""
    concerts = [
        _concert(
            "c-wed-cheap",
            "Midweek Act",
            date=WEDNESDAY,
            price=Price(min=25, max=30, currency="USD"),
        ),
        _concert(
            "c-fri-pricey",
            "Weekend Pricey",
            date=FRIDAY,
            price=Price(min=95, max=120, currency="USD"),
        ),
        _concert(
            "c-sat-cheap",
            "Saturday Cheap",
            date=SATURDAY,
            price=Price(min=32, max=40, currency="USD"),
        ),
        _concert("c-sat-unpriced", "Saturday Unpriced", date=SATURDAY, price=None),
    ]
    pool_mock = _seed_pool(monkeypatch, concerts)

    jev_calls = 0
    explain_calls = 0
    base_model = contract_model().function
    assert base_model is not None

    async def counted_jev(*args: Any, **kwargs: Any) -> dict[str, int]:
        nonlocal jev_calls
        jev_calls += 1
        return await contract_grades(*args, **kwargs)

    def counted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal explain_calls
        if info.instructions == ranker.REASONS:
            explain_calls += 1
        return base_model(messages, info)  # pyright: ignore[reportReturnType]

    monkeypatch.setattr(jev, "grade", counted_jev)
    redis = FakeAsyncRedis()
    app = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        redis,
        FunctionModel(counted_model),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, reading, poster_artists = await _initial_search(api)
        assert jev_calls == 1
        assert explain_calls == 1
        assert pool_mock.call_count == 1

        # 1) "Only weekends" -> drops Wednesday, ZERO new Jev / explain / pool calls.
        resp_wknd = await api.post(
            "/search",
            json={
                "reading": reading,
                "refinement": "Only weekends",
                "poster_artists": poster_artists,
                "search_id": search_id,
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp_wknd.status_code == 200
        wknd_events = _parse_sse(resp_wknd.text)
        wknd_map = dict(wknd_events)
        assert wknd_map["refinement"]["label"] == "Weekends only"
        assert wknd_map["reading"]["weekends_only"] is True
        wknd_ids = [r["concert"]["id"] for r in wknd_map["poster"]["recommendations"]]
        assert "c-wed-cheap" not in wknd_ids
        assert set(wknd_ids) == {"c-fri-pricey", "c-sat-cheap", "c-sat-unpriced"}
        assert jev_calls == 1
        assert explain_calls == 1
        assert pool_mock.call_count == 1
        assert wknd_events[-1] == ("done", {})

        # 2) Chain "cheaper" -> drops pricey AND unpriced (ADR 0002), still ZERO ranker calls.
        next_search_id = wknd_map["shareable"]["search_id"]
        resp_cheap = await api.post(
            "/search",
            json={
                "reading": wknd_map["reading"],
                "refinement": "cheaper",
                "poster_artists": [
                    r["concert"]["artists"][0]["name"]
                    for r in wknd_map["poster"]["recommendations"]
                ],
                "search_id": next_search_id,
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp_cheap.status_code == 200
        cheap_map = dict(_parse_sse(resp_cheap.text))
        assert cheap_map["reading"]["max_price"] == 40.0
        assert [r["concert"]["id"] for r in cheap_map["poster"]["recommendations"]] == [
            "c-sat-cheap"
        ]
        assert jev_calls == 1
        assert explain_calls == 1
        assert pool_mock.call_count == 1


async def test_place_and_taste_refinements_produce_new_poster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'try Oakland instead' and 'more like <Artist on the Poster>' run the pipeline."""
    concerts = [
        _concert("c-one", "Sammy Virji", city="Oakland"),
        _concert("c-two", "Jamie xx", city="Oakland"),
    ]
    pool_mock = _seed_pool(monkeypatch, concerts)
    geocode_mock = AsyncMock(return_value=Place(name="Oakland, California", lat=37.8, lon=-122.27))
    monkeypatch.setattr(geocoder, "geocode", geocode_mock)

    redis = FakeAsyncRedis()
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, reading, poster_artists = await _initial_search(api)
        assert pool_mock.call_count == 1

        # "try Oakland instead" -> geocodes Oakland and refreshes pool.
        resp_oak = await api.post(
            "/search",
            json={
                "reading": reading,
                "refinement": "try Oakland instead",
                "poster_artists": poster_artists,
                "search_id": search_id,
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp_oak.status_code == 200
        oak_map = dict(_parse_sse(resp_oak.text))
        assert "Oakland" in oak_map["reading"]["place"]
        assert oak_map["refinement"]["label"] == "Try Oakland"
        assert pool_mock.call_count == 2
        assert len(oak_map["poster"]["recommendations"]) == 2

        # "more like the second one" -> resolves Jamie xx from poster_artists.
        resp_more = await api.post(
            "/search",
            json={
                "reading": oak_map["reading"],
                "refinement": "more like the second one",
                "poster_artists": ["Sammy Virji", "Jamie xx"],
                "search_id": oak_map["shareable"]["search_id"],
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp_more.status_code == 200
        more_map = dict(_parse_sse(resp_more.text))
        assert "Jamie xx" in more_map["reading"]["artists"]
        assert more_map["refinement"]["label"] == "More like Jamie xx"
        assert len(more_map["poster"]["recommendations"]) == 2


async def test_unanswerable_question_returns_cant_tell_with_source_link_and_no_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'is it all ages?' never invents facts and runs zero pool or ranker calls."""
    concerts = [
        _concert("c-one", "Sammy Virji"),
        _concert("c-two", "Jamie xx"),
    ]
    pool_mock = _seed_pool(monkeypatch, concerts)
    jev_mock = AsyncMock(side_effect=contract_grades)
    monkeypatch.setattr(jev, "grade", jev_mock)

    redis = FakeAsyncRedis()
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, reading, poster_artists = await _initial_search(api)
        assert pool_mock.call_count == 1
        assert jev_mock.call_count == 1

        resp = await api.post(
            "/search",
            json={
                "reading": reading,
                "refinement": "is it all ages?",
                "poster_artists": poster_artists,
                "search_id": search_id,
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        names = [name for name, _ in events]
        assert "unanswerable" in names
        assert "poster" not in names
        assert "reading" not in names
        assert "shareable" not in names
        assert events[-1] == ("done", {})

        note = dict(events)["unanswerable"]
        assert "can't tell" in note["message"].casefold()
        assert note["source_url"] == "https://tickets.example/c-one"
        assert note["artist"] == "Sammy Virji"
        # No new pool or ranker calls.
        assert pool_mock.call_count == 1
        assert jev_mock.call_count == 1


async def test_refinement_model_never_sees_coordinates_imported_taste_spotify_or_listing_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0003 & privacy: model input contains only Reading, poster_artists, and Refinement."""
    captured_prompts: list[str] = []
    base_model = contract_model().function
    assert base_model is not None

    def spy_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if (info.instructions or "").startswith(refinement.INSTRUCTIONS):
            for msg in messages:
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        captured_prompts.append(part.content)
        return base_model(messages, info)  # pyright: ignore[reportReturnType]

    concerts = [_concert("c-secret", "Contract Artist", venue="Secret Venue XYZ")]
    _seed_pool(monkeypatch, concerts)
    redis = FakeAsyncRedis()
    app = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        redis,
        FunctionModel(spy_model),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, reading, poster_artists = await _initial_search(api)
        resp = await api.post(
            "/search",
            json={
                "reading": reading,
                "refinement": "Only weekends",
                "poster_artists": poster_artists,
                "search_id": search_id,
                "near": {"lat": 37.7749, "lon": -122.4194},
                "taste": ["Secret Spotify Artist", "Private Imported Band"],
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp.status_code == 200

    assert len(captured_prompts) == 1
    sent = json.loads(captured_prompts[0])
    assert set(sent.keys()) == {"reading", "poster_artists", "refinement"}
    raw_prompt = captured_prompts[0]
    assert "37.7749" not in raw_prompt
    assert "-122.4194" not in raw_prompt
    assert "Secret Spotify Artist" not in raw_prompt
    assert "Private Imported Band" not in raw_prompt
    assert "Secret Venue XYZ" not in raw_prompt
    assert "tickets.example" not in raw_prompt


async def test_refinements_count_against_visitor_limit_and_spend_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each Refinement counts as one Search against visitor limits and daily/monthly spend caps."""
    concerts = [_concert("c-one", "Contract Artist", date=SATURDAY)]
    _seed_pool(monkeypatch, concerts)

    base_model = contract_model().function
    assert base_model is not None

    def billed_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        resp = base_model(messages, info)
        assert isinstance(resp, ModelResponse)
        return ModelResponse(
            parts=resp.parts,
            usage=RequestUsage(input_tokens=2000, output_tokens=200),
            model_name="claude-haiku-5-5",
        )

    redis = FakeAsyncRedis()
    app = create_app(
        settings_with(searches_per_hour=2),
        httpx.MockTransport(forbidden_http),
        redis,
        FunctionModel(billed_model),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        # 1st call: initial Search (uses 1 of 2 hourly Searches).
        search_id, reading, poster_artists = await _initial_search(api)

        # 2nd call: Refinement (uses 2 of 2 hourly Searches).
        resp2 = await api.post(
            "/search",
            json={
                "reading": reading,
                "refinement": "Only weekends",
                "poster_artists": poster_artists,
                "search_id": search_id,
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp2.status_code == 200

        # 3rd call: another Refinement -> 429 visitor_limit.
        resp3 = await api.post(
            "/search",
            json={
                "reading": reading,
                "refinement": "is it all ages?",
                "poster_artists": poster_artists,
                "search_id": search_id,
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp3.status_code == 429
        assert resp3.json()["code"] == "visitor_limit"

    # Spend cap check: when daily budget is exhausted, Refinement is refused with 503.
    redis_capped = FakeAsyncRedis()
    await limits.record_spend(redis_capped, Decimal("2.00"))
    app_capped = create_app(
        settings_with(searches_per_hour=10),
        httpx.MockTransport(forbidden_http),
        redis_capped,
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app_capped), base_url="http://test"
    ) as api:
        resp_cap = await api.post(
            "/search",
            json={
                "reading": {"place": "San Francisco", "artists": ["Sammy Virji"]},
                "refinement": "Only weekends",
                "poster_artists": ["Sammy Virji"],
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
        assert resp_cap.status_code == 503
        assert resp_cap.json()["code"] == "budget_reached"


@pytest.mark.parametrize(
    "body",
    [
        {"refinement": "Only weekends"},  # Missing current Reading
        {"text": "UKG in SF", "reading": {"place": "SF"}, "refinement": "Only weekends"},
        {"reading": {"place": "SF"}, "refinement": "   "},
        {"reading": {"place": "SF"}, "refinement": "x" * 301},
        {"reading": {"place": "SF"}, "refinement": "cheaper", "poster_artists": ["A"] * 21},
        {"reading": {"place": "SF"}, "refinement": "cheaper", "search_id": "bad id!"},
    ],
)
async def test_invalid_refinement_requests_are_refused(body: dict[str, Any]) -> None:
    redis = FakeAsyncRedis()
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        resp = await api.post("/search", json={**body, "token": TOKEN, "time_zone": "UTC"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_search"


async def test_eval_refinement_cases_all_pass_contract_expectations() -> None:
    """Verify every Refinement case in `evals/refinements.yaml` against `refinement.refine`."""
    all_searches = {s.id for s in cases.load()}
    refinement_cases = cases.load_refinements()
    assert len(refinement_cases) == 5

    today = dt.date(2026, 11, 21)
    model = contract_model()
    for case in refinement_cases:
        assert case.base_search in all_searches
        base_reading = Reading(
            artists=["Fred again.."] if "fred" in case.base_search else [],
            descriptors=["groove-led instrumental"] if "instrumental" in case.base_search else [],
            tags=["uk garage"] if "fred" in case.base_search else ["funk"],
            place="San Francisco, California, United States",
        )
        outcome = await refinement.refine(
            base_reading, case.poster_artists, case.refinement, today, model
        )
        if case.expect_kind == "unanswerable":
            assert isinstance(outcome, refinement.UnanswerableRefinement), case.id
            assert "can't tell" in outcome.message.casefold()
        else:
            assert isinstance(outcome, refinement.RefinedReading), case.id
            assert (
                refinement.is_filter_only(
                    base_reading,
                    outcome.reading,
                    boost_artists=outcome.boost_artists,
                    today=today,
                )
                is case.expect_filter_only
            ), case.id
            if case.expect_weekends_only:
                assert outcome.reading.weekends_only is True
            if case.expect_place_contains:
                assert case.expect_place_contains in (outcome.reading.place or "")
            if case.expect_adds_artist:
                assert case.expect_adds_artist in outcome.reading.artists
            if case.expect_has_max_price:
                assert outcome.reading.max_price is not None
                assert outcome.reading.max_price > 0
