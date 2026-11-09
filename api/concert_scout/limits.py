import asyncio
import datetime as dt
import hashlib
import logging
import math
import time
from decimal import Decimal

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# One call per slot. Any one second touches at most 4 slots, under Ticketmaster's 5 a second,
# and the count holds across every worker sharing Redis.
SLOT_SECONDS = 1 / 3
DAILY_CALLS = 5000
# MusicBrainz blocks clients that average over 1 request a second.
MUSICBRAINZ_GAP = dt.timedelta(seconds=1)


SEARCHES_PER_HOUR = 10
TASTE_PER_HOUR = 30
ARTIST_PER_HOUR = 120
# Each save or import looks its Concerts up on Ticketmaster.
SAVES_PER_HOUR = 120
# Each share writes one small record that lives for 90 days.
SHARES_PER_HOUR = 30
FEEDBACK_PER_HOUR = 5
FEEDBACK_EVERYONE_PER_HOUR = 20
HOUR_SECONDS = 3600
DAILY_SPEND = Decimal(1)
# Eval runs are paid tuning work by the owner, so they get more room per day than visitors.
EVAL_DAILY_SPEND = Decimal(3)
MONTHLY_SPEND = Decimal(10)
MICRODOLLARS = 1_000_000


class VisitorLimitReached(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


class SpendCapReached(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


class DailyLimitReached(Exception):
    """Today's Ticketmaster calls are spent."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


async def ticketmaster_call(redis: Redis) -> None:
    """Count one call against today's limit, then wait for a free slot to make it."""
    try:
        await _count_today(redis)
        await _wait_for_slot(redis)
    except RedisError as exc:
        # Without Redis nothing is shared, so pace this caller alone and let the Search go on.
        logger.warning("Limiter failed: %s", type(exc).__name__)
        await asyncio.sleep(SLOT_SECONDS)


async def musicbrainz_call(redis: Redis) -> None:
    """Wait until a full gap has passed since the last MusicBrainz call by any worker."""
    try:
        while True:
            if await redis.set("musicbrainz:gate", 1, nx=True, px=MUSICBRAINZ_GAP):
                return
            await asyncio.sleep(MUSICBRAINZ_GAP.total_seconds() / 20)
    except RedisError as exc:
        logger.warning("Limiter failed: %s", type(exc).__name__)
        await asyncio.sleep(MUSICBRAINZ_GAP.total_seconds())


async def visitor_call(redis: Redis, bucket: str, ip: str, limit: int) -> None:
    """Count one call for this visitor this hour. Redis failures are the caller's to handle."""
    now = time.time()
    hour = int(now // HOUR_SECONDS)
    # Redis only needs to tell visitors apart, so it never holds an address.
    visitor = hashlib.sha256(ip.encode()).hexdigest()[:32]
    key = f"visitor:{bucket}:{visitor}:{hour}"
    calls = await redis.incr(key)
    if calls == 1:
        await redis.expire(key, HOUR_SECONDS)
    if calls > limit:
        raise VisitorLimitReached(HOUR_SECONDS - int(now % HOUR_SECONDS))


def _spend_keys(now: dt.datetime) -> tuple[str, str]:
    return f"spend:day:{now.date()}", f"spend:month:{now:%Y-%m}"


def _seconds_until(moment: dt.datetime, now: dt.datetime) -> int:
    return int((moment - now).total_seconds()) + 1


async def check_spend(redis: Redis, daily: Decimal = DAILY_SPEND) -> None:
    """Raises at either cap. Redis failures are the caller's to handle."""
    now = dt.datetime.now(dt.UTC)
    day_key, month_key = _spend_keys(now)
    day, month = await redis.mget([day_key, month_key])
    if Decimal(int(month or 0)) / MICRODOLLARS >= MONTHLY_SPEND:
        next_month = (now.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        start = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        raise SpendCapReached(_seconds_until(start, now))
    if Decimal(int(day or 0)) / MICRODOLLARS >= daily:
        tomorrow = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.UTC)
        raise SpendCapReached(_seconds_until(tomorrow, now))


async def record_spend(redis: Redis, cost: Decimal) -> None:
    amount = math.ceil(cost * MICRODOLLARS)
    if not amount:
        return
    day_key, month_key = _spend_keys(dt.datetime.now(dt.UTC))
    try:
        async with redis.pipeline(transaction=False) as pipeline:
            pipeline.incrby(day_key, amount)
            pipeline.expire(day_key, dt.timedelta(days=2))
            pipeline.incrby(month_key, amount)
            pipeline.expire(month_key, dt.timedelta(days=40))
            await pipeline.execute()
    except RedisError as exc:
        logger.warning("Spend not recorded: %s", type(exc).__name__)


async def _count_today(redis: Redis) -> None:
    now = dt.datetime.now(dt.UTC)
    key = f"ticketmaster:calls:{now.date()}"
    calls = await redis.incr(key)
    if calls == 1:
        await redis.expire(key, dt.timedelta(days=2))
    if calls > DAILY_CALLS:
        tomorrow = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.UTC)
        raise DailyLimitReached(int((tomorrow - now).total_seconds()) + 1)


async def _wait_for_slot(redis: Redis) -> None:
    while True:
        slot = int(time.time() / SLOT_SECONDS)
        if await redis.set(f"ticketmaster:slot:{slot}", 1, nx=True, ex=2):
            return
        await asyncio.sleep(SLOT_SECONDS - time.time() % SLOT_SECONDS)
