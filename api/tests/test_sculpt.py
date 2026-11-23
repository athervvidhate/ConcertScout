"""Contract tests for Instant Poster Sculpting (Issue #140)."""

import datetime as dt
import json
import math
import time
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis.aioredis import FakeRedis as FakeAsyncRedis
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import cobilling, embeddings, limits, matching, pool, ranker, sculpt, share
from concert_scout.app import create_app
from concert_scout.models import Artist, ArtistProfile, Concert, Price
from concert_scout.names import normalize
from concert_scout.sources import jev, listenbrainz, supabase, venues
from tests.contracts import (
    contract_grades,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)

TOKEN = "valid-token"


@pytest.fixture(autouse=True)
def _sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


# Friday, Saturday, Sunday, and a Wednesday in the future so dates never expire.
BASE_MONDAY = dt.date.today() + dt.timedelta(days=(7 - dt.date.today().weekday()) + 7)
WEDNESDAY = BASE_MONDAY + dt.timedelta(days=2)
FRIDAY = BASE_MONDAY + dt.timedelta(days=4)
SATURDAY = BASE_MONDAY + dt.timedelta(days=5)
SUNDAY = BASE_MONDAY + dt.timedelta(days=6)


DEFAULT_PRICE = Price(min=30, max=45, currency="USD")


def _concert(
    cid: str,
    artist: str,
    *,
    mbid: str | None = None,
    date: dt.date | None = FRIDAY,
    venue: str | None = "Club Small",
    city: str = "San Francisco",
    price: Price | None = DEFAULT_PRICE,
    festival: bool = False,
) -> Concert:
    return Concert(
        id=cid,
        name=f"{artist} Live",
        url=f"https://tickets.example/{cid}",
        artists=[Artist(name=artist, mbid=mbid or f"mbid-{normalize(artist)}")],
        date=date,
        time=dt.time(20, 0),
        time_zone="America/Los_Angeles",
        venue=venue,
        city=city,
        region="CA",
        price=price,
        festival=festival,
    )


def _parse_sse(body: str) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    name = ""
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and name:
            events[name] = json.loads(line.removeprefix("data: "))
            name = ""
    return events


async def _run_search(
    api: httpx.AsyncClient, text: str = "UKG in SF", **extra: Any
) -> tuple[str, dict[str, dict[str, Any]]]:
    payload: dict[str, Any] = {"text": text, "token": TOKEN, "time_zone": "UTC", **extra}
    resp = await api.post("/search", json=payload)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    search_id = events.get("shareable", events.get("done", {})).get("search_id")
    assert isinstance(search_id, str)
    return search_id, events


def _seed_pool(monkeypatch: pytest.MonkeyPatch, concerts: list[Concert]) -> None:
    monkeypatch.setattr(pool, "find_concerts", AsyncMock(return_value=concerts))
    tags = {a.mbid: ["uk garage"] for c in concerts for a in c.artists if a.mbid}
    monkeypatch.setattr(listenbrainz.TagFetch, "tags", AsyncMock(return_value=tags))


async def test_filter_only_sculpt_reuses_cached_grades_with_zero_model_calls_and_under_100ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concerts = [
        _concert(
            "c-cheap", "Artist Cheap", date=FRIDAY, price=Price(min=25, max=35, currency="USD")
        ),
        _concert("c-mid", "Artist Mid", date=SATURDAY, price=Price(min=60, max=80, currency="USD")),
        _concert("c-unpriced", "Artist Unpriced", date=SUNDAY, price=None),
    ]
    _seed_pool(monkeypatch, concerts)

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
        search_id, _ = await _run_search(api)
        assert jev_calls == 1
        assert explain_calls == 1

        started = time.perf_counter()
        resp = await api.post(f"/search/{search_id}/sculpt", json={"max_price": 40})
        elapsed_ms = (time.perf_counter() - started) * 1000

    assert resp.status_code == 200
    body = resp.json()
    ids = [r["concert"]["id"] for r in body["poster"]["recommendations"]]
    assert ids == ["c-cheap"]
    assert body["meta"]["unpriced_count"] == 1
    assert jev_calls == 1  # Zero new Jev calls.
    assert explain_calls == 1  # Zero new Haiku calls.
    assert elapsed_ms < 100


async def test_missing_price_and_unknown_venue_never_falsely_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concerts = [
        _concert(
            "c-club", "Club Act", venue="Intimate Club", price=Price(min=35, max=35, currency="USD")
        ),
        _concert(
            "c-arena", "Arena Act", venue="Big Arena", price=Price(min=35, max=35, currency="USD")
        ),
        _concert("c-unknown", "Unknown Room Act", venue="Mystery Warehouse", price=None),
    ]
    _seed_pool(monkeypatch, concerts)
    redis = FakeAsyncRedis()
    # Pre-cache verified venue character for Club and Arena; leave Mystery Warehouse unverified.
    await redis.set(
        venues.cache_key("Intimate Club", "San Francisco"),
        venues.VenueCharacter(
            name="Intimate Club", city="San Francisco", capacity=350, tier="Intimate club"
        ).model_dump_json(),
    )
    await redis.set(
        venues.cache_key("Big Arena", "San Francisco"),
        venues.VenueCharacter(
            name="Big Arena", city="San Francisco", capacity=18000, tier="Arena / Stadium"
        ).model_dump_json(),
    )
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, _ = await _run_search(api)

        room_resp = await api.post(f"/search/{search_id}/sculpt", json={"intimate_only": True})
        assert room_resp.status_code == 200
        room_body = room_resp.json()
        assert [r["concert"]["id"] for r in room_body["poster"]["recommendations"]] == ["c-club"]
        assert room_body["meta"]["unknown_room_count"] == 1

        price_resp = await api.post(f"/search/{search_id}/sculpt", json={"max_price": 50})
        assert price_resp.status_code == 200
        price_body = price_resp.json()
        assert sorted(r["concert"]["id"] for r in price_body["poster"]["recommendations"]) == [
            "c-arena",
            "c-club",
        ]
        assert price_body["meta"]["unpriced_count"] == 1


async def test_weekends_only_and_hide_festivals_and_empty_eliminated_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concerts = [
        _concert("c-wed", "Wed Artist", date=WEDNESDAY),
        _concert("c-fri-fest", "Fri Fest Artist", date=FRIDAY, festival=True),
        _concert("c-sat", "Sat Artist", date=SATURDAY, price=Price(min=90, max=90, currency="USD")),
        _concert("c-nodate", "No Date Artist", date=None),
    ]
    _seed_pool(monkeypatch, concerts)
    redis = FakeAsyncRedis()
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, _ = await _run_search(api)

        wknd = await api.post(
            f"/search/{search_id}/sculpt",
            json={"weekends_only": True, "hide_festivals": True},
        )
        assert wknd.status_code == 200
        assert [r["concert"]["id"] for r in wknd.json()["poster"]["recommendations"]] == ["c-sat"]

        empty = await api.post(
            f"/search/{search_id}/sculpt",
            json={"weekends_only": True, "hide_festivals": True, "max_price": 40},
        )
        assert empty.status_code == 200
        empty_body = empty.json()
        assert empty_body["poster"]["recommendations"] == []
        assert empty_body["meta"]["eliminated_by"] == "max_price"


async def test_discovery_curve_reorders_deep_cuts_vs_familiar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concerts = [
        _concert("c-mega", "Mega Star", venue="Big Arena"),
        _concert("c-under", "Underground Gem", venue="Tiny Club"),
    ]
    _seed_pool(monkeypatch, concerts)
    redis = FakeAsyncRedis()
    await redis.set(
        f"artist:lastfm:{normalize('Mega Star')}",
        ArtistProfile(name="Mega Star", listeners=3_500_000).model_dump_json(),
    )
    await redis.set(
        f"artist:lastfm:{normalize('Underground Gem')}",
        ArtistProfile(name="Underground Gem", listeners=1_200).model_dump_json(),
    )
    await redis.set(
        venues.cache_key("Big Arena", "San Francisco"),
        venues.VenueCharacter(
            name="Big Arena", city="San Francisco", tier="Arena / Stadium"
        ).model_dump_json(),
    )
    await redis.set(
        venues.cache_key("Tiny Club", "San Francisco"),
        venues.VenueCharacter(
            name="Tiny Club", city="San Francisco", tier="Intimate club"
        ).model_dump_json(),
    )
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, _ = await _run_search(api)

        deep = await api.post(f"/search/{search_id}/sculpt", json={"discovery": "deep_cuts"})
        assert deep.status_code == 200
        assert [r["concert"]["id"] for r in deep.json()["poster"]["recommendations"]] == [
            "c-under",
            "c-mega",
        ]

        familiar = await api.post(f"/search/{search_id}/sculpt", json={"discovery": "familiar"})
        assert familiar.status_code == 200
        assert [r["concert"]["id"] for r in familiar.json()["poster"]["recommendations"]] == [
            "c-mega",
            "c-under",
        ]


def test_rocchio_shift_moves_toward_liked_and_away_from_disliked() -> None:
    query = [1.0, 0.0, 0.0]
    liked = [[0.0, 1.0, 0.0]]
    disliked = [[0.0, 0.0, 1.0]]
    shifted = sculpt.rocchio_shift(query, liked, disliked)
    # Unit normalized.
    assert math.isclose(math.sqrt(sum(x * x for x in shifted)), 1.0, rel_tol=1e-6)
    # Positive component toward liked (+0.6), negative away from disliked (-0.5).
    assert shifted[1] > 0.4
    assert shifted[2] < -0.3


async def test_rocchio_boost_and_exclude_grades_only_new_candidates_and_explains_promoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 45 concerts so concert #42 starts outside the initial 40-concert shortlist (ungraded).
    concerts = [_concert(f"c-{i}", f"Pool Artist {i}", mbid=f"mbid-pool-{i}") for i in range(42)]
    concerts.append(_concert("c-new", "Steered Twin", mbid="mbid-twin"))
    _seed_pool(monkeypatch, concerts)

    graded_batches: list[list[str]] = []
    explained_batches: list[list[str]] = []
    base_model = contract_model().function
    assert base_model is not None

    async def track_jev(
        client: httpx.AsyncClient, taste: dict[str, list[str]], rows: dict[str, str]
    ) -> dict[str, int]:
        graded_batches.append(list(rows.keys()))
        return await contract_grades(client, taste, rows)

    def track_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if info.instructions == ranker.REASONS:
            text = " ".join(
                p.content
                for m in messages
                for p in m.parts
                if isinstance(p, UserPromptPart) and isinstance(p.content, str)
            )
            prompt = json.loads(text)
            explained_batches.append([row["artist"] for row in prompt["candidates"]])
        return base_model(messages, info)  # pyright: ignore[reportReturnType]

    monkeypatch.setattr(jev, "grade", track_jev)
    monkeypatch.setattr(
        cobilling,
        "find_peers",
        AsyncMock(
            return_value={
                "Pool Artist 0": [matching.CoBilledPeer(artist_key="steered twin", weight=3.0)]
            }
        ),
    )
    monkeypatch.setattr(
        supabase,
        "stored_embeddings",
        AsyncMock(
            return_value=[
                supabase.StoredEmbedding(
                    artist_key="pool artist 0", tier=1, card_hash="h0", embedding=[0.0, 1.0, 0.0]
                ),
                supabase.StoredEmbedding(
                    artist_key="pool artist 1", tier=1, card_hash="h1", embedding=[0.0, 0.0, 1.0]
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        embeddings,
        "pool_scores",
        AsyncMock(return_value={"steered twin": 0.95}),
    )
    from concert_scout import lab

    monkeypatch.setattr(lab, "insert_telemetry_rows", AsyncMock(return_value=1))

    redis = FakeAsyncRedis()
    app = create_app(
        settings_with(
            supabase_url="https://example.supabase.co",
            supabase_secret_key=SecretStr("sb-secret"),
        ),
        httpx.MockTransport(forbidden_http),
        redis,
        FunctionModel(track_model),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, _ = await _run_search(api)
        # Seed a query embedding onto the stored session to exercise Rocchio shift.
        session = await sculpt.load_session(redis, search_id)
        await sculpt.save_session(
            redis,
            search_id,
            session.model_copy(update={"query_embedding": [1.0, 0.0, 0.0]}),
        )
        assert "c-new" not in session.grades

        resp = await api.post(
            f"/search/{search_id}/sculpt",
            json={"boost_artists": ["Pool Artist 0"], "exclude_artists": ["Pool Artist 1"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    rec_ids = [r["concert"]["id"] for r in body["poster"]["recommendations"]]
    assert "c-1" not in rec_ids  # Excluded Artist dropped.
    assert "c-new" in rec_ids  # Boosted Co-Billing/Rocchio neighbour promoted.
    # Second Jev call graded ONLY the previously ungraded candidate(s), not the 40 cached ones.
    assert len(graded_batches) == 2
    assert "c-new" in graded_batches[1]
    assert "c-0" not in graded_batches[1]
    # Haiku explain was called ONLY for newly promoted recommendations lacking cached reasons.
    assert len(explained_batches) == 2
    assert "Steered Twin" in explained_batches[1]
    assert "Pool Artist 0" not in explained_batches[1]


async def test_session_expired_404_and_security_guards_and_bounds() -> None:
    redis = FakeAsyncRedis()
    app = create_app(
        settings_with(sculpts_per_hour=2),
        httpx.MockTransport(forbidden_http),
        redis,
        contract_model(),
    )
    unknown_id = share.new_search_id()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        # Bad origin -> 403.
        bad_origin = await api.post(
            f"/search/{unknown_id}/sculpt",
            json={},
            headers={"Origin": "https://evil.example"},
        )
        assert bad_origin.status_code == 403
        assert bad_origin.json()["code"] == "origin_refused"

        # Invalid bounds: >5 boosts -> 422.
        too_many_boosts = await api.post(
            f"/search/{unknown_id}/sculpt",
            json={"boost_artists": [f"A{i}" for i in range(6)]},
        )
        assert too_many_boosts.status_code == 422
        assert too_many_boosts.json()["code"] == "invalid_sculpt"

        # Invalid bounds: >10 excludes -> 422.
        too_many_excludes = await api.post(
            f"/search/{unknown_id}/sculpt",
            json={"exclude_artists": [f"E{i}" for i in range(11)]},
        )
        assert too_many_excludes.status_code == 422

        # Invalid bounds: non-positive max_price -> 422.
        bad_price = await api.post(f"/search/{unknown_id}/sculpt", json={"max_price": 0})
        assert bad_price.status_code == 422

        # Missing/expired session -> 404 session_expired (consumes 1st visitor call).
        expired = await api.post(f"/search/{unknown_id}/sculpt", json={})
        assert expired.status_code == 404
        assert expired.json()["code"] == "session_expired"

        # 2nd visitor call -> 404.
        expired2 = await api.post(f"/search/{unknown_id}/sculpt", json={})
        assert expired2.status_code == 404

        # 3rd visitor call -> 429 visitor_limit.
        limited = await api.post(f"/search/{unknown_id}/sculpt", json={})
        assert limited.status_code == 429
        assert limited.json()["code"] == "visitor_limit"


async def test_session_privacy_ttl_and_fresh_search_id_shareability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concerts = [
        _concert("c-one", "Alpha Artist", date=FRIDAY, price=Price(min=30, max=30, currency="USD")),
        _concert(
            "c-two", "Beta Artist", date=WEDNESDAY, price=Price(min=30, max=30, currency="USD")
        ),
    ]
    _seed_pool(monkeypatch, concerts)
    redis = FakeAsyncRedis()
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        search_id, _ = await _run_search(
            api,
            text="UKG near me",
            near={"lat": 37.7749, "lon": -122.4194},
        )

        raw = await redis.get(sculpt.session_key(search_id))
        assert raw is not None
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        # Never store visitor coordinates, IP, or Spotify OAuth data.
        assert "37.7749" not in text
        assert "-122.4194" not in text
        assert "127.0.0.1" not in text
        assert "access_token" not in text

        ttl = await redis.ttl(sculpt.session_key(search_id))
        assert 1700 <= ttl <= 1800

        # Sculpt returns a fresh search_id that is shareable AND chainable.
        sculpted = await api.post(f"/search/{search_id}/sculpt", json={"weekends_only": True})
        assert sculpted.status_code == 200
        new_id = sculpted.json()["search_id"]
        assert new_id != search_id

        # Share the sculpted Poster.
        shared = await api.post("/share", json={"search_id": new_id})
        assert shared.status_code == 200
        share_link = shared.json()["id"]
        read_shared = await api.get(f"/share/{share_link}")
        assert read_shared.status_code == 200
        assert [r["concert"]["id"] for r in read_shared.json()["recommendations"]] == ["c-one"]

        # Chain a reset sculpt on the fresh search_id to get both concerts back.
        chained = await api.post(f"/search/{new_id}/sculpt", json={"weekends_only": False})
        assert chained.status_code == 200
        assert sorted(r["concert"]["id"] for r in chained.json()["poster"]["recommendations"]) == [
            "c-one",
            "c-two",
        ]


async def test_sculpt_respects_spend_cap_and_search_off() -> None:
    redis = FakeAsyncRedis()
    await limits.record_spend(redis, limits.DAILY_SPEND)
    app = create_app(settings_with(), httpx.MockTransport(forbidden_http), redis, contract_model())
    sid = share.new_search_id()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
        capped = await api.post(f"/search/{sid}/sculpt", json={})
        assert capped.status_code == 503
        assert capped.json()["code"] == "budget_reached"

    app_off = create_app(
        settings_with(search_enabled=False),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app_off), base_url="http://test"
    ) as api:
        off = await api.post(f"/search/{sid}/sculpt", json={})
        assert off.status_code == 503
        assert off.json()["code"] == "search_off"
