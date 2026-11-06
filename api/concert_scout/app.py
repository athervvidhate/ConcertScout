import datetime as dt
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, StringConstraints
from pydantic_ai.models import Model
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import cache, interpreter, limits, security
from concert_scout.config import Settings
from concert_scout.models import ImportedTaste, Nearby, Places, SearchError
from concert_scout.pipeline import ASK_FOR_A_SEARCH, Services, find_nearby, run_search
from concert_scout.security import Refused, SecurityHeaders
from concert_scout.sources import geocoder, lastfm, listenbrainz, musicbrainz, ticketmaster

logger = logging.getLogger(__name__)

IMPORT_SIZE = 50
MAX_TASTE = 100


def _failure(status: int, error: SearchError) -> JSONResponse:
    return JSONResponse(error.model_dump(exclude_none=True), status_code=status)


class TasteRequest(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


ArtistName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SearchRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    token: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    taste: Annotated[list[ArtistName], Field(max_length=MAX_TASTE)] = []


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
        turnstile=security.make_turnstile_client(transport),
    )


async def _top_artists(source: str, username: str, services: Services) -> list[str]:
    """Usernames stay out of the logs: they identify a person."""
    name = "Last.fm" if source == "lastfm" else "ListenBrainz"
    unavailable = Refused(503, "taste_unavailable", f"{name} is not answering. Try again soon.")
    try:
        if source == "listenbrainz":
            artists = await listenbrainz.top_artists(services.listenbrainz, username, IMPORT_SIZE)
        elif services.lastfm:
            artists = await lastfm.top_artists(services.lastfm, username, IMPORT_SIZE)
        else:
            raise unavailable
    except (lastfm.UserNotFound, listenbrainz.UserNotFound):
        message = f"We could not find that {name} username. Check the spelling."
        raise Refused(404, "taste_user_not_found", message) from None
    except lastfm.PrivateUser:
        message = (
            "That Last.fm profile hides its listening. Turn that off in Last.fm's privacy settings."
        )
        raise Refused(403, "taste_private", message) from None
    except (lastfm.LastfmError, listenbrainz.ListenBrainzError) as exc:
        logger.warning("Taste import failed: %s", exc)
        raise unavailable from None
    if not artists:
        raise Refused(404, "taste_empty", f"That {name} account has no listening to import yet.")
    return artists


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
        await services.turnstile.aclose()
        await services.redis.aclose()

    app = FastAPI(title="Concert Scout", lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    async def limit_visitor(request: Request, bucket: str, limit: int) -> None:
        """A lookup risks no model spend, so a Redis outage lets it through."""
        ip = security.client_ip(request, settings.client_ip_header)
        try:
            await limits.visitor_call(services.redis, bucket, ip, limit)
        except limits.VisitorLimitReached as exc:
            message = "That is a lot of lookups. Try again soon."
            raise Refused(429, "visitor_limit", message, exc.retry_after) from None
        except RedisError as exc:
            logger.warning("Visitor limit failed: %s", type(exc).__name__)

    async def guard_search(search: SearchRequest, request: Request) -> None:
        """The cheapest refusals come first, so abuse costs no outbound call."""
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            raise Refused(403, "origin_refused", "This site cannot run Searches.")
        if not settings.search_enabled:
            message = "Search is off for now. Nearby Concerts still work."
            raise Refused(503, "search_off", message)
        ip = security.client_ip(request, settings.client_ip_header)
        try:
            await limits.check_spend(services.redis)
            await limits.visitor_call(services.redis, "search", ip, limits.SEARCHES_PER_HOUR)
        except limits.SpendCapReached as exc:
            message = (
                "Concert Scout has used its Search budget for now. Nearby Concerts still work."
            )
            raise Refused(503, "budget_reached", message, exc.retry_after) from None
        except limits.VisitorLimitReached as exc:
            minutes = exc.retry_after // 60 + 1
            wait = "1 minute" if minutes == 1 else f"{minutes} minutes"
            message = f"You have used this hour's Searches. Try again in {wait}."
            raise Refused(429, "visitor_limit", message, exc.retry_after) from None
        except RedisError as exc:
            # Without Redis, spend cannot be counted, so a Search could overspend unseen.
            logger.warning("Limits failed: %s", type(exc).__name__)
            message = "Search is unavailable. Try again in a minute."
            raise Refused(503, "limits_unavailable", message) from None
        await security.verify_turnstile(
            services.turnstile, settings.turnstile_secret, search.token, ip
        )

    @app.exception_handler(Refused)
    async def refused(_: Request, exc: Refused) -> JSONResponse:
        return _failure(exc.status, exc.error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _: RequestValidationError) -> JSONResponse:
        if request.url.path == "/search":
            return _failure(422, SearchError(code="invalid_search", message=ASK_FOR_A_SEARCH))
        if request.url.path.startswith("/taste/"):
            return _failure(422, SearchError(code="invalid_username", message="Enter a username."))
        return _failure(422, SearchError(code="invalid_place", message="Choose a place."))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/places", response_model=Places)
    async def places(
        request: Request,
        text: Annotated[str, Query(min_length=2, max_length=100)],
    ) -> Places | JSONResponse:
        await limit_visitor(request, "places", limits.PLACES_PER_HOUR)
        try:
            found = await geocoder.find_places(services.geocoder, services.redis, text)
        except geocoder.GeocoderError as exc:
            logger.warning("Geocoder failed: %s", exc)
            message = "We could not look up places. Try again in a minute."
            return _failure(503, SearchError(code="geocoder_unavailable", message=message))
        return Places(places=found)

    @app.get("/nearby", response_model=Nearby, response_model_exclude_none=True)
    async def nearby(
        request: Request,
        lat: Annotated[float, Query(ge=-90, le=90)],
        lon: Annotated[float, Query(ge=-180, le=180)],
    ) -> Nearby | JSONResponse:
        await limit_visitor(request, "nearby", limits.NEARBY_PER_HOUR)
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

    # A POST, so the username stays out of access logs.
    @app.post("/taste/{source}")
    async def import_taste(
        request: Request, source: Literal["lastfm", "listenbrainz"], body: TasteRequest
    ) -> ImportedTaste:
        await limit_visitor(request, "taste", limits.TASTE_PER_HOUR)
        return ImportedTaste(artists=await _top_artists(source, body.username, services))

    @app.post("/search", response_class=EventSourceResponse, dependencies=[Depends(guard_search)])
    async def search(search: SearchRequest) -> AsyncIterator[ServerSentEvent]:
        async for event in run_search(search.text, search.taste, services):
            yield event

    return app
