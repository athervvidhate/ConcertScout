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

from concert_scout.config import Settings
from concert_scout.models import SearchError
from concert_scout.pipeline import run_search
from concert_scout.sources import ticketmaster


class SearchRequest(BaseModel):
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    client = ticketmaster.make_client(settings.tm_key.get_secret_value(), transport)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await client.aclose()

    app = FastAPI(title="Concert Scout", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_search(_: Request, __: RequestValidationError) -> JSONResponse:
        error = SearchError(code="invalid_search", message="Enter a city.")
        return JSONResponse(error.model_dump(exclude_none=True), status_code=422)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/search", response_class=EventSourceResponse)
    async def search(search: SearchRequest) -> AsyncIterator[ServerSentEvent]:
        async for event in run_search(search.city, client):
            yield event

    return app
