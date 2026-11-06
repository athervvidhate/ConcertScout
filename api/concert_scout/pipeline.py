import asyncio
import datetime as dt
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

import anyio
import httpx
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout import assemble, limits, matching, pool, similarity, telemetry
from concert_scout.interpreter import Interpretation, InterpreterError, interpret
from concert_scout.models import (
    Candidates,
    Concert,
    Interpreted,
    Place,
    PoolTotal,
    Poster,
    Recommendation,
    SearchError,
    SeedArtist,
    Status,
)
from concert_scout.ranker import RankerError, rank
from concert_scout.sources import geocoder, listenbrainz, musicbrainz, ticketmaster

logger = logging.getLogger(__name__)

ASK_FOR_A_SEARCH = "Tell us an Artist, a style or a place."
# The home page shows the soonest of these, so a month of Concerts is plenty.
NEARBY_WINDOW = dt.timedelta(days=30)
NEARBY_SIZE = 12
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
    redis: Redis
    model: Model
    turnstile: httpx.AsyncClient


async def find_nearby(lat: float, lon: float, services: Services, today: dt.date) -> list[Concert]:
    """Notable Concerts soonest first, for the home page. This path never calls a model."""
    place = Place(name="Nearby", lat=lat, lon=lon)
    concerts = await pool.find_concerts(
        services.ticketmaster, services.redis, place, [], today, today + NEARBY_WINDOW, today
    )
    return [candidate.concert for candidate in matching.notable(concerts)[:NEARBY_SIZE]]


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
    return matching.Taste([*seeds, *extra], neighbours, interpretation.tags)


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


async def _steps(
    text: str, imported: Sequence[str], services: Services, today: dt.date
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
            start=interpretation.start,
            end=interpretation.end,
            artists=interpretation.artists,
        ),
    )

    if not (interpretation.place or interpretation.artists):
        if interpretation.descriptors or interpretation.tags:
            # Similar Artists start from a seed, so a style alone has nothing to look up.
            yield _error("needs_place", "Add a place or an Artist to your Search.")
        else:
            yield _error("needs_taste_or_place", ASK_FOR_A_SEARCH)
        return

    place = None
    if interpretation.place:
        message = f"Finding {interpretation.place}"
        yield _event("status", Status(step="resolve", message=message))
        with telemetry.step("resolve_place"):
            place = await geocoder.geocode(services.geocoder, services.redis, interpretation.place)
        if place is None:
            message = f"We could not find {interpretation.place}. Check the spelling."
            yield _error("place_not_found", message)
            return

    if interpretation.artists:
        message = f"Finding Artists like {', '.join(interpretation.artists)}"
        yield _event("status", Status(step="resolve", message=message))
    with telemetry.step("resolve_artists"):
        taste = await _find_taste(interpretation, names_only, services)

    if place:
        message = f"Looking for Concerts near {place.name}"
        lookups = interpretation.artists
    else:
        message = f"Looking for Concerts by {', '.join(interpretation.artists)} and similar Artists"
        lookups = [*interpretation.artists, *similarity.closest(taste.neighbours, DIRECT_LOOKUPS)]
    yield _event("status", Status(step="pool", message=message))
    with telemetry.step("pool"):
        concerts = await pool.find_concerts(
            services.ticketmaster,
            services.redis,
            place,
            lookups,
            interpretation.start,
            interpretation.end,
            today,
        )
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


async def run_search(
    text: str, imported: Sequence[str], services: Services
) -> AsyncIterator[ServerSentEvent]:
    with telemetry.search() as usage:
        try:
            async for event in stream_search(text, imported, services, dt.date.today()):
                yield event
        finally:
            # A visitor who leaves early has still cost money, so a cancel must not skip this.
            if not usage.complete:
                logger.warning("Search cost is incomplete")
            with anyio.CancelScope(shield=True):
                await limits.record_spend(services.redis, usage.cost)


async def stream_search(
    text: str, imported: Sequence[str], services: Services, today: dt.date
) -> AsyncIterator[ServerSentEvent]:
    try:
        async for event in _steps(text, imported, services, today):
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
