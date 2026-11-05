import logging
from collections.abc import AsyncIterator

import httpx
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel

from concert_scout.models import Poster, Recommendation, SearchError, Status
from concert_scout.sources import ticketmaster

logger = logging.getLogger(__name__)


def _event(name: str, payload: BaseModel | None = None) -> ServerSentEvent:
    data = payload.model_dump(mode="json", exclude_none=True) if payload else {}
    return ServerSentEvent(event=name, data=data)


async def run_search(city: str, client: httpx.AsyncClient) -> AsyncIterator[ServerSentEvent]:
    yield _event("status", Status(step="pool", message=f"Looking for Concerts in {city}"))
    try:
        concerts = await ticketmaster.find_concerts(client, city)
    except ticketmaster.TicketmasterError as exc:
        logger.warning("Ticketmaster failed: %s", exc)
        message = "Ticketmaster is not responding. Try again in a minute."
        yield _event("error", SearchError(code="ticketmaster_unavailable", message=message))
    else:
        recommendations = [Recommendation(concert=concert) for concert in concerts]
        yield _event("poster", Poster(recommendations=recommendations))
    yield _event("done")
