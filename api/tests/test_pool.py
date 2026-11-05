import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import pool
from concert_scout.models import Concert
from concert_scout.sources.ticketmaster import make_client
from tests.conftest import CHICAGO, tm_body, tm_record

TODAY = dt.date(2026, 11, 5)

Handler = Callable[[httpx.Request], httpx.Response]


def on(day: str, **overrides: Any) -> dict[str, Any]:
    record = tm_record(**({"id": day} | overrides))
    record["dates"]["start"]["localDate"] = day
    return record


async def find(
    handler: Handler,
    redis: FakeAsyncRedis | None = None,
    place: Any = CHICAGO,
    artists: tuple[str, ...] = (),
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[Concert]:
    async with make_client("test-key", httpx.MockTransport(handler)) as client:
        return await pool.find_concerts(
            client, redis or FakeAsyncRedis(), place, artists, start, end, TODAY
        )


def empty(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=tm_body())


def forbidden(_: httpx.Request) -> httpx.Response:
    raise AssertionError("Ticketmaster should not be called")


def recording(requests: list[httpx.Request], respond: Handler = empty) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    return handler


@pytest.mark.parametrize(
    ("start", "end", "window"),
    [
        (None, None, (TODAY, dt.date(2027, 5, 4))),
        (dt.date(2027, 1, 10), None, (dt.date(2027, 1, 10), dt.date(2027, 7, 9))),
        (None, dt.date(2026, 11, 15), (TODAY, dt.date(2026, 11, 15))),
        (dt.date(2026, 10, 1), dt.date(2026, 11, 15), (TODAY, dt.date(2026, 11, 15))),
    ],
)
def test_date_window_fills_in_what_the_search_left_open(
    start: dt.date | None, end: dt.date | None, window: tuple[dt.date, dt.date]
) -> None:
    assert pool.date_window(start, end, TODAY) == window


def test_month_chunks_cover_the_window_and_cross_the_year() -> None:
    assert pool.month_chunks(dt.date(2026, 11, 5), dt.date(2027, 1, 31)) == [
        dt.date(2026, 11, 1),
        dt.date(2026, 12, 1),
        dt.date(2027, 1, 1),
    ]


def test_a_window_that_ended_before_it_began_has_no_chunks() -> None:
    assert pool.month_chunks(dt.date(2027, 3, 5), dt.date(2026, 3, 5)) == []


async def test_the_default_window_asks_for_each_month_from_today() -> None:
    requests: list[httpx.Request] = []

    await find(recording(requests))

    windows = sorted(request.url.params["localStartDateTime"] for request in requests)
    assert len(windows) == 7
    assert windows[0] == "2026-11-05T00:00:00,2026-11-30T23:59:59"
    assert windows[-1] == "2027-05-01T00:00:00,2027-05-31T23:59:59"


async def test_chunks_are_cached_for_six_hours_including_empty_ones() -> None:
    redis = FakeAsyncRedis()

    await find(empty, redis)

    assert await redis.ttl("pool:dp3wn:2026-11") == pool.CACHE_TTL.total_seconds()
    assert await redis.ttl("pool:dp3wn:2027-05") == pool.CACHE_TTL.total_seconds()
    await find(forbidden, redis)


async def test_searches_with_different_dates_in_a_month_share_its_chunk() -> None:
    redis = FakeAsyncRedis()
    first_week = (dt.date(2026, 12, 1), dt.date(2026, 12, 7))
    last_week = (dt.date(2026, 12, 25), dt.date(2026, 12, 31))

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tm_body(on("2026-12-03"), on("2026-12-28")))

    early = await find(respond, redis, start=first_week[0], end=first_week[1])
    late = await find(forbidden, redis, start=last_week[0], end=last_week[1])

    assert [concert.id for concert in early] == ["2026-12-03"]
    assert [concert.id for concert in late] == ["2026-12-28"]


async def test_nearby_places_share_a_pool() -> None:
    redis = FakeAsyncRedis()
    await find(empty, redis)
    nearby = CHICAGO.model_copy(update={"lat": CHICAGO.lat + 0.0005})

    await find(forbidden, redis, nearby)


async def test_a_failed_chunk_is_not_cached() -> None:
    redis = FakeAsyncRedis()

    def fail(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with pytest.raises(Exception, match="status 401"):
        await find(fail, redis)

    assert await redis.get("pool:dp3wn:2026-11") is None


async def test_seed_concerts_come_first_and_appear_once() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if "keyword" in request.url.params:
            return httpx.Response(200, json=tm_body(on("2026-12-20")))
        other = {"_embedded": {"attractions": [{"name": "Someone Else"}]}}
        if request.url.params["localStartDateTime"].startswith("2026-12"):
            return httpx.Response(200, json=tm_body(on("2026-12-01", **other), on("2026-12-20")))
        return httpx.Response(200, json=tm_body())

    concerts = await find(respond, artists=("Khruangbin",))

    assert [concert.id for concert in concerts] == ["2026-12-20", "2026-12-01"]


async def test_a_lookup_is_cached_and_shared_across_date_windows() -> None:
    redis = FakeAsyncRedis()

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tm_body(on("2026-12-20"), on("2027-02-20")))

    december = (dt.date(2026, 12, 1), dt.date(2026, 12, 31))
    february = (dt.date(2027, 2, 1), dt.date(2027, 2, 28))
    first = await find(respond, redis, None, ("Khruangbin",), *december)
    second = await find(forbidden, redis, None, (" KHRUANGBIN",), *february)

    assert [concert.id for concert in first] == ["2026-12-20"]
    assert [concert.id for concert in second] == ["2027-02-20"]


async def test_no_place_skips_the_pool() -> None:
    requests: list[httpx.Request] = []

    await find(recording(requests), place=None, artists=("Khruangbin", "Four Tet"))

    assert sorted(request.url.params["keyword"] for request in requests) == [
        "Four Tet",
        "Khruangbin",
    ]


async def test_a_concert_with_no_known_date_stays_out_of_the_window() -> None:
    undated = tm_record(id="undated")
    undated["dates"]["start"]["dateTBA"] = True

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tm_body(undated))

    assert await find(respond, place=None, artists=("Khruangbin",)) == []
