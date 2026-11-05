from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, StringConstraints
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout import cache, interpreter
from concert_scout.config import Settings
from concert_scout.models import SearchError
from concert_scout.pipeline import ASK_FOR_A_SEARCH, Services, run_search
from concert_scout.sources import geocoder, lastfm, listenbrainz, musicbrainz, ticketmaster


class SearchRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    redis: Redis | None = None,
    model: Model | None = None,
) -> FastAPI:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    lastfm_client = None
    if settings.lastfm_key:
        lastfm_client = lastfm.make_client(settings.lastfm_key.get_secret_value(), transport)
    services = Services(
        ticketmaster=ticketmaster.make_client(settings.tm_key.get_secret_value(), transport),
        geocoder=geocoder.make_client(settings.geoapify_key.get_secret_value(), transport),
        musicbrainz=musicbrainz.make_client(transport),
        listenbrainz=listenbrainz.make_client(transport),
        lastfm=lastfm_client,
        redis=redis or cache.make_client(settings.redis_url),
        model=model or interpreter.make_model(settings.anthropic_api_key.get_secret_value()),
    )

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
    async def invalid_search(_: Request, __: RequestValidationError) -> JSONResponse:
        error = SearchError(code="invalid_search", message=ASK_FOR_A_SEARCH)
        return JSONResponse(error.model_dump(exclude_none=True), status_code=422)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/search", response_class=EventSourceResponse)
    async def search(search: SearchRequest) -> AsyncIterator[ServerSentEvent]:
        async for event in run_search(search.text, services):
            yield event

    return app
