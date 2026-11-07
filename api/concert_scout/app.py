import datetime as dt
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, StringConstraints
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout import cache, interpreter, limits
from concert_scout.config import Settings
from concert_scout.models import Nearby, Places, SearchError
from concert_scout.pipeline import ASK_FOR_A_SEARCH, Services, find_nearby, run_search
from concert_scout.sources import geocoder, lastfm, listenbrainz, musicbrainz, ticketmaster

logger = logging.getLogger(__name__)


def _failure(status: int, error: SearchError) -> JSONResponse:
    return JSONResponse(error.model_dump(exclude_none=True), status_code=status)


class SearchRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def make_services(
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
    redis: Redis | None = None,
    model: Model | None = None,
) -> Services:
    lastfm_client = None
    if settings.lastfm_key:
        lastfm_client = lastfm.make_client(settings.lastfm_key.get_secret_value(), transport)
    return Services(
        ticketmaster=ticketmaster.make_client(settings.tm_key.get_secret_value(), transport),
        geocoder=geocoder.make_client(settings.geoapify_key.get_secret_value(), transport),
        musicbrainz=musicbrainz.make_client(transport),
        listenbrainz=listenbrainz.make_client(transport),
        lastfm=lastfm_client,
        redis=redis or cache.make_client(settings.redis_url),
        model=model or interpreter.make_model(settings.anthropic_api_key.get_secret_value()),
    )


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    redis: Redis | None = None,
    model: Model | None = None,
) -> FastAPI:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    services = make_services(settings, transport, redis, model)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await services.ticketmaster.aclose()
        await services.geocoder.aclose()
        await services.musicbrainz.aclose()
        await services.listenbrainz.aclose()
        if services.lastfm:
            await services.lastfm.aclose()
        await services.redis.aclose()

    app = FastAPI(title="Concert Scout", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _: RequestValidationError) -> JSONResponse:
        if request.url.path == "/search":
            return _failure(422, SearchError(code="invalid_search", message=ASK_FOR_A_SEARCH))
        return _failure(422, SearchError(code="invalid_place", message="Choose a place."))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/places", response_model=Places)
    async def places(
        text: Annotated[str, Query(min_length=2, max_length=100)],
    ) -> Places | JSONResponse:
        try:
            found = await geocoder.find_places(services.geocoder, services.redis, text)
        except geocoder.GeocoderError as exc:
            logger.warning("Geocoder failed: %s", exc)
            message = "We could not look up places. Try again in a minute."
            return _failure(503, SearchError(code="geocoder_unavailable", message=message))
        return Places(places=found)

    @app.get("/nearby", response_model=Nearby, response_model_exclude_none=True)
    async def nearby(
        lat: Annotated[float, Query(ge=-90, le=90)],
        lon: Annotated[float, Query(ge=-180, le=180)],
    ) -> Nearby | JSONResponse:
        try:
            concerts = await find_nearby(lat, lon, services, dt.date.today())
        except limits.DailyLimitReached as exc:
            message = "We have used today's Ticketmaster allowance. Try again tomorrow."
            error = SearchError(
                code="ticketmaster_limit", message=message, retry_after=exc.retry_after
            )
            return _failure(429, error)
        except ticketmaster.TicketmasterError as exc:
            logger.warning("Ticketmaster failed: %s", exc)
            message = "Ticketmaster is not responding. Try again in a minute."
            return _failure(503, SearchError(code="ticketmaster_unavailable", message=message))
        return Nearby(concerts=concerts)

    @app.post("/search", response_class=EventSourceResponse)
    async def search(search: SearchRequest) -> AsyncIterator[ServerSentEvent]:
        async for event in run_search(search.text, services):
            yield event

    return app
