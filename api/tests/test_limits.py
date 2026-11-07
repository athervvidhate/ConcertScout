import asyncio
import datetime as dt

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
