"""Daily background sync of the national JamBase catalog, then MusicBrainz IDs for its Artists.

The first runs download each state once, resuming where the last run stopped. After that a run
asks only for events changed since the previous run, plus the day newly inside the window. A
Search never calls JamBase, so visitors cannot spend its quota.
"""

import asyncio
import datetime as dt
import logging
import secrets
import time

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import cache, catalog, warm
from concert_scout.names import normalize
from concert_scout.pipeline import Services
from concert_scout.sources import geocoder, jambase, musicbrainz

logger = logging.getLogger(__name__)

STATE = "jambase:sync"
LOCK = "jambase:sync-lock"
# The whole route must end inside the 300-second function limit.
RUN_SECONDS = 240
# MusicBrainz always gets this much of a run, even while the first download is underway.
IDENTIFY_SECONDS = 60
# Stay inside the Developer plan's 1,000 included calls, so overage can never bill.
MONTHLY_LIMIT = 900
MIN_REMAINING = 25
# JamBase's Developer rate is 3,600 an hour.
REQUEST_GAP = 1.0
# Changes a little earlier than the last run's start are asked for again, as JamBase advises.
OVERLAP = dt.timedelta(minutes=5)
# MusicBrainz lookups favour Concerts in the next month in busy and busiest cells.
SOON = dt.timedelta(days=30)
BUSIEST_CELLS = 20
LOOKUP_SECONDS = 3.0
STATES = tuple(
    f"US-{code}"
    for code in (
        "CA NY TX FL IL WA CO TN GA MA PA NC OR AZ MI OH MN NJ VA MD WI MO LA NV IN SC KY UT "
        "OK AL CT IA KS NM NE ID AR MS HI ME NH RI MT DE VT WV SD ND AK WY DC"
    ).split()
)


class SyncState(BaseModel):
    # Changes from here on are still to be applied. Unset until the first run starts.
    checkpoint: dt.datetime | None = None
    # The last event date the catalog holds for every seeded state.
    horizon: dt.date | None = None
    seeded: list[str] = []


class Step(BaseModel):
    name: str
    requests: int = 0
    stored: int = 0
    removed: int = 0
    seconds: float = 0
    error: str | None = None


class _Calls:
    """Paces JamBase requests and stops at the run's allowance or time."""

    def __init__(self, client: httpx.AsyncClient, allowance: int, deadline: float):
        self.client = client
        self.allowance = allowance
        self.deadline = deadline
        self.used = 0
        self._last = 0.0

    def affords(self, pages: int) -> bool:
        seconds = pages * (REQUEST_GAP + 0.5)
        return self.used + pages <= self.allowance and time.monotonic() + seconds < self.deadline

    async def page(self, params: dict[str, str | int], page: int) -> jambase.Page:
        if not self.affords(1):
            raise jambase.JamBaseError("run allowance reached")
        await asyncio.sleep(max(0.0, self._last + REQUEST_GAP - time.monotonic()))
        self._last = time.monotonic()
        self.used += 1
        return await jambase.events(self.client, params, page)


async def _walk(
    calls: _Calls, redis: Redis, step: Step, params: dict[str, str | int], today: dt.date
) -> None:
    """Every page of one query, or an error before any page beyond the first is spent."""
    began = time.perf_counter()
    page = 1
    while True:
        result = await calls.page(params, page)
        step.requests += 1
        step.stored += await catalog.store(redis, result.listings, result.removed, today)
        step.removed += len(result.removed)
        if page >= result.pages:
            break
        if page == 1 and not calls.affords(result.pages - 1):
            raise jambase.JamBaseError(f"{result.pages} pages exceed this run")
        page += 1
    step.seconds = round(time.perf_counter() - began, 3)


def _stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _catalog(
    services: Services, client: httpx.AsyncClient, now: dt.datetime, deadline: float
) -> list[Step]:
    redis = services.redis
    today = now.date()
    horizon = today + dt.timedelta(days=services.jambase_days)
    quota = await jambase.quota(client)
    allowance = min(quota.remaining, MONTHLY_LIMIT - quota.used) - MIN_REMAINING
    if allowance <= 0:
        return [Step(name="quota", error="included quota reserved; no overage")]
    calls = _Calls(client, allowance, deadline)
    state = await cache.read(redis, STATE, SyncState) or SyncState()
    steps: list[Step] = []

    if state.checkpoint and state.horizon:
        changes = Step(name="changes")
        steps.append(changes)
        try:
            await _walk(
                calls,
                redis,
                changes,
                {
                    "geoCountryIso2": catalog.COUNTRY,
                    "dateModifiedFrom": _stamp(state.checkpoint),
                    "eventDateFrom": str(today - dt.timedelta(days=1)),
                    "eventDateTo": str(horizon + dt.timedelta(days=1)),
                },
                today,
            )
            if horizon > state.horizon:
                ahead = Step(name="newly in window")
                steps.append(ahead)
                await _walk(
                    calls,
                    redis,
                    ahead,
                    {
                        "geoCountryIso2": catalog.COUNTRY,
                        "eventDateFrom": str(state.horizon),
                        "eventDateTo": str(horizon + dt.timedelta(days=1)),
                    },
                    today,
                )
            state.checkpoint, state.horizon = now - OVERLAP, horizon
            await _save(redis, state)
        except jambase.JamBaseError as exc:
            steps[-1].error = str(exc)
            return steps
    else:
        state = SyncState(checkpoint=now - OVERLAP, horizon=horizon)
        await _save(redis, state)

    for region in [s for s in STATES if s not in state.seeded]:
        seed = Step(name=f"download {region}")
        steps.append(seed)
        try:
            await _walk(
                calls,
                redis,
                seed,
                {
                    "geoCountryIso2": catalog.COUNTRY,
                    "geoStateIso": region,
                    "eventDateFrom": str(today - dt.timedelta(days=1)),
                    "eventDateTo": str((state.horizon or horizon) + dt.timedelta(days=1)),
                },
                today,
            )
        except jambase.JamBaseError as exc:
            seed.error = str(exc)
            break
        state.seeded.append(region)
        await _save(redis, state)
    return steps


async def _save(redis: Redis, state: SyncState) -> None:
    await redis.set(STATE, state.model_dump_json())


async def _priority_names(services: Services, today: dt.date) -> list[str]:
    """Unsettled Artists playing soon in busy cities or the cells with the most Concerts.

    The two lists usually agree but not always, so both count.
    """
    cells: set[str] = set()
    for name in warm.PLACES:
        try:
            place = await geocoder.geocode(services.geocoder, services.redis, name)
        except geocoder.GeocoderError:
            continue
        if place and place.country_code in (None, catalog.COUNTRY):
            cells.update(catalog.cells_around(place))
    last = today + SOON
    cells.update(await catalog.busiest_cells(services.redis, today, last, BUSIEST_CELLS))
    listings = await catalog.listings_in(services.redis, cells, today, last)
    listings.sort(key=lambda x: x.concert.date or dt.date.max)
    names = list({normalize(a.name): a.name for x in listings for a in x.concert.artists}.values())
    known = await catalog.identities(services.redis, names, today)
    return [n for n in names if normalize(n) not in known]


async def _identify(services: Services, today: dt.date, deadline: float) -> Step:
    step = Step(name="MusicBrainz IDs")
    began = time.perf_counter()
    redis = services.redis
    names = await _priority_names(services, today)
    queue = await catalog.queued(redis, 2000)
    known = await catalog.identities(redis, queue, today)
    # Queued names another spelling already settled leave without a call.
    if done := [n for n in queue if normalize(n) in known]:
        await redis.zrem(catalog.QUEUE, *done)
    seen = {normalize(n) for n in names}
    names += [n for n in queue if normalize(n) not in known and normalize(n) not in seen]
    for start in range(0, len(names), musicbrainz.BATCH_SIZE):
        if time.monotonic() + LOOKUP_SECONDS > deadline:
            break
        batch = names[start : start + musicbrainz.BATCH_SIZE]
        try:
            settled = await musicbrainz.identify(services.musicbrainz, redis, batch)
        except musicbrainz.MusicBrainzError as exc:
            step.error = str(exc)
            break
        await catalog.settle(redis, settled, today)
        step.requests += 1
        step.stored += sum(1 for v in settled.values() if v)
        step.removed += sum(1 for v in settled.values() if v is None)
    step.seconds = round(time.perf_counter() - began, 3)
    return step


async def run(services: Services, now: dt.datetime) -> list[Step]:
    """One locked run: catalog first, then MusicBrainz with the time left."""
    deadline = time.monotonic() + RUN_SECONDS
    token = secrets.token_hex(16)
    try:
        if not await services.redis.set(LOCK, token, nx=True, ex=RUN_SECONDS + 60):
            return [Step(name="sync", error="sync already running")]
    except RedisError:
        return [Step(name="sync", error="cache unavailable")]
    steps: list[Step] = []
    try:
        if services.jambase:
            try:
                steps += await _catalog(
                    services, services.jambase, now, deadline - IDENTIFY_SECONDS
                )
            except jambase.JamBaseError as exc:
                steps.append(Step(name="catalog", error=str(exc)))
            steps.append(
                Step(name="prune", removed=await catalog.prune(services.redis, now.date()))
            )
        steps.append(await _identify(services, now.date(), deadline))
    except RedisError as exc:
        steps.append(Step(name="sync", error=type(exc).__name__))
    finally:
        await _release(services.redis, token)
    for step in steps:
        logger.info("Sync %s", step.model_dump_json(exclude_defaults=True))
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
