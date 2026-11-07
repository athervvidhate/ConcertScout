import asyncio
import datetime as dt
import hashlib
import time
from decimal import Decimal

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError

from concert_scout import limits


class BrokenRedis(FakeAsyncRedis):
    async def execute_command(self, *_: object, **__: object) -> None:
        raise ConnectionError


def today_key() -> str:
    return f"ticketmaster:calls:{dt.datetime.now(dt.UTC).date()}"


async def test_calls_sharing_redis_each_get_their_own_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "SLOT_SECONDS", 0.02)
    redis = FakeAsyncRedis()
    loop = asyncio.get_running_loop()
    started = loop.time()

    await asyncio.gather(*(limits.ticketmaster_call(redis) for _ in range(5)))

    # Five slots end to end, so at least the four gaps between them must pass.
    assert loop.time() - started >= 4 * 0.02 - 0.02


async def test_calls_count_towards_today_and_the_count_expires() -> None:
    redis = FakeAsyncRedis()

    await limits.ticketmaster_call(redis)
    await limits.ticketmaster_call(redis)

    assert await redis.get(today_key()) == b"2"
    assert 0 < await redis.ttl(today_key()) <= 2 * 86400


async def test_the_last_call_of_the_day_is_allowed_and_the_next_is_refused() -> None:
    redis = FakeAsyncRedis()
    await redis.set(today_key(), limits.DAILY_CALLS - 1)

    await limits.ticketmaster_call(redis)
    with pytest.raises(limits.DailyLimitReached) as caught:
        await limits.ticketmaster_call(redis)

    assert 0 < caught.value.retry_after <= 86400


async def test_a_redis_outage_never_stops_a_search() -> None:
    await limits.ticketmaster_call(BrokenRedis())


async def test_musicbrainz_calls_keep_a_full_gap_across_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "MUSICBRAINZ_GAP", dt.timedelta(milliseconds=30))
    redis = FakeAsyncRedis()
    loop = asyncio.get_running_loop()
    started = loop.time()

    await asyncio.gather(*(limits.musicbrainz_call(redis) for _ in range(4)))

    assert loop.time() - started >= 3 * 0.03 - 0.01


async def test_musicbrainz_calls_pace_themselves_without_redis() -> None:
    await limits.musicbrainz_call(BrokenRedis())


async def test_visitor_limits_count_each_client_separately() -> None:
    redis = FakeAsyncRedis()

    await limits.visitor_call(redis, "search", "1.1.1.1", 1)

    with pytest.raises(limits.VisitorLimitReached) as caught:
        await limits.visitor_call(redis, "search", "1.1.1.1", 1)
    assert 0 < caught.value.retry_after <= limits.HOUR_SECONDS
    await limits.visitor_call(redis, "search", "2.2.2.2", 1)


async def test_redis_never_holds_a_visitor_address() -> None:
    redis = FakeAsyncRedis()

    await limits.visitor_call(redis, "search", "1.1.1.1", 1)

    visitor = hashlib.sha256(b"1.1.1.1").hexdigest()[:32]
    hour = int(time.time() // limits.HOUR_SECONDS)
    assert await redis.get(f"visitor:search:{visitor}:{hour}") == b"1"
    assert await redis.get(f"visitor:search:1.1.1.1:{hour}") is None


async def test_spend_adds_up_to_the_daily_cap() -> None:
    redis = FakeAsyncRedis()

    await limits.record_spend(redis, Decimal("0.999999"))
    await limits.check_spend(redis)
    await limits.record_spend(redis, Decimal("0.000001"))

    with pytest.raises(limits.SpendCapReached) as caught:
        await limits.check_spend(redis)
    assert 0 < caught.value.retry_after <= 86401


async def test_the_monthly_cap_holds_after_the_day_rolls_over() -> None:
    redis = FakeAsyncRedis()
    now = dt.datetime.now(dt.UTC)
    await redis.set(f"spend:month:{now:%Y-%m}", 10 * limits.MICRODOLLARS)

    with pytest.raises(limits.SpendCapReached) as caught:
        await limits.check_spend(redis)
    assert caught.value.retry_after > 0


async def test_a_tiny_cost_still_counts() -> None:
    redis = FakeAsyncRedis()

    await limits.record_spend(redis, Decimal("0.0000001"))

    assert await redis.get(f"spend:day:{dt.datetime.now(dt.UTC).date()}") == b"1"


async def test_eval_runs_may_pass_the_visitor_daily_cap_but_not_their_own() -> None:
    redis = FakeAsyncRedis()
    await limits.record_spend(redis, limits.DAILY_SPEND)

    await limits.check_spend(redis, limits.EVAL_DAILY_SPEND)
    await limits.record_spend(redis, limits.EVAL_DAILY_SPEND - limits.DAILY_SPEND)
    with pytest.raises(limits.SpendCapReached):
        await limits.check_spend(redis, limits.EVAL_DAILY_SPEND)
