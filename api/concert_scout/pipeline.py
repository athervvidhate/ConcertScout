import asyncio
import datetime as dt
import hashlib
import logging
from collections.abc import AsyncIterator, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout import (
    assemble,
    cache,
    clock,
    interpreter,
    limits,
    matching,
    pool,
    ranker,
    similarity,
    telemetry,
)
from concert_scout.aliases import place_name
from concert_scout.interpreter import InterpreterError, interpret
from concert_scout.models import (
    ArtistProfile,
    Candidates,
    Concert,
    Elsewhere,
    Place,
    PoolTotal,
    Poster,
    Reading,
    Recommendation,
    SearchError,
    SeedArtist,
    Status,
)
from concert_scout.names import collab_names
from concert_scout.ranker import RankerError
from concert_scout.sources import (
    geocoder,
    jev,
    lastfm,
    listenbrainz,
    musicbrainz,
    spotify_catalog,
    ticketmaster,
)

logger = logging.getLogger(__name__)

ASK_FOR_A_SEARCH = "Tell us an Artist, a style or a place."
NEEDS_A_PLACE = "Add a place or an Artist, or press the location button."
# The home page shows the soonest of these, so a month of Concerts is plenty.
# With no place there is no pool, so this many similar Artists get looked up by name.
DIRECT_LOOKUPS = 15
# Imported Artists past this many join as names only, so a long list costs no extra API calls.
IMPORTED_SEEDS = 5


@dataclass(frozen=True)
class Services:
    ticketmaster: httpx.AsyncClient
    geocoder: httpx.AsyncClient
    musicbrainz: httpx.AsyncClient
    listenbrainz: httpx.AsyncClient
    lastfm: httpx.AsyncClient | None
    spotify_catalog: httpx.AsyncClient | None
    jev: httpx.AsyncClient
    redis: Redis
    model: Model
    turnstile: httpx.AsyncClient
    jambase: httpx.AsyncClient | None = None
    jambase_days: int = 90


async def find_artist_profile(name: str, services: Services) -> ArtistProfile:
    """Public Artist facts for the panel. This path never calls a model, and a dead source only
    leaves its part of the panel empty."""

    async def profile() -> ArtistProfile:
        if not services.lastfm:
            return ArtistProfile(name=name)
        try:
            return await lastfm.artist_profile(services.lastfm, services.redis, name)
        except lastfm.LastfmError as exc:
            logger.warning("Artist profile failed: %s", exc)
            return ArtistProfile(name=name)

    async def page() -> str | None:
        if not services.spotify_catalog:
            return None
        return await spotify_catalog.artist_page(services.spotify_catalog, services.redis, name)

    facts, spotify_url = await asyncio.gather(profile(), page())
    return facts.model_copy(update={"spotify_url": spotify_url})


async def find_artist_profiles(name: str, services: Services) -> list[ArtistProfile]:
    """A real duo keeps its own page. A tour billed as one name becomes each of its Artists."""
    whole = await find_artist_profile(name, services)
    parts = collab_names(name)
    if whole.spotify_url or whole.bio or not parts:
        return [whole]
    return list(await asyncio.gather(*(_billed_profile(part, services) for part in parts)))


async def _billed_profile(name: str, services: Services) -> ArtistProfile:
    """A billing can use a name the Artist is not filed under, so an alias gets a second look."""
    facts = await find_artist_profile(name, services)
    if facts.spotify_url:
        return facts
    try:
        filed = await musicbrainz.filed_name(services.musicbrainz, services.redis, name)
    except musicbrainz.MusicBrainzError as exc:
        logger.warning("MusicBrainz failed: %s", exc)
        return facts
    return await find_artist_profile(filed, services) if filed != name else facts


def _event(name: str, payload: BaseModel | None = None) -> ServerSentEvent:
    data = payload.model_dump(mode="json", exclude_none=True) if payload else {}
    return ServerSentEvent(event=name, data=data)


def _error(code: str, message: str) -> ServerSentEvent:
    return _event("error", SearchError(code=code, message=message))


async def _resolve_seed(name: str, services: Services) -> SeedArtist:
    try:
        return await musicbrainz.resolve(services.musicbrainz, services.redis, name)
    except musicbrainz.MusicBrainzError as exc:
        # The name alone can still join the pool, so a Search survives without MusicBrainz.
        logger.warning("MusicBrainz failed: %s", exc)
        return SeedArtist(name=name)


async def _find_taste(
    reading: Reading, names_only: Sequence[str], services: Services
) -> matching.Taste:
    seeds = await asyncio.gather(*(_resolve_seed(n, services) for n in reading.artists))
    neighbours = await similarity.find_neighbours(
        services.listenbrainz, services.lastfm, services.redis, seeds
    )
    extra = [SeedArtist(name=name) for name in names_only]
    return matching.Taste([*seeds, *extra], neighbours, reading.tags, reading.genres)


# A repeated Search within this window gets the same reading and grades, so the same Poster,
# and pays for no model call. It matches the Concert pool's own cache.
ANSWER_TTL = pool.CACHE_TTL


def _answer_key(kind: str, *parts: str) -> str:
    """Hashed, so a cache key never holds a visitor's Search text."""
    digest = hashlib.sha256("\x00".join(parts).encode()).hexdigest()
    return f"answer:{kind}:{digest}"


async def _interpreted(text: str, today: dt.date, services: Services) -> Reading:
    words = " ".join(text.split()).casefold()
    key = _answer_key("interpret", interpreter.INSTRUCTIONS, today.isoformat(), words)
    if cached := await cache.read(services.redis, key, Reading):
        return cached
    reading = await interpret(text, today, services.model)
    await cache.write(services.redis, key, reading, ANSWER_TTL)
    return reading


class Levels(BaseModel):
    levels: dict[str, int]


class Explained(BaseModel):
    reasons: list[str]


async def _graded(
    reading: Reading, rows: Mapping[str, ranker.Row], services: Services
) -> dict[str, int]:
    as_json = [f"{id_}={row.model_dump_json()}" for id_, row in rows.items()]
    taste = str(ranker.taste(reading))
    key = _answer_key("grade", jev.MODEL, jev.GUIDE, jev.QUESTION, *jev.LEVELS, taste, *as_json)
    if cached := await cache.read(services.redis, key, Levels):
        return cached.levels
    levels = await ranker.grade(services.jev, reading, rows)
    await cache.write(services.redis, key, Levels(levels=levels), ANSWER_TTL)
    return levels


async def _explained(
    reading: Reading, shown: Sequence[ranker.Row], services: Services
) -> list[str]:
    key = _answer_key("explain", ranker.REASONS, ranker.reasons_prompt(reading, shown))
    if cached := await cache.read(services.redis, key, Explained):
        return cached.reasons
    reasons = await ranker.explain(reading, shown, services.model)
    await cache.write(services.redis, key, Explained(reasons=reasons), ANSWER_TTL)
    return reasons


async def _recommend(
    reading: Reading,
    shortlist: Sequence[matching.Candidate],
    artist_tags: Mapping[str, Sequence[str]],
    services: Services,
) -> list[Recommendation]:
    rows = ranker.rows(shortlist, artist_tags)
    try:
        levels = await _graded(reading, rows, services)
    except RankerError as exc:
        logger.warning("Ranker failed: %s", exc)
        return assemble.from_matches(shortlist)
    if not levels:
        return assemble.from_matches(shortlist)
    poster = assemble.from_levels(levels, shortlist)
    candidates = {candidate.concert.id: candidate for candidate in shortlist}
    shown = [ranker.row(candidates[r.concert.id], artist_tags) for r in poster]
    # A Concert with no Lineup has no Artist to describe, so it keeps its neutral reason.
    named = [n for n, row in enumerate(shown) if row.artist]
    try:
        written = await _explained(reading, [shown[n] for n in named], services)
    except RankerError as exc:
        # The grades still stand. Each Concert keeps the neutral reason its match gave it.
        logger.warning("Reasons failed: %s", exc)
        return poster
    reasons = dict(zip(named, written, strict=True))
    return [
        r.model_copy(update={"reason": reasons[n]}) if reasons.get(n) else r
        for n, r in enumerate(poster)
    ]


async def _find_elsewhere(
    reading: Reading, place: Place, services: Services, now: dt.datetime
) -> Elsewhere | None:
    """The Poster has already answered this Search, so a failure here only means no extra list."""
    words = [*reading.artists, *reading.tags, *reading.descriptors]
    if not words:
        return None
    try:
        with telemetry.step("elsewhere"):
            concerts = await pool.find_elsewhere(
                services.ticketmaster,
                services.redis,
                words[0],
                reading.start,
                reading.end,
                now,
            )
    except (ticketmaster.TicketmasterError, limits.DailyLimitReached) as exc:
        logger.warning("Elsewhere lookup failed: %s", type(exc).__name__)
        return None
    city = place.name.split(",")[0].casefold()
    others = [concert for concert in concerts if (concert.city or "").casefold() != city]
    return Elsewhere(keyword=words[0], concerts=others) if others else None


async def _read(asked: str | Reading, today: dt.date, services: Services) -> Reading:
    """A corrected Reading skips the interpreter. Its place still goes to the geocoder."""
    if isinstance(asked, Reading):
        return asked.model_copy(update={"place": place_name(asked.place) if asked.place else None})
    with telemetry.step("interpret"):
        return await _interpreted(asked, today, services)


async def _steps(
    asked: str | Reading,
    imported: Sequence[str],
    near: Place | None,
    services: Services,
    now: dt.datetime,
) -> AsyncIterator[ServerSentEvent]:
    if isinstance(asked, str):
        yield _event("status", Status(step="interpret", message="Reading your Search"))
    reading = await _read(asked, now.date(), services)
    names_only: Sequence[str] = ()
    # A Taste typed into this Search says what the person wants now, so it beats an import.
    if not (reading.artists or reading.tags or reading.descriptors):
        seeds, names_only = imported[:IMPORTED_SEEDS], imported[IMPORTED_SEEDS:]
        reading = reading.model_copy(update={"artists": list(seeds)})
    yield _event("reading", reading)

    if not (reading.place or near or reading.artists):
        if reading.descriptors or reading.tags:
            # Similar Artists start from a seed, so a style alone has nothing to look up.
            yield _error("needs_place", NEEDS_A_PLACE)
        else:
            yield _error("needs_taste_or_place", ASK_FOR_A_SEARCH)
        return

    async def find_place() -> Place | None:
        if not reading.place:
            return near
        with telemetry.step("resolve_place"):
            place = await geocoder.geocode(services.geocoder, services.redis, reading.place)
            radius = reading.radius_miles
            return place.model_copy(update={"radius_miles": radius}) if place else None

    async def find_taste() -> matching.Taste:
        with telemetry.step("resolve_artists"):
            return await _find_taste(reading, names_only, services)

    async def find_pool(place: Place | None, lookups: Sequence[str]) -> list[Concert]:
        with telemetry.step("pool"):
            return await pool.find_concerts(
                services.ticketmaster,
                services.musicbrainz,
                services.redis,
                place,
                lookups,
                reading.start,
                reading.end,
                now,
                on_found=tag_fetch.add if wants_tags else None,
            )

    # Tags only score a Taste, so a place-only Search never asks for them.
    wants_tags = bool(reading.artists or names_only or reading.tags)
    tag_fetch = listenbrainz.TagFetch(services.listenbrainz, services.redis)
    # With a place, the pool needs nothing from the Taste, so the slowest steps overlap.
    tasks: list[asyncio.Task[Any]] = []

    def start[T](work: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        task = asyncio.create_task(work)
        tasks.append(task)
        return task

    try:
        place_lookup = start(find_place())
        taste_lookup = start(find_taste())
        if reading.place:
            message = f"Finding {reading.region or reading.place}"
            yield _event("status", Status(step="resolve", message=message))
        if reading.artists:
            message = f"Finding Artists like {', '.join(reading.artists)}"
            yield _event("status", Status(step="resolve", message=message))

        place = await place_lookup
        if reading.place and place is None:
            where = reading.region or reading.place
            message = f"We could not find {where}. Check the spelling."
            yield _error("place_not_found", message)
            return

        if place:
            near_place = "you" if place is near else reading.region or place.name
            message = f"Looking for Concerts near {near_place}"
            yield _event("status", Status(step="pool", message=message))
            concert_lookup = start(find_pool(place, reading.artists))
            taste = await taste_lookup
        else:
            taste = await taste_lookup
            closest = similarity.closest(taste.neighbours, DIRECT_LOOKUPS)
            names = ", ".join(reading.artists)
            message = f"Looking for Concerts by {names} and similar Artists"
            yield _event("status", Status(step="pool", message=message))
            concert_lookup = start(find_pool(None, [*reading.artists, *closest]))
        concerts = await concert_lookup
        yield _event("pool", PoolTotal(total=len(concerts)))

        artist_tags: dict[str, list[str]] = {}
        if taste:
            yield _event("status", Status(step="match", message="Matching Concerts to your Taste"))
            with telemetry.step("match"):
                # Most batches started while the pool was still arriving.
                tag_fetch.add(concerts)
                artist_tags = await tag_fetch.tags()
                shortlist = matching.shortlist(
                    matching.score_concerts(concerts, taste, artist_tags)
                )
        else:
            shortlist = matching.notable(concerts)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await tag_fetch.close()
    names = matching.candidate_names(shortlist)
    yield _event("candidates", Candidates(names=names, total=len(shortlist)))

    if not taste:
        # Product rule for place-only Searches: notable means Ticketmaster-listed; order by date.
        recommendations = assemble.from_notable(shortlist)
    else:
        yield _event("status", Status(step="rank", message="Choosing the closest Concerts"))
        with telemetry.step("rank"):
            recommendations = await _recommend(reading, shortlist, artist_tags, services)
    yield _event("poster", Poster(recommendations=recommendations))
    if place and taste and not recommendations:
        elsewhere = await _find_elsewhere(reading, place, services, now)
        if elsewhere:
            yield _event("elsewhere", elsewhere)


async def run_search(
    asked: str | Reading,
    imported: Sequence[str],
    near: Place | None,
    time_zone: str,
    services: Services,
) -> AsyncIterator[ServerSentEvent]:
    with telemetry.search() as usage:
        try:
            now = clock.now_in(time_zone)
            async for event in stream_search(asked, imported, near, services, now):
                yield event
        finally:
            # A visitor who leaves early has still cost money, so a cancel must not skip this.
            if not usage.complete:
                logger.warning("Search cost is incomplete")
            with anyio.CancelScope(shield=True):
                await limits.record_spend(services.redis, usage.cost)


async def stream_search(
    asked: str | Reading,
    imported: Sequence[str],
    near: Place | None,
    services: Services,
    now: dt.datetime,
) -> AsyncIterator[ServerSentEvent]:
    """`asked` is the Search's words, or a Reading the person corrected."""
    try:
        async for event in _steps(asked, imported, near, services, now):
            yield event
    except InterpreterError as exc:
        logger.warning("Interpreter failed: %s", exc)
        message = "We could not read that Search. Try again in a minute."
        yield _error("interpreter_unavailable", message)
    except geocoder.GeocoderError as exc:
        logger.warning("Geocoder failed: %s", exc)
        message = "We could not look up that place. Try again in a minute."
        yield _error("geocoder_unavailable", message)
    except limits.DailyLimitReached as exc:
        logger.warning("Ticketmaster daily limit reached")
        message = "We have used today's Ticketmaster allowance. Try again tomorrow."
        yield _event(
            "error",
            SearchError(code="ticketmaster_limit", message=message, retry_after=exc.retry_after),
        )
    except ticketmaster.TicketmasterError as exc:
        logger.warning("Ticketmaster failed: %s", exc)
        message = "Ticketmaster is not responding. Try again in a minute."
        yield _error("ticketmaster_unavailable", message)
    yield _event("done")
