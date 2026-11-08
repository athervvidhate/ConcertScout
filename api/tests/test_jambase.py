"""Public catalog refresh, cached Search, and source facts using captured JamBase responses."""

import datetime as dt
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import assemble, cache, matching, pool, warm
from concert_scout.app import make_services
from concert_scout.models import Artist, Concert, Place
from concert_scout.sources import jambase, ticketmaster
from tests.contracts import forbidden_http, settings_with

FIXTURES = Path(__file__).parent / "fixtures"
MOMENT = dt.datetime(2026, 11, 7, 20, tzinfo=dt.UTC)
LA = Place(name="Los Angeles", lat=34.05, lon=-118.24)


def captured(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def listings() -> list[jambase.Listing]:
    return [jambase.parse_listing(row) for row in captured("jambase-lodge.json")["events"]]


async def seed(redis: FakeAsyncRedis, age: dt.timedelta = dt.timedelta()) -> list[Concert]:
    rows = listings()
    catalog = jambase.Catalog(
        refreshed_at=MOMENT - age,
        first=MOMENT.date(),
        last=dt.date(2026, 12, 7),
        listings=rows,
    )
    await cache.write(redis, jambase.catalog_key("US-CA"), catalog, jambase.CACHE_AGE)
    return [r.concert for r in rows]


def test_captured_listing_preserves_lineup_clock_photo_and_event_page() -> None:
    concert = listings()[0].concert
    assert concert.id == "jambase:17324221"
    assert concert.source == "jambase"
    assert [a.name for a in concert.artists] == [
        "Hit the Lights",
        "Forever Came Calling",
        "Fox Royale",
    ]
    assert concert.artists[0].source_id == "jambase:44444"
    assert concert.artists[0].genre == "punk"
    assert (concert.date, concert.time) == (dt.date(2026, 11, 8), dt.time(20))
    assert concert.time_zone == "America/Los_Angeles"
    assert (concert.venue, concert.city, concert.region) == ("Lodge Room", "Los Angeles", "CA")
    assert concert.url == "https://www.jambase.com/show/hit-the-lights-lodge-room-20261108"
    assert concert.image == captured("jambase-lodge.json")["events"][0]["performer"][0]["image"]
    assert concert.price is None and concert.general_sale is None and not concert.presales


async def test_search_reads_catalog_without_provider_http_and_respects_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    rows = await seed(redis)
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[]))
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        found = await pool.find_concerts(
            client,
            redis,
            LA,
            [],
            dt.date(2026, 11, 8),
            dt.date(2026, 11, 8),
            MOMENT,
            jambase_regions=("US-CA",),
        )
    assert found == [rows[0]]
    # A public catalog identity admits place-only Concerts even without MusicBrainz links.
    assert matching.notable(found)[0].concert == rows[0]
    for place in [
        Place(name="San Diego", lat=32.7, lon=-117.2),
        Place(name="Nevada", lat=39, lon=-116, state_code="NV", country_code="US"),
    ]:
        assert await jambase.cached_concerts(redis, ["US-CA"], place, [], None, None, MOMENT) == []
    named = await jambase.cached_concerts(
        redis, ["US-CA"], None, ["hit the lights"], None, None, MOMENT
    )
    assert named == [rows[0]]
    assert (
        await jambase.cached_concerts(redis, ["US-CA"], None, ["unrelated"], None, None, MOMENT)
        == []
    )
    await seed(redis, dt.timedelta(hours=97))
    assert await jambase.cached_concerts(redis, ["US-CA"], LA, [], None, None, MOMENT) == []
    await redis.set(jambase.catalog_key("US-CA"), "broken JSON")
    assert await jambase.cached_concerts(redis, ["US-CA"], LA, [], None, None, MOMENT) == []


def test_merge_keeps_source_ids_and_separate_performances_then_stacks_them() -> None:
    jb = listings()[0].concert
    tm = jb.model_copy(update={"id": "ticketmaster-original", "source": "ticketmaster"})
    late = jb.model_copy(update={"id": "jambase:late", "time": dt.time(23)})
    room = jb.model_copy(update={"id": "jambase:other", "venue": "Other Room"})
    unknown = jb.model_copy(update={"id": "jambase:unknown", "venue": None})
    merged = pool.merge_sources([tm], [jb, late, room, unknown])
    assert [c.id for c in merged] == [tm.id, late.id, room.id, unknown.id]
    rows = matching.score_concerts(merged, matching.Taste([], [], ["punk"]), {})
    poster = assemble.from_levels({c.id: 3 for c in merged}, rows)
    assert {c.id for c in poster[0].also} == {late.id, room.id, unknown.id}


def test_merge_drops_the_same_performance_spelled_differently() -> None:
    # Pairs seen in the November 7, 2026 Los Angeles catalog against Ticketmaster.
    tm = listings()[0].concert.model_copy(
        update={
            "id": "tm",
            "source": "ticketmaster",
            "venue": "The Belasco",
            "city": "Los Angeles",
            "time": dt.time(19),
            "artists": [Artist(name="Omar Rodriguez"), Artist(name="Yuma")],
        }
    )
    variants = [
        {"venue": "Belasco Theater", "city": "Hollywood"},
        {"venue": "Belasco Theater", "time": dt.time(19, 30)},  # doors against set time
        {"venue": "Belasco Theater", "time": None},
        {"venue": "Belasco Theater", "artists": [Artist(name="YUMA")]},  # support headlines
    ]
    extra = [
        tm.model_copy(update={"id": f"jambase:{i}", "source": "jambase", **change})
        for i, change in enumerate(variants)
    ]
    assert pool.merge_sources([tm], extra) == [tm]


async def test_refresh_publishes_whole_generation_and_warm_path_uses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer unused"
        name = "jambase-quota.json" if request.url.path == "/v3/quota" else "jambase-lodge.json"
        return httpx.Response(200, json=captured(name))

    redis = FakeAsyncRedis()
    services = make_services(
        settings_with(jbd_api_key="unused"), httpx.MockTransport(respond), redis
    )
    monkeypatch.setattr(warm, "PLACES", ())
    [report] = await warm.warm(services, MOMENT)
    assert report.error is None and report.concerts == len(listings())
    event_request = requests[-1]
    assert event_request.url.params["geoStateIso"] == "US-CA"
    assert event_request.url.params["perPage"] == "100"
    found = await jambase.cached_concerts(redis, ["US-CA"], LA, [], None, None, MOMENT)
    assert found == [row.concert for row in listings()]
    [again] = await warm.warm(services, MOMENT + dt.timedelta(hours=1))
    assert again.error is None
    assert sum(r.url.path == "/v3/events" for r in requests) == 1
    assert not await redis.exists("jambase:refresh-lock")


async def test_bad_or_incomplete_refresh_retains_previous_generation() -> None:
    redis = FakeAsyncRedis()
    await seed(redis, dt.timedelta(hours=45))
    before = await redis.get(jambase.catalog_key("US-CA"))
    # Truncate an actual capture: this must never publish a seemingly complete catalog.
    body = captured("jambase-lodge.json")
    body["events"] = body["events"][:-1]
    for response in [httpx.Response(200, json=body), httpx.Response(503)]:

        def respond(request: httpx.Request, response: httpx.Response = response) -> httpx.Response:
            if request.url.path == "/v3/quota":
                return httpx.Response(200, json=captured("jambase-quota.json"))
            return response

        async with jambase.make_client("unused", httpx.MockTransport(respond)) as client:
            [report] = await jambase.refresh(client, redis, ["US-CA"], 30, MOMENT)
        assert report.error is not None
        assert await redis.get(jambase.catalog_key("US-CA")) == before
        assert not await redis.exists("jambase:refresh-lock")


async def test_quota_and_lock_guard_prevent_catalog_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A low local budget exercises the boundary using the real quota capture, unchanged.
    monkeypatch.setattr(jambase, "MONTHLY_LIMIT", 29)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, json=captured("jambase-quota.json"))

    redis = FakeAsyncRedis()
    async with jambase.make_client("unused", httpx.MockTransport(respond)) as client:
        [report] = await jambase.refresh(client, redis, ["US-CA"], 30, MOMENT)
        assert report.error == "included quota reserved; no overage"
        assert requests == ["/v3/quota"]
        await redis.set("jambase:refresh-lock", "other-writer", ex=120)
        [locked] = await jambase.refresh(client, redis, ["US-CA"], 30, MOMENT)
        assert locked.error == "refresh already running"
        # A refresh that loses the lock must never release another writer's lock.
        assert await redis.get("jambase:refresh-lock") == b"other-writer"
        assert requests == ["/v3/quota"]
