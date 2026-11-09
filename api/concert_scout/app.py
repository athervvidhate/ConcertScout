import datetime as dt
import hmac
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, StringConstraints
from pydantic_ai.models import Model
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import (
    accounts,
    cache,
    feedback,
    home,
    interpreter,
    limits,
    security,
    spotify,
    sync,
    warm,
)
from concert_scout.config import Settings
from concert_scout.models import ArtistProfiles, ImportedTaste, Place, SearchError
from concert_scout.pipeline import (
    ASK_FOR_A_SEARCH,
    Services,
    find_artist_profiles,
    run_search,
)
from concert_scout.security import Refused, SecurityHeaders
from concert_scout.sources import (
    geocoder,
    jambase,
    jev,
    lastfm,
    listenbrainz,
    musicbrainz,
    spotify_catalog,
    supabase,
    ticketmaster,
)
from concert_scout.sources.spotify import SpotifyError

logger = logging.getLogger(__name__)

IMPORT_SIZE = 50
MAX_TASTE = 100


def _failure(status: int, error: SearchError) -> JSONResponse:
    return JSONResponse(error.model_dump(exclude_none=True), status_code=status)


class TasteRequest(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


ArtistName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Coordinates(BaseModel):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class SearchRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    token: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    taste: Annotated[list[ArtistName], Field(max_length=MAX_TASTE)] = []
    # A location the visitor already shared, used when the Search names no place.
    near: Coordinates | None = None
    # The browser's zone, so "this weekend" and "today" mean the visitor's own days.
    time_zone: Annotated[str, StringConstraints(max_length=64)]


def _catalog_client(
    settings: Settings, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient | None:
    if not (settings.spotify_client_id and settings.spotify_client_secret):
        return None
    secret = settings.spotify_client_secret.get_secret_value()
    return spotify_catalog.make_client(settings.spotify_client_id, secret, transport)


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
        jev=jev.make_client(settings.typesafe_api_key.get_secret_value(), transport),
        lastfm=lastfm_client,
        spotify_catalog=_catalog_client(settings, transport),
        redis=redis or cache.make_client(settings.redis_url),
        model=model or interpreter.make_model(settings.anthropic_api_key.get_secret_value()),
        turnstile=security.make_turnstile_client(transport),
        jambase=jambase.make_client(settings.jbd_api_key.get_secret_value(), transport)
        if settings.jbd_api_key
        else None,
        jambase_days=settings.jambase_days,
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
    accounts_client = (
        supabase.make_client(settings.supabase_url, transport)
        if settings.supabase_url and settings.accounts_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await services.ticketmaster.aclose()
        if services.jambase:
            await services.jambase.aclose()
        await services.geocoder.aclose()
        await services.musicbrainz.aclose()
        await services.listenbrainz.aclose()
        await services.jev.aclose()
        if services.lastfm:
            await services.lastfm.aclose()
        if services.spotify_catalog:
            await services.spotify_catalog.aclose()
        await services.turnstile.aclose()
        await services.redis.aclose()
        if accounts_client:
            await accounts_client.aclose()

    app = FastAPI(title="Concert Scout", lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
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
            message = "Search is off for now."
            raise Refused(503, "search_off", message)
        ip = security.client_ip(request, settings.client_ip_header)
        try:
            await limits.check_spend(services.redis)
            await limits.visitor_call(services.redis, "search", ip, settings.searches_per_hour)
        except limits.SpendCapReached as exc:
            message = "Concert Scout has used its Search budget for now."
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
        if request.url.path == "/artist":
            return _failure(422, SearchError(code="invalid_artist", message="Choose an Artist."))
        if request.url.path.startswith(accounts.PREFIX):
            message = "That is not a Concert you can save."
            return _failure(422, SearchError(code="invalid_save", message=message))
        if request.url.path.startswith("/taste/"):
            return _failure(422, SearchError(code="invalid_username", message="Enter a username."))
        return _failure(422, SearchError(code="invalid_place", message="Choose a place."))

    @app.exception_handler(RedisError)
    async def storage_error(_: Request, __: RedisError) -> JSONResponse:
        return _failure(
            503,
            SearchError(
                code="storage_unavailable",
                message="Connection storage is unavailable. Try again soon.",
            ),
        )

    @app.exception_handler(SpotifyError)
    async def spotify_error(_: Request, exc: SpotifyError) -> JSONResponse:
        return _failure(exc.status, SearchError(code=exc.code, message=exc.message))

    app.include_router(
        spotify.router(settings, services.redis, services.ticketmaster, services.geocoder)
    )
    app.include_router(feedback.router(settings, services.redis, transport))
    if accounts_client:
        app.include_router(
            accounts.router(settings, accounts_client, services.redis, services.ticketmaster)
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/examples", response_model=home.Examples, response_model_exclude_none=True)
    async def examples() -> home.Examples:
        return await home.read(services.redis, dt.datetime.now(dt.UTC).date())

    if settings.cron_secret:
        expected = f"Bearer {settings.cron_secret.get_secret_value()}".encode()

        async def scheduler_only(authorization: Annotated[str, Header()] = "") -> None:
            if not hmac.compare_digest(authorization.encode(), expected):
                raise Refused(401, "not_scheduler", "Only the scheduler can run this job.")

        scheduled = APIRouter(dependencies=[Depends(scheduler_only)], include_in_schema=False)

        # Only this authenticated job builds the public example Posters.
        @scheduled.get("/warm")
        async def warm_cache() -> list[warm.Warmed]:
            if accounts_client and settings.supabase_secret_key:
                try:
                    await supabase.keep_awake(accounts_client, settings.supabase_secret_key)
                except supabase.SupabaseError as exc:
                    logger.warning("Supabase keep-awake failed: %s", exc)
            warmed = await warm.warm(services, dt.datetime.now(dt.UTC))
            if settings.search_enabled:
                await home.refresh(services)
            return warmed

        # Once a day: the JamBase Catalog, then MusicBrainz IDs.
        @scheduled.get("/sync")
        async def sync_catalog() -> list[sync.Step]:
            return await sync.run(services, dt.datetime.now(dt.UTC))

        app.include_router(scheduled)

    @app.get("/artist", response_model=ArtistProfiles, response_model_exclude_none=True)
    async def artist(
        request: Request, name: Annotated[str, Query(min_length=1, max_length=200)]
    ) -> ArtistProfiles:
        await limit_visitor(request, "artist", limits.ARTIST_PER_HOUR)
        return ArtistProfiles(profiles=await find_artist_profiles(name, services))

    # A POST, so the username stays out of access logs.
    @app.post("/taste/{source}")
    async def import_taste(
        request: Request, source: Literal["lastfm", "listenbrainz"], body: TasteRequest
    ) -> ImportedTaste:
        await limit_visitor(request, "taste", limits.TASTE_PER_HOUR)
        return ImportedTaste(artists=await _top_artists(source, body.username, services))

    @app.post("/search", response_class=EventSourceResponse, dependencies=[Depends(guard_search)])
    async def search(search: SearchRequest) -> AsyncIterator[ServerSentEvent]:
        here = search.near
        near = Place(name="Near you", lat=here.lat, lon=here.lon) if here else None
        async for event in run_search(search.text, search.taste, near, search.time_zone, services):
            yield event

    return app
