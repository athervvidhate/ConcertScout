import datetime as dt
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout.interpreter import InterpreterError, interpret
from concert_scout.models import Interpreted, Poster, Recommendation, SearchError, Status
from concert_scout.sources import geocoder, ticketmaster

logger = logging.getLogger(__name__)

ASK_FOR_A_SEARCH = "Tell us an Artist, a style or a place."


@dataclass(frozen=True)
class Services:
    ticketmaster: httpx.AsyncClient
    geocoder: httpx.AsyncClient
    redis: Redis
    model: Model


def _event(name: str, payload: BaseModel | None = None) -> ServerSentEvent:
    data = payload.model_dump(mode="json", exclude_none=True) if payload else {}
    return ServerSentEvent(event=name, data=data)


def _error(code: str, message: str) -> ServerSentEvent:
    return _event("error", SearchError(code=code, message=message))


async def _steps(text: str, services: Services) -> AsyncIterator[ServerSentEvent]:
    yield _event("status", Status(step="interpret", message="Reading your Search"))
    interpretation = await interpret(text, dt.date.today(), services.model)
    yield _event(
        "interpreted",
        Interpreted(
            place=interpretation.place,
            start=interpretation.start,
            end=interpretation.end,
            artists=interpretation.artists,
        ),
    )

    if interpretation.place is None:
        if interpretation.artists or interpretation.descriptors or interpretation.tags:
            # Searching without a place arrives with the Concert pool's direct lookup.
            yield _error("needs_place", "Add a place to your Search, such as a city.")
        else:
            yield _error("needs_taste_or_place", ASK_FOR_A_SEARCH)
        return

    message = f"Finding {interpretation.place}"
    yield _event("status", Status(step="resolve", message=message))
    place = await geocoder.geocode(services.geocoder, services.redis, interpretation.place)
    if place is None:
        message = f"We could not find {interpretation.place}. Check the spelling."
        yield _error("place_not_found", message)
        return

    message = f"Looking for Concerts near {place.name}"
    yield _event("status", Status(step="pool", message=message))
    concerts = await ticketmaster.find_concerts(
        services.ticketmaster, place, interpretation.start, interpretation.end
    )
    recommendations = [Recommendation(concert=concert) for concert in concerts]
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
    except ticketmaster.TicketmasterError as exc:
        logger.warning("Ticketmaster failed: %s", exc)
        message = "Ticketmaster is not responding. Try again in a minute."
        yield _error("ticketmaster_unavailable", message)
    yield _event("done")
