import asyncio
import calendar
import datetime as dt
from collections.abc import Sequence

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache
from concert_scout.models import Concert, Place
from concert_scout.names import normalize
from concert_scout.sources import ticketmaster

CACHE_TTL = dt.timedelta(hours=6)
DEFAULT_WINDOW = dt.timedelta(days=180)


class CachedConcerts(BaseModel):
    concerts: list[Concert]


def date_window(
    start: dt.date | None, end: dt.date | None, today: dt.date
) -> tuple[dt.date, dt.date]:
    first = max(start or today, today)
    return first, end or first + DEFAULT_WINDOW


def month_chunks(first: dt.date, last: dt.date) -> list[dt.date]:
    """The first day of each calendar month the window touches."""
    months: list[dt.date] = []
    month = first.replace(day=1)
    while month <= last:
        months.append(month)
        month = (month + dt.timedelta(days=31)).replace(day=1)
    return months


async def find_concerts(
    client: httpx.AsyncClient,
    redis: Redis,
    place: Place | None,
    artists: Sequence[str],
    start: dt.date | None,
    end: dt.date | None,
    today: dt.date,
) -> list[Concert]:
    """Every Concert for the Search, seed Artists first, then the pool soonest first.

    Chunks and lookups stay whole in the cache, so any date window can share them.
    """
    first, last = date_window(start, end, today)
    state = (
        (place.country_code, place.state_code)
        if place and place.country_code and place.state_code
        else None
    )
    point = ticketmaster.rounded_point(place) if place and not state else None
    radius = (place.radius_miles if place else None) or ticketmaster.RADIUS_MILES
    seeds = await asyncio.gather(
        *(_artist(client, redis, name, point, state, radius) for name in artists)
    )
    chunks: list[list[Concert]] = []
    if state or point:
        months = month_chunks(first, last)
        chunks = await asyncio.gather(
            *(_chunk(client, redis, point, m, today, state, radius) for m in months)
        )
    # An Artist lookup already holds every listed date, so only a chosen end cuts it short.
    seed_last = end or dt.date.max
    from_seeds = [c for group in seeds for c in group if _within(c, first, seed_last)]
    from_pool = [c for group in chunks for c in group if _within(c, first, last)]
    return list({c.id: c for c in [*from_seeds, *from_pool]}.values())


def _within(concert: Concert, first: dt.date, last: dt.date) -> bool:
    return concert.date is not None and first <= concert.date <= last


def _scope(point: str | None, state: tuple[str, str] | None, radius: int) -> str:
    if state:
        return ":".join(state)
    return f"{point}:{radius}" if point else "anywhere"


async def _chunk(
    client: httpx.AsyncClient,
    redis: Redis,
    point: str | None,
    month: dt.date,
    today: dt.date,
    state: tuple[str, str] | None,
    radius: int,
) -> list[Concert]:
    key = f"pool:{_scope(point, state, radius)}:{month:%Y-%m}"
    if cached := await cache.read(redis, key, CachedConcerts):
        return cached.concerts
    last_day = calendar.monthrange(month.year, month.month)[1]
    concerts = await ticketmaster.find_concerts(
        client,
        redis,
        point,
        max(month, today),
        month.replace(day=last_day),
        state=state,
        radius=radius,
    )
    await cache.write(redis, key, CachedConcerts(concerts=concerts), CACHE_TTL)
    return concerts


async def _artist(
    client: httpx.AsyncClient,
    redis: Redis,
    name: str,
    point: str | None,
    state: tuple[str, str] | None,
    radius: int,
) -> list[Concert]:
    key = f"artist:{_scope(point, state, radius)}:{normalize(name)}"
    if cached := await cache.read(redis, key, CachedConcerts):
        return cached.concerts
    concerts = await ticketmaster.find_artist_concerts(
        client, redis, name, point, state=state, radius=radius
    )
    await cache.write(redis, key, CachedConcerts(concerts=concerts), CACHE_TTL)
    return concerts
