import asyncio
import calendar
import datetime as dt
from collections.abc import Sequence

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import cache, clock
from concert_scout.models import Concert, Place
from concert_scout.names import normalize
from concert_scout.sources import jambase, ticketmaster

CACHE_TTL = dt.timedelta(hours=6)
ELSEWHERE_SIZE = 12
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
    now: dt.datetime,
    on_found: ticketmaster.OnPage | None = None,
    *,
    jambase_regions: Sequence[str] = (),
) -> list[Concert]:
    """Every Concert for the Search, seed Artists first, then the pool soonest first.

    Chunks and lookups stay whole in the cache, so any date window can share them. `on_found`
    sees each page's Concerts in the window as they arrive, so later steps can start early.
    """
    first, last = date_window(start, end, now.date())
    state = (
        (place.country_code, place.state_code)
        if place and place.country_code and place.state_code
        else None
    )
    point = ticketmaster.rounded_point(place) if place and not state else None
    radius = (place.radius_miles if place else None) or ticketmaster.RADIUS_MILES
    # An Artist lookup already holds every listed date, so only a chosen end cuts it short.
    seed_last = end or dt.date.max

    def found_within(last_day: dt.date) -> ticketmaster.OnPage | None:
        if on_found is None:
            return None
        report = on_found
        return lambda concerts: report([c for c in concerts if _ahead(c, start, last_day, now)])

    seeds = await asyncio.gather(
        *(
            _artist(client, redis, name, point, state, radius, found_within(seed_last))
            for name in artists
        )
    )
    chunks: list[list[Concert]] = []
    if state or point:
        earliest = _earliest(first, now.date())
        months = month_chunks(earliest, last)
        chunks = await asyncio.gather(
            *(
                _chunk(client, redis, point, m, earliest, state, radius, found_within(last))
                for m in months
            )
        )
    from_seeds = [c for group in seeds for c in group if _ahead(c, start, seed_last, now)]
    from_pool = [c for group in chunks for c in group if _ahead(c, start, last, now)]
    primary = list({c.id: c for c in [*from_seeds, *from_pool]}.values())
    extra = await jambase.cached_concerts(redis, jambase_regions, place, artists, start, end, now)
    merged = merge_sources(primary, extra)
    if on_found and (added := merged[len(primary) :]):
        on_found(added)
    return merged


# Words every venue name shares, so they never prove two listings are the same room.
_VENUE_FILLER = frozenset(
    "the a an at of and by on in theatre theater theatres theaters club room hall bar "
    "lounge center centre venue house live music ca los angeles".split()
)
# Sources disagree on doors versus set time. Early and late sets sit further apart.
_SAME_SET = dt.timedelta(minutes=90)


def _venue_words(venue: str | None) -> set[str]:
    return {w for w in normalize(venue or "").split() if w not in _VENUE_FILLER}


def _same_set(a: dt.time | None, b: dt.time | None) -> bool:
    if a is None or b is None:
        return True
    day = dt.date(2000, 1, 1)
    gap = dt.datetime.combine(day, a) - dt.datetime.combine(day, b)
    return abs(gap) <= _SAME_SET


def merge_sources(primary: Sequence[Concert], extra: Sequence[Concert]) -> list[Concert]:
    """Prefer the primary source's listing of a performance; keep other sets, rooms and dates.

    Sources spell venues and cities differently, so a duplicate is the same date, the extra
    headliner anywhere in the primary Lineup, a shared distinctive venue word and a nearby
    start time.
    """
    by_artist: dict[tuple[dt.date, str], list[Concert]] = {}
    for concert in primary:
        if concert.date:
            for artist in concert.artists:
                by_artist.setdefault((concert.date, normalize(artist.name)), []).append(concert)
    merged = list(primary)
    for concert in extra:
        matches = (
            by_artist.get((concert.date, normalize(concert.artists[0].name)), [])
            if concert.date and concert.artists
            else []
        )
        words = _venue_words(concert.venue)
        if not any(
            words & _venue_words(other.venue) and _same_set(concert.time, other.time)
            for other in matches
        ):
            merged.append(concert)
    return merged


async def find_elsewhere(
    client: httpx.AsyncClient,
    redis: Redis,
    keyword: str,
    start: dt.date | None,
    end: dt.date | None,
    now: dt.datetime,
) -> list[Concert]:
    """Concerts that match a Search's words in any place. This costs one Ticketmaster call."""
    first, last = date_window(start, end, now.date())
    earliest = _earliest(first, now.date())
    key = f"elsewhere:{normalize(keyword)}:{earliest}:{last}"
    if cached := await cache.read(redis, key, CachedConcerts):
        concerts = cached.concerts
    else:
        concerts = await ticketmaster.find_keyword(
            client, redis, keyword, earliest, last, ELSEWHERE_SIZE
        )
        await cache.write(redis, key, CachedConcerts(concerts=concerts), CACHE_TTL)
    return [concert for concert in concerts if _ahead(concert, start, last, now)]


def _earliest(first: dt.date, today: dt.date) -> dt.date:
    """The first day to ask for. A venue can still be on the visitor's yesterday."""
    return first - dt.timedelta(days=1) if first == today else first


def _ahead(concert: Concert, start: dt.date | None, last: dt.date, now: dt.datetime) -> bool:
    """Whether a Concert is in the window and not over by the calendar at its own venue."""
    if concert.date is None:
        return False
    venue_today = clock.date_at(now, concert.time_zone)
    return max(start or venue_today, venue_today) <= concert.date <= last


def _scope(point: str | None, state: tuple[str, str] | None, radius: int) -> str:
    if state:
        return ":".join(state)
    return f"{point}:{radius}" if point else "anywhere"


async def _chunk(
    client: httpx.AsyncClient,
    redis: Redis,
    point: str | None,
    month: dt.date,
    earliest: dt.date,
    state: tuple[str, str] | None,
    radius: int,
    on_found: ticketmaster.OnPage | None,
) -> list[Concert]:
    key = f"pool:{_scope(point, state, radius)}:{month:%Y-%m}"
    if cached := await cache.read(redis, key, CachedConcerts):
        if on_found:
            on_found(cached.concerts)
        return cached.concerts
    last_day = calendar.monthrange(month.year, month.month)[1]
    concerts = await ticketmaster.find_concerts(
        client,
        redis,
        point,
        max(month, earliest),
        month.replace(day=last_day),
        state=state,
        radius=radius,
        on_page=on_found,
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
    on_found: ticketmaster.OnPage | None,
) -> list[Concert]:
    key = f"artist:{_scope(point, state, radius)}:{normalize(name)}"
    if cached := await cache.read(redis, key, CachedConcerts):
        concerts = cached.concerts
    else:
        concerts = await ticketmaster.find_artist_concerts(
            client, redis, name, point, state=state, radius=radius
        )
        await cache.write(redis, key, CachedConcerts(concerts=concerts), CACHE_TTL)
    if on_found:
        on_found(concerts)
    return concerts
