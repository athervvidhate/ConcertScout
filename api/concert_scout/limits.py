import asyncio
import datetime as dt
import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# One call per slot. Any one second touches at most 4 slots, under Ticketmaster's 5 a second,
# and the count holds across every worker sharing Redis.
SLOT_SECONDS = 1 / 3
DAILY_CALLS = 5000
# MusicBrainz blocks clients that average over 1 request a second.
MUSICBRAINZ_GAP = dt.timedelta(seconds=1)


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
