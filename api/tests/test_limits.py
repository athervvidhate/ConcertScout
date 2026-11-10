import asyncio
import datetime as dt
import hashlib
import itertools
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from fakeredis import FakeAsyncRedis, FakeServer
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from concert_scout import limits


class BrokenRedis(FakeAsyncRedis):
    async def execute_command(self, *_: object, **__: object) -> None:
        raise ConnectionError


def today_key() -> str:
    return f"ticketmaster:calls:{dt.datetime.now(dt.UTC).date()}"


async def started_in_turn(
    gate: Callable[[Redis], Awaitable[None]], workers: list[Redis], callers: int
) -> list[tuple[int, float]]:
    """Callers ask one after another, spread across workers. Each reports when it started."""
    loop = asyncio.get_running_loop()
    starts: list[tuple[int, float]] = []

    async def call(n: int) -> None:
        await gate(workers[n % len(workers)])
        starts.append((n, loop.time()))

    tasks: list[asyncio.Task[None]] = []
    for n in range(callers):
        tasks.append(asyncio.create_task(call(n)))
        # Let this caller book its turn before the next one asks.
        await asyncio.sleep(0.002)
    await asyncio.gather(*tasks)
    return starts


def workers_sharing_one_redis(count: int) -> list[Redis]:
    server = FakeServer()
    return [FakeAsyncRedis(server=server) for _ in range(count)]


@pytest.mark.parametrize(
    ("gate", "gap_name"),
    [
        (limits.ticketmaster_call, "TICKETMASTER_GAP"),
        (limits.musicbrainz_call, "MUSICBRAINZ_GAP"),
    ],
)
async def test_callers_on_every_worker_go_first_come_first_served_a_full_gap_apart(
    monkeypatch: pytest.MonkeyPatch,
    gate: Callable[[Redis], Awaitable[None]],
    gap_name: str,
) -> None:
    gap = 0.04
    monkeypatch.setattr(limits, gap_name, dt.timedelta(seconds=gap))

    starts = await started_in_turn(gate, workers_sharing_one_redis(3), callers=6)

    assert [n for n, _ in starts] == list(range(6))
    times = [t for _, t in starts]
    # The sleep timer may fire a little early, never a whole gap early.
    assert all(later - earlier >= gap * 0.8 for earlier, later in itertools.pairwise(times))


async def test_a_caller_waits_only_for_those_who_asked_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gap = 0.05
    monkeypatch.setattr(limits, "MUSICBRAINZ_GAP", dt.timedelta(seconds=gap))
    redis = FakeAsyncRedis()
    loop = asyncio.get_running_loop()
    await asyncio.gather(*(limits.musicbrainz_call(redis) for _ in range(3)))
    # The three earlier turns have passed, so a caller now starts at once.
    await asyncio.sleep(gap)
    started = loop.time()

    await limits.musicbrainz_call(redis)

    assert loop.time() - started < gap / 2


async def test_a_caller_with_many_calls_takes_turns_with_one_that_asks_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gap = 0.03
    monkeypatch.setattr(limits, "TICKETMASTER_GAP", dt.timedelta(seconds=gap))
    redis = FakeAsyncRedis()
    loop = asyncio.get_running_loop()
    finished: dict[str, float] = {}

    async def caller(name: str, calls: int, delay: float) -> None:
        await asyncio.sleep(delay)
        with limits.one_caller():
            await asyncio.gather(*(limits.ticketmaster_call(redis) for _ in range(calls)))
        finished[name] = loop.time()

    started = loop.time()
    await asyncio.gather(caller("big", 10, 0), caller("small", 2, gap / 2))

    # The small caller's two calls alternate with the big one's, rather than waiting behind ten.
    assert finished["small"] - started < 6 * gap
    assert finished["big"] - started >= 11 * gap * 0.8


async def test_a_caller_alone_still_gets_every_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    gap = 0.03
    monkeypatch.setattr(limits, "TICKETMASTER_GAP", dt.timedelta(seconds=gap))
    redis = FakeAsyncRedis()
    loop = asyncio.get_running_loop()
    started = loop.time()

    with limits.one_caller():
        await asyncio.gather(*(limits.ticketmaster_call(redis) for _ in range(6)))

    assert loop.time() - started < 8 * gap


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
