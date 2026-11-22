"""Underground venue calendar and curated Eventbrite promoter store in Redis.

Mirrors `catalog.py`'s cell-by-month hashes under `underground:*`, synced by `/sync-underground`
so Searches never scrape venue websites or call Eventbrite live.
"""

import asyncio
import datetime as dt
import logging
import secrets
import time
from collections.abc import Iterable, Sequence

import httpx
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redis.typing import EncodableT, FieldT

from concert_scout import catalog, clock
from concert_scout.models import Artist, Concert, Place
from concert_scout.names import normalize
from concert_scout.sources import eventbrite, jsonld_venues, musicbrainz
from concert_scout.underground_registry import VENUES, UndergroundVenue

logger = logging.getLogger(__name__)

COUNTRY = "US"
WHERE = "underground:where"
CELLS = "underground:cells"
LOCK = "underground:sync-lock"
LOCK_TTL_SECONDS = 300
DEFAULT_CONCURRENCY = 3
DEFAULT_DELAY_SECONDS = 0.25


class StoredListing(BaseModel):
    concert: Concert
    latitude: float
    longitude: float
    source_key: str


class Step(BaseModel):
    name: str
    requests: int = 0
    stored: int = 0
    removed: int = 0
    confirmed: int = 0
    seconds: float = 0.0
    error: str | None = None


def _texts(values: Iterable[bytes | str]) -> list[str]:
    return [v.decode() if isinstance(v, bytes) else v for v in values]


def _month_key(cell: str, month: dt.date) -> str:
    return f"underground:cell:{cell}:{month:%Y-%m}"


def _state_key(state: str) -> str:
    return f"underground:state:{state}"


def _source_key(name: str) -> str:
    return f"underground:source:{name}"


def _expiry(month: dt.date) -> dt.datetime:
    following = (month + dt.timedelta(days=31)).replace(day=1)
    return dt.datetime.combine(following + dt.timedelta(days=3), dt.time(), dt.UTC)


def parse_organizer_ids(raw: str) -> list[str]:
    """Parse comma-separated Eventbrite organizer IDs cleanly."""
    seen: set[str] = set()
    ids: list[str] = []
    for part in raw.split(","):
        cleaned = part.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ids.append(cleaned)
    return ids


def holds(concert_id: str) -> bool:
    """Whether an ID belongs to the local underground store."""
    return concert_id.startswith(("venue:", "eventbrite:"))


async def find(redis: Redis, concert_id: str) -> Concert | None:
    """One stored underground Concert by ID, or None when gone or expired."""
    key = await redis.hget(WHERE, concert_id)
    value = await redis.hget(_texts([key])[0], concert_id) if key else None
    if not value:
        return None
    try:
        return StoredListing.model_validate_json(value).concert
    except ValidationError:
        return None


async def _read(redis: Redis, keys: Iterable[str]) -> list[StoredListing]:
    key_list = list(keys)
    if not key_list:
        return []
    pipe = redis.pipeline(transaction=False)
    for key in key_list:
        pipe.hvals(key)
    listings: list[StoredListing] = []
    for values in await pipe.execute():
        for value in values:
            try:
                listings.append(StoredListing.model_validate_json(value))
            except ValidationError:
                continue
    return listings


async def store_source(
    redis: Redis, source_key: str, listings: Sequence[StoredListing]
) -> tuple[int, int]:
    """Replace one venue or organizer's stored listings, removing any that disappeared."""
    placed = [x for x in listings if x.concert.date is not None]
    current_ids = {x.concert.id for x in placed}
    source_set = _source_key(source_key)
    previous_raw = await redis.smembers(source_set)
    previous_ids = set(_texts(previous_raw))
    removed_ids = sorted(previous_ids - current_ids)

    all_ids = [x.concert.id for x in placed] + removed_ids
    if not all_ids:
        return 0, 0
    olds = await redis.hmget(WHERE, all_ids)
    where = {i: _texts([o])[0] for i, o in zip(all_ids, olds, strict=True) if o is not None}

    pipe = redis.pipeline(transaction=False)
    for event_id in removed_ids:
        if old := where.get(event_id):
            pipe.hdel(old, event_id)
        pipe.hdel(WHERE, event_id)
    if removed_ids:
        pipe.srem(source_set, *removed_ids)

    rows: dict[str, dict[FieldT, EncodableT]] = {}
    expiries: dict[str, dt.datetime] = {}
    states: dict[str, set[str]] = {}
    moved: dict[FieldT, EncodableT] = {}

    for listing in placed:
        concert = listing.concert
        assert concert.date is not None
        cell = catalog.cell_of(listing.latitude, listing.longitude)
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
        pipe.sadd(source_set, *current_ids)
    for region, cells in states.items():
        if region:
            pipe.sadd(_state_key(region), *cells)
    await pipe.execute()
    return len(placed), len(removed_ids)


async def prune(redis: Redis, today: dt.date) -> int:
    """Drop past-month index pointers from `underground:where`; their hashes expire on their own."""
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
    redis: Redis,
    place: Place,
    start: dt.date | None,
    end: dt.date | None,
    now: dt.datetime,
) -> list[Concert]:
    """Upcoming underground Concerts near `place` from local Redis, filtered by radius and dates."""
    if place.country_code and place.country_code != COUNTRY:
        return []
    today = now.date()
    first = max(start or today, today) - dt.timedelta(days=1)
    last = end or today + dt.timedelta(days=366)
    try:
        by_state = bool(place.state_code and place.country_code == COUNTRY)
        if by_state:
            members = await redis.smembers(_state_key(place.state_code or ""))
            cells = _texts(members)
        else:
            cells = catalog.cells_around(place)
        spans = clock.months(first, last)
        listings = await _read(redis, (_month_key(c, m) for c in cells for m in spans))
    except RedisError as exc:
        logger.warning("Underground store read failed: %s", type(exc).__name__)
        return []

    radius = place.radius_miles or catalog.DEFAULT_RADIUS_MILES
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
        elif catalog.miles(place.lat, place.lon, listing.latitude, listing.longitude) > radius:
            continue
        concerts.append(concert)
    return concerts


async def harvest_venue_calendars(
    venue_client: httpx.AsyncClient,
    mb_client: httpx.AsyncClient,
    redis: Redis,
    now: dt.datetime,
    venues: Sequence[UndergroundVenue] | None = None,
    *,
    max_concurrency: int = DEFAULT_CONCURRENCY,
    delay_seconds: float | None = None,
) -> Step:
    """Fetch curated venue calendars, confirm performers via MusicBrainz, and store in Redis."""
    step = Step(name="venue_calendars")
    began = time.perf_counter()
    targets = VENUES if venues is None else venues
    pause = DEFAULT_DELAY_SECONDS if delay_seconds is None else delay_seconds
    if not targets:
        return step

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    fetched: list[tuple[UndergroundVenue, list[jsonld_venues.ExtractedEvent]]] = []
    errors: list[str] = []

    async def load(venue: UndergroundVenue) -> None:
        async with semaphore:
            if pause > 0:
                await asyncio.sleep(pause)
            step.requests += 1
            try:
                events = await jsonld_venues.fetch_calendar(venue_client, venue, now)
            except jsonld_venues.JsonLdError as exc:
                errors.append(f"{venue.slug}: {exc}")
                return
            fetched.append((venue, events))

    await asyncio.gather(*(load(venue) for venue in targets))

    performer_names = list(
        dict.fromkeys(
            name
            for _, events in fetched
            for event in events
            for name in event.performer_names
            if name
        )
    )
    confirmed: dict[str, str] = {}
    if performer_names:
        try:
            confirmed = await musicbrainz.confirm(mb_client, redis, performer_names)
        except musicbrainz.MusicBrainzError as exc:
            logger.warning("Underground MusicBrainz confirm failed: %s", exc)
            errors.append(f"musicbrainz: {exc}")

    confirmed_artists: set[str] = set()
    for venue, events in fetched:
        source_key = f"venue:{venue.slug}"
        to_store: list[StoredListing] = []
        for event in events:
            seen_keys: set[str] = set()
            artists: list[Artist] = []
            for raw_name in event.performer_names:
                key = normalize(raw_name)
                if key and key in confirmed and key not in seen_keys:
                    seen_keys.add(key)
                    confirmed_artists.add(key)
                    artists.append(Artist(name=raw_name, mbid=confirmed[key]))
            concert = event.concert.model_copy(
                update={"source": "venue_calendar", "artists": artists}
            )
            to_store.append(
                StoredListing(
                    concert=concert,
                    latitude=event.latitude,
                    longitude=event.longitude,
                    source_key=source_key,
                )
            )
        stored_count, removed_count = await store_source(redis, source_key, to_store)
        step.stored += stored_count
        step.removed += removed_count

    step.confirmed = len(confirmed_artists)
    if errors:
        step.error = "; ".join(errors[:5])
    step.seconds = round(time.perf_counter() - began, 3)
    return step


async def harvest_eventbrite_organizers(
    eb_client: httpx.AsyncClient,
    redis: Redis,
    organizer_ids: Sequence[str],
    now: dt.datetime,
    *,
    delay_seconds: float | None = None,
) -> Step:
    """Fetch curated Eventbrite promoters, preserving `artists=[]` and `sold_out` (ADR 0002)."""
    step = Step(name="eventbrite_organizers")
    began = time.perf_counter()
    pause = DEFAULT_DELAY_SECONDS if delay_seconds is None else delay_seconds
    errors: list[str] = []

    for index, organizer_id in enumerate(organizer_ids):
        if index > 0 and pause > 0:
            await asyncio.sleep(pause)
        step.requests += 1
        try:
            listings = await eventbrite.organizer_listings(eb_client, organizer_id, now)
        except eventbrite.EventbriteError as exc:
            errors.append(f"{organizer_id}: {exc}")
            continue

        source_key = f"eventbrite:{organizer_id}"
        to_store: list[StoredListing] = []
        for listing in listings:
            if (
                listing.concert.date is None
                or listing.latitude is None
                or listing.longitude is None
            ):
                continue
            # ADR 0002: Eventbrite titles never fabricate Artist Lineups.
            concert = listing.concert.model_copy(
                update={
                    "source": "eventbrite",
                    "artists": [],
                    "sold_out": listing.sold_out,
                }
            )
            to_store.append(
                StoredListing(
                    concert=concert,
                    latitude=float(listing.latitude),
                    longitude=float(listing.longitude),
                    source_key=source_key,
                )
            )
        stored_count, removed_count = await store_source(redis, source_key, to_store)
        step.stored += stored_count
        step.removed += removed_count

    if errors:
        step.error = "; ".join(errors[:5])
    step.seconds = round(time.perf_counter() - began, 3)
    return step


async def run(
    venue_client: httpx.AsyncClient,
    mb_client: httpx.AsyncClient,
    redis: Redis,
    now: dt.datetime,
    *,
    eventbrite_client: httpx.AsyncClient | None = None,
    organizer_ids: Sequence[str] = (),
    venues: Sequence[UndergroundVenue] | None = None,
    max_concurrency: int = DEFAULT_CONCURRENCY,
    delay_seconds: float | None = None,
) -> list[Step]:
    """One locked underground sync: venue calendars, configured Eventbrite organizers, prune."""
    token = secrets.token_hex(16)
    try:
        if not await redis.set(LOCK, token, nx=True, ex=LOCK_TTL_SECONDS):
            return [Step(name="underground", error="sync already running")]
    except RedisError:
        return [Step(name="underground", error="cache unavailable")]

    steps: list[Step] = []
    try:
        steps.append(
            await harvest_venue_calendars(
                venue_client,
                mb_client,
                redis,
                now,
                venues=venues,
                max_concurrency=max_concurrency,
                delay_seconds=delay_seconds,
            )
        )
        if eventbrite_client and organizer_ids:
            steps.append(
                await harvest_eventbrite_organizers(
                    eventbrite_client,
                    redis,
                    organizer_ids,
                    now,
                    delay_seconds=delay_seconds,
                )
            )
        steps.append(Step(name="prune", removed=await prune(redis, now.date())))
    except RedisError as exc:
        steps.append(Step(name="underground", error=type(exc).__name__))
    finally:
        await _release(redis, token)
    for step in steps:
        logger.info("Underground sync %s", step.model_dump_json(exclude_defaults=True))
    return steps


async def _release(redis: Redis, token: str) -> None:
    try:
        async with redis.pipeline() as pipe:
            await pipe.watch(LOCK)
            if await pipe.get(LOCK) == token.encode():
                pipe.multi()
                pipe.delete(LOCK)
                await pipe.execute()
    except RedisError:
        pass
