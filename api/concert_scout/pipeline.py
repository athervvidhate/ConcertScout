import asyncio
import datetime as dt
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout import limits, matching, pool, similarity
from concert_scout.interpreter import InterpreterError, Interpretation, interpret
from concert_scout.models import (
    Candidates,
    Interpreted,
    PoolTotal,
    Poster,
    Recommendation,
    SearchError,
    SeedArtist,
    Status,
)
from concert_scout.sources import geocoder, listenbrainz, musicbrainz, ticketmaster

logger = logging.getLogger(__name__)

ASK_FOR_A_SEARCH = "Tell us an Artist, a style or a place."
# With no place there is no pool, so this many similar Artists get looked up by name.
DIRECT_LOOKUPS = 15


@dataclass(frozen=True)
class Services:
    ticketmaster: httpx.AsyncClient
    geocoder: httpx.AsyncClient
    musicbrainz: httpx.AsyncClient
    listenbrainz: httpx.AsyncClient
    lastfm: httpx.AsyncClient | None
    redis: Redis
    model: Model


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


async def _find_taste(interpretation: Interpretation, services: Services) -> matching.Taste:
    seeds = await asyncio.gather(*(_resolve_seed(n, services) for n in interpretation.artists))
    neighbours = await similarity.find_neighbours(
        services.listenbrainz, services.lastfm, services.redis, seeds
    )
    return matching.Taste(seeds, neighbours, interpretation.tags)


async def _steps(text: str, services: Services) -> AsyncIterator[ServerSentEvent]:
    yield _event("status", Status(step="interpret", message="Reading your Search"))
    today = dt.date.today()
    interpretation = await interpret(text, today, services.model)
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
        place = await geocoder.geocode(services.geocoder, services.redis, interpretation.place)
        if place is None:
            message = f"We could not find {interpretation.place}. Check the spelling."
            yield _error("place_not_found", message)
            return

    if interpretation.artists:
        message = f"Finding Artists like {', '.join(interpretation.artists)}"
        yield _event("status", Status(step="resolve", message=message))
    taste = await _find_taste(interpretation, services)

    if place:
        message = f"Looking for Concerts near {place.name}"
        lookups = interpretation.artists
    else:
        message = f"Looking for Concerts by {', '.join(interpretation.artists)} and similar Artists"
        lookups = [*interpretation.artists, *similarity.closest(taste.neighbours, DIRECT_LOOKUPS)]
    yield _event("status", Status(step="pool", message=message))
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
        artist_tags = await listenbrainz.artist_tags(
            services.listenbrainz, services.redis, sorted(mbids)
        )
    shortlist = matching.shortlist(matching.score_concerts(concerts, taste, artist_tags))
    names = matching.candidate_names(shortlist)
    yield _event("candidates", Candidates(names=names, total=len(shortlist)))

    recommendations = [Recommendation(concert=c.concert) for c in shortlist]
    yield _event("poster", Poster(recommendations=recommendations))


async def run_search(text: str, services: Services) -> AsyncIterator[ServerSentEvent]:
    try:
        async for event in _steps(text, services):
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
