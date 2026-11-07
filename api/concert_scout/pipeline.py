import asyncio
import datetime as dt
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

from concert_scout import assemble, limits, matching, pool, similarity, telemetry
from concert_scout.interpreter import Interpretation, InterpreterError, interpret
from concert_scout.models import (
    ArtistProfile,
    Candidates,
    Concert,
    Elsewhere,
    Interpreted,
    Place,
    PoolTotal,
    Poster,
    Recommendation,
    SearchError,
    SeedArtist,
    Status,
)
from concert_scout.names import collab_names
from concert_scout.ranker import RankerError, rank
from concert_scout.sources import (
    geocoder,
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
    redis: Redis
    model: Model
    turnstile: httpx.AsyncClient


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
    interpretation: Interpretation, names_only: Sequence[str], services: Services
) -> matching.Taste:
    seeds = await asyncio.gather(*(_resolve_seed(n, services) for n in interpretation.artists))
    neighbours = await similarity.find_neighbours(
        services.listenbrainz, services.lastfm, services.redis, seeds
    )
    extra = [SeedArtist(name=name) for name in names_only]
    return matching.Taste([*seeds, *extra], neighbours, interpretation.tags, interpretation.genres)


async def _recommend(
    interpretation: Interpretation,
    shortlist: Sequence[matching.Candidate],
    artist_tags: Mapping[str, Sequence[str]],
    services: Services,
) -> list[Recommendation]:
    try:
        picks = await rank(interpretation, shortlist, artist_tags, services.model)
    except RankerError as exc:
        logger.warning("Ranker failed: %s", exc)
        return assemble.from_matches(shortlist)
    recommendations = assemble.from_picks(picks, shortlist)
    # Picks that all name unknown IDs are a garbled answer, not a verdict that nothing fits.
    return assemble.from_matches(shortlist) if picks and not recommendations else recommendations


async def _find_elsewhere(
    interpretation: Interpretation, place: Place, services: Services, today: dt.date
) -> Elsewhere | None:
    """The Poster has already answered this Search, so a failure here only means no extra list."""
    words = [*interpretation.artists, *interpretation.tags, *interpretation.descriptors]
    if not words:
        return None
    try:
        with telemetry.step("elsewhere"):
            concerts = await pool.find_elsewhere(
                services.ticketmaster,
                services.redis,
                words[0],
                interpretation.start,
                interpretation.end,
                today,
            )
    except (ticketmaster.TicketmasterError, limits.DailyLimitReached) as exc:
        logger.warning("Elsewhere lookup failed: %s", type(exc).__name__)
        return None
    city = place.name.split(",")[0].casefold()
    others = [concert for concert in concerts if (concert.city or "").casefold() != city]
    return Elsewhere(keyword=words[0], concerts=others) if others else None


async def _steps(
    text: str, imported: Sequence[str], near: Place | None, services: Services, today: dt.date
) -> AsyncIterator[ServerSentEvent]:
    yield _event("status", Status(step="interpret", message="Reading your Search"))
    with telemetry.step("interpret"):
        interpretation = await interpret(text, today, services.model)
    names_only: Sequence[str] = ()
    # A Taste typed into this Search says what the person wants now, so it beats an import.
    if not (interpretation.artists or interpretation.tags or interpretation.descriptors):
        seeds, names_only = imported[:IMPORTED_SEEDS], imported[IMPORTED_SEEDS:]
        interpretation = interpretation.model_copy(update={"artists": list(seeds)})
    yield _event(
        "interpreted",
        Interpreted(
            place=interpretation.place,
            region=interpretation.region,
            radius_miles=interpretation.radius_miles,
            start=interpretation.start,
            end=interpretation.end,
            artists=interpretation.artists,
            genres=interpretation.genres,
        ),
    )

    if not (interpretation.place or near or interpretation.artists):
        if interpretation.descriptors or interpretation.tags:
            # Similar Artists start from a seed, so a style alone has nothing to look up.
            yield _error("needs_place", NEEDS_A_PLACE)
        else:
            yield _error("needs_taste_or_place", ASK_FOR_A_SEARCH)
        return

    async def find_place() -> Place | None:
        if not interpretation.place:
            return near
        with telemetry.step("resolve_place"):
            place = await geocoder.geocode(services.geocoder, services.redis, interpretation.place)
            radius = interpretation.radius_miles
            return place.model_copy(update={"radius_miles": radius}) if place else None

    async def find_taste() -> matching.Taste:
        with telemetry.step("resolve_artists"):
            return await _find_taste(interpretation, names_only, services)

    async def find_pool(place: Place | None, lookups: Sequence[str]) -> list[Concert]:
        with telemetry.step("pool"):
            return await pool.find_concerts(
                services.ticketmaster,
                services.redis,
                place,
                lookups,
                interpretation.start,
                interpretation.end,
                today,
            )

    # With a place, the pool needs nothing from the Taste, so the slowest steps overlap.
    tasks: list[asyncio.Task[Any]] = []

    def start[T](work: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        task = asyncio.create_task(work)
        tasks.append(task)
        return task

    try:
        place_lookup = start(find_place())
        taste_lookup = start(find_taste())
        if interpretation.place:
            message = f"Finding {interpretation.region or interpretation.place}"
            yield _event("status", Status(step="resolve", message=message))
        if interpretation.artists:
            message = f"Finding Artists like {', '.join(interpretation.artists)}"
            yield _event("status", Status(step="resolve", message=message))

        place = await place_lookup
        if interpretation.place and place is None:
            where = interpretation.region or interpretation.place
            message = f"We could not find {where}. Check the spelling."
            yield _error("place_not_found", message)
            return

        if place:
            near_place = "you" if place is near else interpretation.region or place.name
            message = f"Looking for Concerts near {near_place}"
            yield _event("status", Status(step="pool", message=message))
            concert_lookup = start(find_pool(place, interpretation.artists))
            taste = await taste_lookup
        else:
            taste = await taste_lookup
            closest = similarity.closest(taste.neighbours, DIRECT_LOOKUPS)
            names = ", ".join(interpretation.artists)
            message = f"Looking for Concerts by {names} and similar Artists"
            yield _event("status", Status(step="pool", message=message))
            concert_lookup = start(find_pool(None, [*interpretation.artists, *closest]))
        concerts = await concert_lookup
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    yield _event("pool", PoolTotal(total=len(concerts)))

    artist_tags: dict[str, list[str]] = {}
    if taste:
        yield _event("status", Status(step="match", message="Matching Concerts to your Taste"))
        mbids = {a.mbid for concert in concerts for a in concert.artists if a.mbid}
        with telemetry.step("match"):
            artist_tags = await listenbrainz.artist_tags(
                services.listenbrainz, services.redis, sorted(mbids)
            )
            shortlist = matching.shortlist(matching.score_concerts(concerts, taste, artist_tags))
    else:
        shortlist = matching.notable(concerts)
    names = matching.candidate_names(shortlist)
    yield _event("candidates", Candidates(names=names, total=len(shortlist)))

    if not taste:
        # Product rule for place-only Searches: notable means Ticketmaster-listed; order by date.
        recommendations = assemble.from_notable(shortlist)
    else:
        yield _event("status", Status(step="rank", message="Choosing the closest Concerts"))
        with telemetry.step("rank"):
            recommendations = await _recommend(interpretation, shortlist, artist_tags, services)
    yield _event("poster", Poster(recommendations=recommendations))
    if place and taste and not recommendations:
        elsewhere = await _find_elsewhere(interpretation, place, services, today)
        if elsewhere:
            yield _event("elsewhere", elsewhere)


async def run_search(
    text: str, imported: Sequence[str], near: Place | None, services: Services
) -> AsyncIterator[ServerSentEvent]:
    with telemetry.search() as usage:
        try:
            async for event in stream_search(text, imported, near, services, dt.date.today()):
                yield event
        finally:
            # A visitor who leaves early has still cost money, so a cancel must not skip this.
            if not usage.complete:
                logger.warning("Search cost is incomplete")
            with anyio.CancelScope(shield=True):
                await limits.record_spend(services.redis, usage.cost)


async def stream_search(
    text: str, imported: Sequence[str], near: Place | None, services: Services, today: dt.date
) -> AsyncIterator[ServerSentEvent]:
    try:
        async for event in _steps(text, imported, near, services, today):
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
