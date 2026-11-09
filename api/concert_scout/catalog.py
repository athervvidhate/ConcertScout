"""The national JamBase catalog in Redis, written by the sync and read by Searches.

Listings live in one hash per one-degree grid cell and calendar month, so a Search reads only
the few cells around its place, and a past month expires on its own.
"""

import datetime as dt
import logging
import math
from collections.abc import Iterable, Sequence
from typing import cast

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.typing import EncodableT, FieldT

from concert_scout import clock
from concert_scout.models import Concert, Place
from concert_scout.names import normalize
from concert_scout.sources.jambase import Listing

logger = logging.getLogger(__name__)

COUNTRY = "US"
DEFAULT_RADIUS_MILES = 50
MILES_PER_DEGREE = 69.0
# Where each event is stored, so a moved or removed event leaves its old cell.
WHERE = "jambase:where"
CELLS = "jambase:cells"
QUEUE = "jambase:mbid-queue"
MBIDS = "jambase:mbid"
# A name MusicBrainz could not settle is asked again after this long.
RETRY_UNKNOWN = dt.timedelta(days=60)


class Identity(BaseModel):
    mbid: str | None
    checked: dt.date


def _texts(values: Iterable[bytes | str]) -> list[str]:
    """Redis replies as text; redis-py types them loosely."""
    return [v.decode() if isinstance(v, bytes) else v for v in values]


def cell_of(lat: float, lon: float) -> str:
    return f"{math.floor(lat)}:{math.floor(lon)}"


def _month_key(cell: str, month: dt.date) -> str:
    return f"jambase:cell:{cell}:{month:%Y-%m}"


def _state_key(state: str) -> str:
    return f"jambase:state:{state}"


def _expiry(month: dt.date) -> dt.datetime:
    following = (month + dt.timedelta(days=31)).replace(day=1)
    # A few days past the month, so a venue further west can still be on its last day.
    return dt.datetime.combine(following + dt.timedelta(days=3), dt.time(), dt.UTC)


def cells_around(place: Place) -> list[str]:
    radius = place.radius_miles or DEFAULT_RADIUS_MILES
    lat_span = radius / MILES_PER_DEGREE
    lon_span = radius / (MILES_PER_DEGREE * max(math.cos(math.radians(place.lat)), 0.01))
    return [
        f"{lat}:{lon}"
        for lat in range(math.floor(place.lat - lat_span), math.floor(place.lat + lat_span) + 1)
        for lon in range(math.floor(place.lon - lon_span), math.floor(place.lon + lon_span) + 1)
    ]


def miles(lat: float, lon: float, other_lat: float, other_lon: float) -> float:
    a, b = math.radians(lat), math.radians(other_lat)
    value = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(other_lon - lon) / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(min(1, math.sqrt(value)))


async def store(
    redis: Redis, listings: Sequence[Listing], removed: Sequence[str], today: dt.date
) -> int:
    """Upsert one page. A listing without a date or coordinates cannot be found, so it leaves."""
    placed = [
        x for x in listings if x.concert.date and x.latitude is not None and x.longitude is not None
    ]
    gone = [*removed, *(x.concert.id for x in listings if x not in placed)]
    ids = [x.concert.id for x in placed] + gone
    if not ids:
        return 0
    olds = await redis.hmget(WHERE, ids)
    where = {i: _texts([o])[0] for i, o in zip(ids, olds, strict=True) if o is not None}
    pipe = redis.pipeline(transaction=False)
    for event_id in gone:
        if old := where.get(event_id):
            pipe.hdel(old, event_id)
            pipe.hdel(WHERE, event_id)
    # Upstash bills each command, so per-key and per-cell bookkeeping happens once a page.
    rows: dict[str, dict[FieldT, EncodableT]] = {}
    expiries: dict[str, dt.datetime] = {}
    states: dict[str, set[str]] = {}
    moved: dict[FieldT, EncodableT] = {}
    for listing in placed:
        concert = listing.concert
        assert concert.date and listing.latitude is not None and listing.longitude is not None
        cell = cell_of(listing.latitude, listing.longitude)
        month = concert.date.replace(day=1)
        key = _month_key(cell, month)
        if (old := where.get(concert.id)) and old != key:
            pipe.hdel(old, concert.id)
        if where.get(concert.id) != key:
            moved[concert.id] = key
        rows.setdefault(key, {})[concert.id] = listing.model_dump_json(exclude_none=True)
        expiries[key] = _expiry(month)
        states.setdefault(concert.region or "", set()).add(cell)
    for key, mapping in rows.items():
        pipe.hset(key, mapping=mapping)
        pipe.expireat(key, expiries[key])
    if moved:
        pipe.hset(WHERE, mapping=moved)
    if placed:
        pipe.sadd(CELLS, *{c for cells in states.values() for c in cells})
    for region, cells in states.items():
        if region:
            pipe.sadd(_state_key(region), *cells)
    await pipe.execute()
    await _enqueue(redis, placed, today)
    return len(placed)


async def _enqueue(redis: Redis, listings: Sequence[Listing], today: dt.date) -> None:
    """Queue Artists MusicBrainz has not settled yet, soonest Concert first."""
    soonest: dict[str, tuple[str, int]] = {}
    for listing in listings:
        assert listing.concert.date
        day = listing.concert.date.toordinal()
        for artist in listing.concert.artists:
            key = normalize(artist.name)
            if key and (key not in soonest or day < soonest[key][1]):
                soonest[key] = (artist.name, day)
    if not soonest:
        return
    known = await identities(redis, list(soonest), today)
    waiting = {name: day for key, (name, day) in soonest.items() if key not in known}
    if waiting:
        await redis.zadd(QUEUE, waiting, lt=True)  # pyright: ignore[reportArgumentType]


async def identities(redis: Redis, names: Sequence[str], today: dt.date) -> dict[str, Identity]:
    """Settled identities by normalized name. An old unknown counts as unsettled again."""
    keys = list(dict.fromkeys(normalize(n) for n in names))
    if not keys:
        return {}
    values = await redis.hmget(MBIDS, keys)
    found: dict[str, Identity] = {}
    for key, value in zip(keys, values, strict=True):
        if not value:
            continue
        try:
            identity = Identity.model_validate_json(value)
        except ValidationError:
            continue
        if identity.mbid or today - identity.checked < RETRY_UNKNOWN:
            found[key] = identity
    return found


async def settle(redis: Redis, results: dict[str, str | None], today: dt.date) -> None:
    """Record MusicBrainz answers by original name and take them off the queue."""
    if not results:
        return
    pipe = redis.pipeline(transaction=False)
    for name, mbid in results.items():
        pipe.hset(MBIDS, normalize(name), Identity(mbid=mbid, checked=today).model_dump_json())
    pipe.zrem(QUEUE, *results)
    await pipe.execute()


async def queued(redis: Redis, count: int) -> list[str]:
    # redis-py leaves zrange's reply untyped.
    reply = await redis.zrange(QUEUE, 0, count - 1)  # pyright: ignore[reportUnknownMemberType]
    names = cast(list[bytes], reply)
    return _texts(names)


async def _read(redis: Redis, keys: Iterable[str]) -> list[Listing]:
    pipe = redis.pipeline(transaction=False)
    for key in keys:
        pipe.hvals(key)
    listings: list[Listing] = []
    for values in await pipe.execute():
        for value in values:
            try:
                listings.append(Listing.model_validate_json(value))
            except ValidationError:
                continue
    return listings


def holds(concert_id: str) -> bool:
    """Whether an ID names a Catalog Concert. JamBase prefixes its own identifiers."""
    return concert_id.startswith("jambase:")


async def find(redis: Redis, concert_id: str) -> Concert | None:
    """One Catalog Concert by ID. The sync removes cancelled and past events, so they are None."""
    key = await redis.hget(WHERE, concert_id)
    value = await redis.hget(_texts([key])[0], concert_id) if key else None
    if not value:
        return None
    try:
        return Listing.model_validate_json(value).concert
    except ValidationError:
        return None


async def busiest_cells(redis: Redis, first: dt.date, last: dt.date, count: int) -> list[str]:
    """The cells holding the most Concerts in the window: where the music actually is."""
    members = await redis.smembers(CELLS)
    cells = sorted(_texts(members))
    spans = clock.months(first, last)
    pipe = redis.pipeline(transaction=False)
    for cell in cells:
        for month in spans:
            pipe.hlen(_month_key(cell, month))
    sizes: list[int] = await pipe.execute()
    totals = {
        cell: sum(sizes[i * len(spans) : (i + 1) * len(spans)]) for i, cell in enumerate(cells)
    }
    return sorted(totals, key=lambda c: -totals[c])[:count]


async def listings_in(
    redis: Redis, cells: Iterable[str], first: dt.date, last: dt.date
) -> list[Listing]:
    return await _read(redis, (_month_key(c, m) for c in cells for m in clock.months(first, last)))


async def prune(redis: Redis, today: dt.date) -> int:
    """Forget where past months' events were; their hashes have already expired."""
    current = f"{today:%Y-%m}"
    stale: list[str] = []
    entries = await redis.hgetall(WHERE)
    for event_id, key in zip(_texts(entries), _texts(entries.values()), strict=True):
        if key[-7:] < current:
            stale.append(event_id)
    if stale:
        await redis.hdel(WHERE, *stale)
    return len(stale)


async def concerts_near(
    redis: Redis, place: Place, start: dt.date | None, end: dt.date | None, now: dt.datetime
) -> list[Concert]:
    """Upcoming catalog Concerts for a place, with any MusicBrainz IDs the sync has settled."""
    if place.country_code and place.country_code != COUNTRY:
        return []
    today = now.date()
    first = max(start or today, today) - dt.timedelta(days=1)
    last = end or today + dt.timedelta(days=366)
    try:
        by_state = place.state_code and place.country_code == COUNTRY
        if by_state:
            members = await redis.smembers(_state_key(place.state_code or ""))
            cells = _texts(members)
        else:
            cells = cells_around(place)
        listings = await listings_in(redis, cells, first, last)
        radius = place.radius_miles or DEFAULT_RADIUS_MILES
        concerts: list[Concert] = []
        for listing in listings:
            concert = listing.concert
            local_today = clock.date_at(now, concert.time_zone)
            if not concert.date or concert.date < max(start or local_today, local_today):
                continue
            if end and concert.date > end:
                continue
            if by_state:
                if concert.region != place.state_code:
                    continue
            elif listing.latitude is None or listing.longitude is None:
                continue
            elif miles(place.lat, place.lon, listing.latitude, listing.longitude) > radius:
                continue
            concerts.append(concert)
        known = await identities(redis, [a.name for c in concerts for a in c.artists], today)
    except RedisError as exc:
        logger.warning("Catalog read failed: %s", type(exc).__name__)
        return []
    return [
        c.model_copy(
            update={
                "artists": [
                    a.model_copy(update={"mbid": known[k].mbid})
                    if (k := normalize(a.name)) in known and known[k].mbid
                    else a
                    for a in c.artists
                ]
            }
        )
        for c in concerts
    ]
