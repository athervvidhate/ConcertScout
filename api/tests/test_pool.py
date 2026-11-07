"""Pool contracts at the typed Ticketmaster adapter boundary."""

import datetime as dt
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import pool
from concert_scout.models import Place
from concert_scout.sources import ticketmaster
from tests.contracts import CONCERTS, DAY, PLACE, forbidden_http


async def test_cached_chunks_are_shared_but_filtered_to_each_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = AsyncMock(return_value=CONCERTS)
    monkeypatch.setattr(ticketmaster, "find_concerts", fetch)
    redis = FakeAsyncRedis()
    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as client:
        first = await pool.find_concerts(client, redis, PLACE, [], DAY, DAY, DAY)
        second = await pool.find_concerts(
            client, redis, PLACE, [], DAY + dt.timedelta(days=1), DAY + dt.timedelta(days=1), DAY
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
            FakeAsyncRedis(),
            PLACE,
            ["Contract Artist"],
            DAY,
            DAY + dt.timedelta(days=1),
            DAY,
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
            client, FakeAsyncRedis(), PLACE, ["Contract Artist"], None, None, DAY
        )
        with_end = await pool.find_concerts(
            client,
            FakeAsyncRedis(),
            PLACE,
            ["Contract Artist"],
            None,
            far_off - dt.timedelta(days=1),
            DAY,
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
        await pool.find_concerts(client, redis, texas, ["Contract Artist"], DAY, DAY, DAY)
        assert chunks.call_args.kwargs["state"] == seeds.call_args.kwargs["state"] == ("US", "TX")
        assert chunks.call_args.args[2] is None
        await pool.find_concerts(client, redis, texas, ["Contract Artist"], DAY, DAY, DAY)
        assert chunks.await_count == 1 and seeds.await_count == 1
        await pool.find_concerts(client, redis, PLACE, [], DAY, DAY, DAY)
        assert chunks.await_count == 2
        assert chunks.call_args.kwargs["state"] is None
        assert chunks.call_args.args[2] == ticketmaster.rounded_point(PLACE)


def test_calendar_chunks_cover_each_day_across_a_year_boundary() -> None:
    first, last = dt.date(2026, 12, 15), dt.date(2027, 2, 10)
    months = pool.month_chunks(first, last)
    assert len(months) == len(set(months))
    day = first
    while day <= last:
        assert day.replace(day=1) in months
        day += dt.timedelta(days=1)
