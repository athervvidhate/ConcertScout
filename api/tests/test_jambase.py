"""National JamBase catalog, background sync and MusicBrainz IDs, using captured responses."""

import datetime as dt
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import assemble, catalog, matching, pool, sync, warm
from concert_scout.app import make_services
from concert_scout.models import Artist, Concert, Place
from concert_scout.sources import jambase, musicbrainz, ticketmaster
from tests.contracts import forbidden_http, settings_with

FIXTURES = Path(__file__).parent / "fixtures"
MOMENT = dt.datetime(2026, 11, 7, 20, tzinfo=dt.UTC)
TODAY = MOMENT.date()
LA = Place(name="Los Angeles", lat=34.05, lon=-118.24)
CALIFORNIA = Place(name="California", lat=36.7, lon=-119.4, state_code="CA", country_code="US")


def captured(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def lodge() -> list[jambase.Listing]:
    return [jambase.parse_listing(row) for row in captured("jambase-lodge.json")["events"]]


def page_of(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success": True,
        "pagination": {"totalItems": len(records), "totalPages": 1 if records else 0},
        "events": records,
    }


async def stored(redis: FakeAsyncRedis) -> list[Concert]:
    rows = lodge()
    await catalog.store(redis, rows, [], TODAY)
    return [r.concert for r in rows]


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "REQUEST_GAP", 0)
    monkeypatch.setattr(warm, "PLACES", ())


def test_captured_listing_preserves_lineup_clock_photo_and_event_page() -> None:
    concert = lodge()[0].concert
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


async def test_search_reads_nearby_cells_and_state_without_provider_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    concerts = await stored(redis)
    first = concerts[0]
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[]))
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        found = await pool.find_concerts(client, redis, LA, [], first.date, first.date, MOMENT)
    assert found == [first]
    # A JamBase Artist ID admits place-only Concerts without MusicBrainz links.
    assert matching.notable(found)[0].concert == first
    statewide = await catalog.concerts_near(redis, CALIFORNIA, None, None, MOMENT)
    assert {c.id for c in statewide} == {c.id for c in concerts}
    far = [
        Place(name="San Diego", lat=32.7, lon=-117.2),
        Place(name="Nevada", lat=39, lon=-116, state_code="NV", country_code="US"),
        Place(name="London", lat=51.5, lon=-0.1, country_code="GB"),
    ]
    for place in far:
        assert await catalog.concerts_near(redis, place, None, None, MOMENT) == []
    later = MOMENT + dt.timedelta(days=400)
    assert await catalog.concerts_near(redis, LA, None, None, later) == []


async def test_moved_cancelled_and_removed_events_leave_their_old_cell() -> None:
    redis = FakeAsyncRedis()
    rows = lodge()
    await catalog.store(redis, rows, [], TODAY)
    records = captured("jambase-lodge.json")["events"]
    moved = {**records[0], "startDate": "2026-12-12T20:00:00"}
    cancelled = {**records[1], "eventStatus": "cancelled"}
    deleted = {**records[2], "deletionStatus": "deleted"}
    page = jambase.parse_page(page_of([moved, cancelled, deleted]))
    assert page.removed == [records[1]["identifier"], records[2]["identifier"]]
    await catalog.store(redis, page.listings, page.removed, TODAY)
    found = {c.id: c for c in await catalog.concerts_near(redis, LA, None, None, MOMENT)}
    assert found[records[0]["identifier"]].date == dt.date(2026, 12, 12)
    assert records[1]["identifier"] not in found and records[2]["identifier"] not in found
    assert len(found) == len(rows) - 2
    cell = catalog.cell_of(rows[0].latitude or 0, rows[0].longitude or 0)
    november = await redis.hkeys(f"jambase:cell:{cell}:2026-11")
    assert november and records[0]["identifier"].encode() not in november


def test_merge_keeps_source_ids_and_separate_performances_then_stacks_them() -> None:
    jb = lodge()[0].concert
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
    tm = lodge()[0].concert.model_copy(
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


def test_batch_lookup_takes_clear_leads_and_leaves_crowded_out_names() -> None:
    body = captured("musicbrainz-batch.json")
    names: list[str] = body["names"]
    settled = musicbrainz.parse_batch(body["artists"], body["count"], names)
    assert settled["Bahamas"] == "294d06f7-fd1f-4cbe-a433-bb9cd6ac937b"  # Afie Jurvanen
    assert settled["Hit the Lights"] == "b0442f82-6322-4096-8535-b3bb776019d3"
    assert settled["YUMA"] is None  # namesakes tie, so nobody is guessed
    assert "Zzqx Nonexistent Act" not in settled  # crowded out of a full page: ask again
    complete = musicbrainz.parse_batch(body["artists"], len(body["artists"]), names)
    assert complete["Zzqx Nonexistent Act"] is None


def vendor(
    events: dict[str, list[dict[str, Any]]], requests: list[httpx.Request]
) -> httpx.MockTransport:
    """JamBase by query, MusicBrainz from the captured batch."""

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "musicbrainz.org":
            body = captured("musicbrainz-batch.json")
            return httpx.Response(200, json={"count": body["count"], "artists": body["artists"]})
        assert request.url.host == "api.data.jambase.com"
        assert request.headers["authorization"] == "Bearer unused"
        if request.url.path == "/v3/quota":
            return httpx.Response(200, json=captured("jambase-quota.json"))
        params = request.url.params
        key = params.get("geoStateIso") or ("changes" if "dateModifiedFrom" in params else "ahead")
        return httpx.Response(200, json=page_of(events.get(key, [])))

    return httpx.MockTransport(respond)


async def test_first_run_downloads_every_state_then_runs_only_change_and_window_queries() -> None:
    records = captured("jambase-lodge.json")["events"]
    requests: list[httpx.Request] = []
    redis = FakeAsyncRedis()
    transport = vendor({"US-CA": records}, requests)
    services = make_services(settings_with(jbd_api_key="unused"), transport, redis)

    steps = await sync.run(services, MOMENT)
    assert all(s.error is None for s in steps)
    downloads = [r for r in requests if "geoStateIso" in r.url.params]
    assert len(downloads) == len(sync.STATES)
    assert downloads[0].url.params["eventDateTo"] == str(TODAY + dt.timedelta(days=91))
    found = await catalog.concerts_near(redis, LA, None, None, MOMENT)
    assert len(found) == len(records)
    # The captured batch names the Lodge Room headliner, so the ID reaches a Search.
    [lights] = [c for c in found if c.id == records[0]["identifier"]]
    assert lights.artists[0].mbid == "b0442f82-6322-4096-8535-b3bb776019d3"

    requests.clear()
    transport = vendor({"changes": [{**records[1], "eventStatus": "cancelled"}]}, requests)
    services = make_services(settings_with(jbd_api_key="unused"), transport, redis)
    next_day = MOMENT + dt.timedelta(days=1)
    steps = await sync.run(services, next_day)
    assert [s.name for s in steps][:2] == ["changes", "newly in window"]
    calls = [r for r in requests if r.url.host != "musicbrainz.org"]
    assert [r.url.path for r in calls] == ["/v3/quota", "/v3/events", "/v3/events"]
    change = calls[1].url.params
    assert change["dateModifiedFrom"] == "2026-11-07T19:55:00Z"
    assert "geoStateIso" not in change
    ahead = calls[2].url.params
    assert (ahead["eventDateFrom"], ahead["eventDateTo"]) == ("2027-02-05", "2027-02-07")
    after = {c.id for c in await catalog.concerts_near(redis, LA, None, None, next_day)}
    assert records[1]["identifier"] not in after
    assert not await redis.exists(sync.LOCK)


async def test_quota_and_lock_stop_before_spending(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    redis = FakeAsyncRedis()
    services = make_services(settings_with(jbd_api_key="unused"), vendor({}, requests), redis)

    monkeypatch.setattr(sync, "MONTHLY_LIMIT", 29)  # the captured quota has 4 used
    [quota, *_] = await sync.run(services, MOMENT)
    assert quota.error == "included quota reserved; no overage"
    assert [r.url.path for r in requests if r.url.host != "musicbrainz.org"] == ["/v3/quota"]
    assert await redis.get(sync.STATE) is None

    await redis.set(sync.LOCK, "other-writer", ex=120)
    [locked] = await sync.run(services, MOMENT)
    assert locked.error == "sync already running"
    assert await redis.get(sync.LOCK) == b"other-writer"


async def test_large_state_waits_for_a_run_that_can_afford_it() -> None:
    redis = FakeAsyncRedis()
    big: dict[str, Any] = {
        "success": True,
        "pagination": {"totalItems": 500, "totalPages": 5},
        "events": [],
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=big))
    async with jambase.make_client("unused", transport) as client:
        calls = sync._Calls(client, 3, float("inf"))  # pyright: ignore[reportPrivateUsage]
        step = sync.Step(name="download US-CA")
        with pytest.raises(jambase.JamBaseError, match="5 pages exceed this run"):
            await sync._walk(calls, redis, step, {}, TODAY)  # pyright: ignore[reportPrivateUsage]
    assert calls.used == 1


async def test_a_saved_catalog_concert_reads_its_facts_from_the_catalog() -> None:
    redis = FakeAsyncRedis()
    first = (await stored(redis))[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_http)) as client:
        assert await pool.find_concert(client, redis, first.id) == first
        with pytest.raises(pool.ConcertNotFound):
            await pool.find_concert(client, redis, "jambase:0")
