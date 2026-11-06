"""A separate Spotify shelf: encrypted sessions and exact names, with no model dependency."""

import datetime as dt
import hashlib
import hmac
import json
import secrets
from collections.abc import Sequence
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from concert_scout import limits, pool
from concert_scout.config import Settings
from concert_scout.models import Concert, Place
from concert_scout.names import normalize
from concert_scout.security import Refused
from concert_scout.sources import geocoder
from concert_scout.sources import ticketmaster as tm
from concert_scout.sources.spotify import (
    Client,
    Credentials,
    SpotifyArtist,
    SpotifyError,
    expired,
    reconnect,
)

PREFIX = "/auth/spotify"
SESSION_COOKIE = "concert_scout_spotify"
STATE_COOKIE = "concert_scout_spotify_state"
SESSION_TTL = 7 * 86400
STATE_TTL = 600


def session_key(session: str) -> str:
    return "spotify:session:" + hashlib.sha256(session.encode()).hexdigest()


class Sessions:
    def __init__(self, redis: Redis, key: str) -> None:
        self.redis, self.cipher = redis, Fernet(key.encode())

    async def save(self, session: str, token: Credentials, *, existing: bool = False) -> None:
        raw = json.dumps(
            {
                "access_token": token.access_token.get_secret_value(),
                "refresh_token": token.refresh_token.get_secret_value()
                if token.refresh_token
                else None,
                "expires_at": token.expires_at,
            }
        )
        encrypted = self.cipher.encrypt(raw.encode())
        if existing:
            # A concurrent Disconnect must never be undone by an in-flight refresh.
            stored = await self.redis.set(session_key(session), encrypted, xx=True, keepttl=True)
        else:
            stored = await self.redis.set(session_key(session), encrypted, ex=SESSION_TTL, nx=True)
        if not stored:
            raise reconnect()

    async def load(self, session: str | None) -> Credentials | None:
        if not session:
            return None
        raw = await self.redis.get(session_key(session))
        if raw is None:
            return None
        try:
            return Credentials.model_validate_json(self.cipher.decrypt(raw, ttl=SESSION_TTL))
        except (InvalidToken, ValidationError):
            await self.delete(session)
            return None

    async def delete(self, session: str) -> None:
        await self.redis.delete(session_key(session))


class ShelfConcert(BaseModel):
    concert: Concert
    artist: SpotifyArtist


def exact_matches(
    concerts: Sequence[Concert], artists: Sequence[SpotifyArtist]
) -> list[ShelfConcert]:
    wanted = {normalize(a.name): (rank, a) for rank, a in reversed(list(enumerate(artists)))}
    matches: dict[str, tuple[int, ShelfConcert]] = {}
    for concert in concerts:
        found = [wanted[normalize(a.name)] for a in concert.artists if normalize(a.name) in wanted]
        if found:
            rank, artist = min(found, key=lambda item: item[0])
            matches.setdefault(concert.id, (rank, ShelfConcert(concert=concert, artist=artist)))
    ordered = sorted(
        matches.values(), key=lambda item: (item[0], item[1].concert.date or dt.date.max)
    )
    return [item for _, item in ordered[:20]]


def router(
    settings: Settings, redis: Redis, ticketmaster: httpx.AsyncClient, geo: httpx.AsyncClient
) -> APIRouter:
    routes = APIRouter(prefix=PREFIX)
    ready = bool(
        settings.spotify_client_id
        and settings.spotify_client_secret
        and settings.spotify_encryption_key
    )
    sessions = (
        Sessions(redis, settings.spotify_encryption_key.get_secret_value())
        if ready and settings.spotify_encryption_key
        else None
    )
    client = Client(
        settings.spotify_client_id or "",
        settings.spotify_client_secret.get_secret_value() if settings.spotify_client_secret else "",
        settings.spotify_redirect_uri,
    )
    secure = urlsplit(settings.spotify_redirect_uri).scheme == "https"

    def configured() -> Sessions:
        if sessions is None:
            raise Refused(
                503,
                "spotify_not_configured",
                "Spotify connections are not available yet. Use another Taste import.",
            )
        return sessions

    def guard_origin(request: Request) -> None:
        if request.headers.get("origin") not in settings.cors_origins:
            raise Refused(403, "origin_refused", "This site cannot change a Spotify connection.")

    async def credentials(session: str | None) -> Credentials:
        store = configured()
        token = await store.load(session)
        if not token or not session:
            raise reconnect()
        if expired(token):
            try:
                token = await client.refresh(token)
                await store.save(session, token, existing=True)
            except SpotifyError as exc:
                if exc.status == 401:
                    await store.delete(session)
                raise
        return token

    async def limit(request: Request) -> None:
        from concert_scout.security import client_ip

        try:
            await limits.visitor_call(
                redis, "spotify", client_ip(request, settings.client_ip_header), 60
            )
        except limits.VisitorLimitReached as exc:
            raise Refused(
                429, "visitor_limit", "Try connecting to Spotify again later.", exc.retry_after
            ) from None

    @routes.get("/status")
    async def status(
        session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> dict[str, bool]:
        return {"available": ready, "connected": bool(sessions and await sessions.load(session))}

    @routes.get("/login")
    async def login(request: Request, return_to: str) -> RedirectResponse:
        configured()
        await limit(request)
        if return_to not in settings.cors_origins:
            raise Refused(
                400, "spotify_redirect_refused", "Return to Concert Scout to connect Spotify."
            )
        state = secrets.token_urlsafe(32)
        await redis.set(
            "spotify:state:" + hashlib.sha256(state.encode()).hexdigest(), return_to, ex=STATE_TTL
        )
        response = RedirectResponse(await client.authorization(state), status_code=303)
        response.set_cookie(
            STATE_COOKIE,
            state,
            max_age=STATE_TTL,
            httponly=True,
            secure=secure,
            samesite="lax",
            path=PREFIX + "/callback",
        )
        return response

    @routes.get("/callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        store = configured()
        cookie = request.cookies.get(STATE_COOKIE)
        if not state or not cookie or len(state) > 200 or not hmac.compare_digest(state, cookie):
            raise Refused(
                400,
                "spotify_state_invalid",
                "That Spotify connection request expired. Connect again.",
            )
        origin = await redis.getdel("spotify:state:" + hashlib.sha256(state.encode()).hexdigest())
        if not origin:
            raise Refused(
                400,
                "spotify_state_invalid",
                "That Spotify connection request expired. Connect again.",
            )
        return_to = origin.decode() if isinstance(origin, bytes) else origin
        if return_to not in settings.cors_origins:
            raise Refused(
                400, "spotify_state_invalid", "Return to Concert Scout to connect Spotify."
            )
        session: str | None = None
        result = "cancelled"
        if not error and code and len(code) <= 2048:
            try:
                token = await client.exchange(code)
                # The protected API returns 403 for a user outside Spotify's dashboard allowlist.
                await client.artists(token)
                session = secrets.token_urlsafe(32)
                await store.save(session, token)
                old = request.cookies.get(SESSION_COOKIE)
                if old:
                    await store.delete(old)
                result = "connected"
            except SpotifyError as exc:
                result = "not_allowed" if exc.status == 403 else "unavailable"
        response = RedirectResponse(f"{return_to}/?spotify={result}", status_code=303)
        response.delete_cookie(
            STATE_COOKIE, path=PREFIX + "/callback", secure=secure, httponly=True, samesite="lax"
        )
        if session:
            response.set_cookie(
                SESSION_COOKIE,
                session,
                max_age=SESSION_TTL,
                httponly=True,
                secure=secure,
                samesite="lax",
                path=PREFIX,
            )
        return response

    @routes.post("/disconnect")
    async def disconnect(request: Request) -> Response:
        guard_origin(request)
        if session := request.cookies.get(SESSION_COOKIE):
            await redis.delete(session_key(session))
        response = Response(status_code=204)
        response.delete_cookie(
            SESSION_COOKIE, path=PREFIX, secure=secure, httponly=True, samesite="lax"
        )
        return response

    @routes.get("/shelf", response_model_exclude_none=True)
    async def shelf(
        request: Request,
        session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        place: Annotated[str | None, Query(max_length=500)] = None,
        lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
        lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
    ) -> dict[str, list[ShelfConcert]]:
        await limit(request)
        token = await credentials(session)
        try:
            artists = await client.artists(token)
        except SpotifyError as exc:
            if exc.status in {401, 403} and session:
                await configured().delete(session)
            raise
        where: Place | None = None
        if lat is not None and lon is not None:
            where = Place(name="Nearby", lat=lat, lon=lon)
        elif place:
            try:
                where = await geocoder.geocode(geo, redis, place)
            except geocoder.GeocoderError:
                raise Refused(
                    503, "geocoder_unavailable", "We could not look up that place. Try again soon."
                ) from None
        if where is None:
            raise Refused(
                422,
                "spotify_needs_place",
                "Search a place or use your location to see Concerts from your top Artists.",
            )
        try:
            concerts = await pool.find_concerts(
                ticketmaster, redis, where, [], start, end, dt.date.today()
            )
        except tm.TicketmasterError:
            raise Refused(
                503, "ticketmaster_unavailable", "Ticketmaster is not responding. Try again soon."
            ) from None
        except limits.DailyLimitReached as exc:
            raise Refused(
                429,
                "ticketmaster_limit",
                "We have used today's Ticketmaster allowance. Try again tomorrow.",
                exc.retry_after,
            ) from None
        return {"concerts": exact_matches(concerts, artists)}

    return routes
