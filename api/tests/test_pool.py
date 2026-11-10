"""Pool contracts at the typed Ticketmaster adapter boundary."""

import datetime as dt
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import clock, pool
from concert_scout.models import Concert, Place
from concert_scout.sources import musicbrainz, ticketmaster
from tests.contracts import CONCERTS, DAY, NOW, PLACE, forbidden_http, idle_musicbrainz


async def test_cached_chunks_are_shared_but_filtered_to_each_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = AsyncMock(return_value=CONCERTS)
    monkeypatch.setattr(ticketmaster, "find_concerts", fetch)
    redis = FakeAsyncRedis()
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        first = await pool.find_concerts(
            client, idle_musicbrainz(), redis, PLACE, [], DAY, DAY, NOW
        )
        second = await pool.find_concerts(
            client,
            idle_musicbrainz(),
            redis,
            PLACE,
            [],
            DAY + dt.timedelta(days=1),
            DAY + dt.timedelta(days=1),
            NOW,
        )
    assert [c.id for c in first] == [CONCERTS[0].id]
    assert [c.id for c in second] == [CONCERTS[1].id]
    assert fetch.await_count == 1
    assert (
        0
        < await redis.ttl(f"pool:{ticketmaster.rounded_point(PLACE)}:50:{DAY:%Y-%m}")
        <= pool.CACHE_TTL.total_seconds()
    )


async def test_seed_records_survive_pool_paging_and_ids_are_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[CONCERTS[0]]))
    monkeypatch.setattr(ticketmaster, "find_artist_concerts", AsyncMock(return_value=CONCERTS))
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        found = await pool.find_concerts(
            client,
            idle_musicbrainz(),
            FakeAsyncRedis(),
            PLACE,
            ["Contract Artist"],
            DAY,
            DAY + dt.timedelta(days=1),
            NOW,
        )
    assert {c.id for c in found} == {c.id for c in CONCERTS[:2]}
    assert len(found) == 2


async def test_seed_artists_keep_far_off_concerts_unless_the_search_sets_an_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    far_off = DAY + pool.DEFAULT_WINDOW + dt.timedelta(days=10)
    seed_tour = CONCERTS[0].model_copy(update={"id": "seed-tour", "date": far_off})
    pool_listing = CONCERTS[0].model_copy(update={"id": "pool-listing", "date": far_off})
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[pool_listing]))
    monkeypatch.setattr(ticketmaster, "find_artist_concerts", AsyncMock(return_value=[seed_tour]))
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        no_dates = await pool.find_concerts(
            client,
            idle_musicbrainz(),
            FakeAsyncRedis(),
            PLACE,
            ["Contract Artist"],
            None,
            None,
            NOW,
        )
        with_end = await pool.find_concerts(
            client,
            idle_musicbrainz(),
            FakeAsyncRedis(),
            PLACE,
            ["Contract Artist"],
            None,
            far_off - dt.timedelta(days=1),
            NOW,
        )
    assert [c.id for c in no_dates] == ["seed-tour"]
    assert with_end == []


async def test_states_and_city_circles_never_share_cache_or_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks, seeds = AsyncMock(return_value=[]), AsyncMock(return_value=[])
    monkeypatch.setattr(ticketmaster, "find_concerts", chunks)
    monkeypatch.setattr(ticketmaster, "find_artist_concerts", seeds)
    texas = Place(name="Texas", lat=31.1, lon=-99.1, state_code="TX", country_code="US")
    redis = FakeAsyncRedis()
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        await pool.find_concerts(
            client, idle_musicbrainz(), redis, texas, ["Contract Artist"], DAY, DAY, NOW
        )
        assert chunks.call_args.kwargs["state"] == seeds.call_args.kwargs["state"] == ("US", "TX")
        assert chunks.call_args.args[2] is None
        await pool.find_concerts(
            client, idle_musicbrainz(), redis, texas, ["Contract Artist"], DAY, DAY, NOW
        )
        assert chunks.await_count == 1 and seeds.await_count == 1
        await pool.find_concerts(client, idle_musicbrainz(), redis, PLACE, [], DAY, DAY, NOW)
        assert chunks.await_count == 2
        assert chunks.call_args.kwargs["state"] is None
        assert chunks.call_args.args[2] == ticketmaster.rounded_point(PLACE)


def test_calendar_chunks_cover_each_day_across_a_year_boundary() -> None:
    first, last = dt.date(2026, 12, 15), dt.date(2027, 2, 10)
    months = clock.months(first, last)
    assert len(months) == len(set(months))
    day = first
    while day <= last:
        assert day.replace(day=1) in months
        day += dt.timedelta(days=1)


async def test_elsewhere_makes_one_call_and_caches_it() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"page": {"totalElements": 0}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="https://source.test"
    )
    redis = FakeAsyncRedis()
    for _ in range(2):
        assert await pool.find_elsewhere(client, redis, "hyperpop", None, None, NOW) == []
    assert len(calls) == 1
    assert calls[0].url.params["keyword"] == "hyperpop"
    assert calls[0].url.params["size"] == str(pool.ELSEWHERE_SIZE)


@pytest.mark.parametrize(
    ("visitor", "venue", "kept"),
    [
        pytest.param(
            "America/Los_Angeles", "America/New_York", False, id="already-over-in-the-east"
        ),
        pytest.param("Europe/London", "America/Los_Angeles", True, id="still-tonight-in-the-west"),
        pytest.param("America/Los_Angeles", "America/Los_Angeles", True, id="same-zone"),
    ],
)
async def test_a_concert_is_over_by_the_calendar_at_its_own_venue(
    monkeypatch: pytest.MonkeyPatch, visitor: str, venue: str, kept: bool
) -> None:
    moment = dt.datetime(2026, 11, 7, 7, 30, tzinfo=dt.UTC)  # 11:30 PM Nov 6 in Los Angeles
    tonight = CONCERTS[0].model_copy(update={"date": dt.date(2026, 11, 6), "time_zone": venue})
    fetch = AsyncMock(return_value=[tonight])
    monkeypatch.setattr(ticketmaster, "find_concerts", fetch)
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        found = await pool.find_concerts(
            client,
            idle_musicbrainz(),
            FakeAsyncRedis(),
            PLACE,
            [],
            None,
            None,
            moment.astimezone(ZoneInfo(visitor)),
        )
    assert bool(found) is kept
    assert tonight.date is not None
    assert min(call.args[3] for call in fetch.await_args_list) <= tonight.date


async def test_each_page_and_cached_chunk_is_reported_as_it_arrives() -> None:
    def event(id_: str) -> dict[str, object]:
        return {
            "id": id_,
            "name": f"Show {id_}",
            "url": "https://tickets.example",
            "dates": {"start": {"localDate": f"{DAY}"}},
            "_embedded": {"attractions": [{"name": f"Artist {id_}"}]},
        }

    def respond(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        body = {
            "page": {"totalElements": ticketmaster.PAGE_SIZE + 1},
            "_embedded": {"events": [event(f"{page}")]},
        }
        return httpx.Response(200, json=body)

    redis = FakeAsyncRedis()
    seen: list[list[str]] = []

    def found(concerts: list[Concert]) -> None:
        seen.append([c.id for c in concerts])

    async with ticketmaster.make_client("unused", httpx.MockTransport(respond)) as client:
        first = await pool.find_concerts(
            client, idle_musicbrainz(), redis, PLACE, [], DAY, DAY, NOW, found
        )
        assert sorted(seen) == [["0"], ["1"]]
        seen.clear()
        await pool.find_concerts(client, idle_musicbrainz(), redis, PLACE, [], DAY, DAY, NOW, found)
    assert seen == [[c.id for c in first]]


async def test_only_concerts_in_the_window_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=CONCERTS))
    seen: list[str] = []
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        redis = FakeAsyncRedis()
        await pool.find_concerts(client, idle_musicbrainz(), redis, PLACE, [], DAY, DAY, NOW)
        await pool.find_concerts(
            client,
            idle_musicbrainz(),
            redis,
            PLACE,
            [],
            DAY,
            DAY,
            NOW,
            lambda cs: seen.extend(c.id for c in cs),
        )
    assert seen == [CONCERTS[0].id]


def unbilled(id: str, title: str) -> Concert:
    return CONCERTS[0].model_copy(update={"id": id, "name": title, "artists": []})


def musicbrainz_holding(
    held: list[tuple[str, str, int]], requests: list[httpx.Request]
) -> httpx.MockTransport:
    """A MusicBrainz that holds (name, id, score) artists and answers every search with them."""

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        artists = [{"name": name, "id": id_, "score": score} for name, id_, score in held]
        return httpx.Response(200, json={"count": len(artists), "artists": artists})

    return httpx.MockTransport(respond)


async def test_a_title_bills_an_artist_only_when_musicbrainz_confirms_it_and_the_pool_caches_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listings = [
        unbilled("list", "Triptides, Eunoian, Nobody Known"),
        unbilled("tie", "Yuma: Everything Tour"),
        unbilled("tour", "JEFF CROSBY'S ANNUAL HOMECOMING RUN"),
        CONCERTS[1],
    ]
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=listings))
    requests: list[httpx.Request] = []
    held = [
        ("Triptides", "mbid-triptides", 100),
        ("Eunoian", "mbid-eunoian", 100),
        ("Yuma", "mbid-yuma-1", 100),
        ("YUMA", "mbid-yuma-2", 99),
    ]
    redis = FakeAsyncRedis()
    async with (
        ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client,
        musicbrainz.make_client(musicbrainz_holding(held, requests)) as names,
    ):
        found = await pool.find_concerts(
            client, names, redis, PLACE, [], DAY, DAY + dt.timedelta(1), NOW
        )
        again = await pool.find_concerts(
            client, names, redis, PLACE, [], DAY, DAY + dt.timedelta(1), NOW
        )

    by_id = {c.id: c for c in found}
    # Confirmed names join the Lineup, with the MusicBrainz ID that confirmed them.
    assert [(a.name, a.mbid) for a in by_id["list"].artists] == [
        ("Triptides", "mbid-triptides"),
        ("Eunoian", "mbid-eunoian"),
    ]
    # A tie between namesakes guesses nobody, and a name MusicBrainz lacks stays out.
    assert by_id["tie"].artists == [] and by_id["tour"].artists == []
    # The title stays the Concert's name, and a Concert with a Lineup is left alone.
    assert by_id["tour"].name == "JEFF CROSBY'S ANNUAL HOMECOMING RUN"
    assert by_id[CONCERTS[1].id] == CONCERTS[1]
    # One batched search for every name, kept with the pool so a repeat asks nothing.
    assert len(requests) == 1
    assert again == found


async def test_a_name_musicbrainz_answered_before_costs_no_call() -> None:
    redis = FakeAsyncRedis()
    requests: list[httpx.Request] = []
    held = [("Triptides", "mbid-triptides", 100)]
    async with musicbrainz.make_client(musicbrainz_holding(held, requests)) as names:
        first = await musicbrainz.confirm(names, redis, ["Triptides", "Unknown Act"])
        second = await musicbrainz.confirm(names, redis, ["triptides", "UNKNOWN ACT"])
    assert first == second == {"triptides": "mbid-triptides"}
    assert len(requests) == 1


async def test_a_search_asks_musicbrainz_for_a_bounded_number_of_new_names() -> None:
    requests: list[httpx.Request] = []
    wanted = [f"Band {n}" for n in range(musicbrainz.BATCH_SIZE * 5)]
    async with musicbrainz.make_client(musicbrainz_holding([], requests)) as names:
        redis = FakeAsyncRedis()
        await musicbrainz.confirm(names, redis, wanted)
        assert len(requests) == musicbrainz.TITLE_BATCHES
        # The next Search asks for the names after those, never the ones already answered.
        await musicbrainz.confirm(names, redis, wanted)
    assert len(requests) == 2 * musicbrainz.TITLE_BATCHES


async def test_a_name_crowded_off_a_full_page_is_not_asked_again_for_a_week() -> None:
    requests: list[httpx.Request] = []

    def full_page(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # 100 namesakes of the first name fill the page, so the other names never appear on it.
        artists = [
            {"name": "Triptides", "id": f"mbid-{n}", "score": 100 if n == 0 else 90}
            for n in range(100)
        ]
        return httpx.Response(200, json={"count": 500, "artists": artists})

    wanted = ["Triptides", "Swift Nation", "Rock"]
    redis = FakeAsyncRedis()
    async with musicbrainz.make_client(httpx.MockTransport(full_page)) as names:
        first = await musicbrainz.confirm(names, redis, wanted)
        second = await musicbrainz.confirm(names, redis, wanted)

    assert first == second == {"triptides": "mbid-0"}
    assert len(requests) == 1
    assert 0 < await redis.ttl("title:swift nation") <= musicbrainz.CACHE_TTL.total_seconds()


async def test_a_musicbrainz_outage_leaves_titles_unread_and_the_pool_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = unbilled("list", "Triptides, Eunoian")
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[listing]))

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with (
        ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client,
        musicbrainz.make_client(httpx.MockTransport(down)) as names,
    ):
        found = await pool.find_concerts(client, names, FakeAsyncRedis(), PLACE, [], DAY, DAY, NOW)
    assert [c.id for c in found] == ["list"] and found[0].artists == []
