"""Official OAuth and minimal Spotify metadata. Never imported by the Search pipeline."""

import asyncio
import time
from collections.abc import Iterable
from typing import Any, Literal, cast

import httpx
import httpx2
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from pydantic import BaseModel, SecretStr

from concert_scout.sources import http

AUTHORIZE = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "user-top-read user-follow-read user-library-read"
PAGE_SIZE = 50
TIME_RANGES = ("medium_term", "short_term", "long_term")
# Spotify reports no play counts, so Liked Songs are read newest first up to this many pages.
MAX_LIKED_PAGES = 20
MAX_FOLLOWED_PAGES = 20


class SpotifyError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


def unavailable() -> SpotifyError:
    return SpotifyError(503, "spotify_unavailable", "Spotify is not answering. Try again soon.")


def reconnect() -> SpotifyError:
    return SpotifyError(401, "spotify_reconnect", "Your Spotify connection expired. Connect again.")


def not_allowed() -> SpotifyError:
    return SpotifyError(
        403,
        "spotify_not_allowed",
        "This Spotify account is not on the app's invite list. "
        "Use a history file or another Taste import instead.",
    )


class Credentials(BaseModel):
    access_token: SecretStr
    refresh_token: SecretStr | None = None
    expires_at: float


class SpotifyArtist(BaseModel):
    name: str
    url: str
    source: Literal["top", "track", "followed", "liked"]


class Client:
    def __init__(self, client_id: str, secret: str, redirect_uri: str) -> None:
        self.client_id, self.secret, self.redirect_uri = client_id, secret, redirect_uri

    def _oauth(self) -> Any:
        return AsyncOAuth2Client(
            self.client_id,
            self.secret,
            redirect_uri=self.redirect_uri,
            scope=SCOPES,
            token_endpoint_auth_method="client_secret_basic",
            timeout=10.0,
            headers={"User-Agent": http.USER_AGENT},
            transport=httpx2.AsyncHTTPTransport(retries=2),
        )

    async def authorization(self, state: str) -> str:
        async with self._oauth() as client:
            url, _ = client.create_authorization_url(AUTHORIZE, state=state)
            return cast(str, url)

    async def exchange(self, code: str) -> Credentials:
        try:
            async with self._oauth() as client:
                token = await client.fetch_token(TOKEN, code=code, grant_type="authorization_code")
            return Credentials.model_validate(token)
        except (OAuthError, httpx2.HTTPError, ValueError, KeyError):
            raise unavailable() from None

    async def refresh(self, old: Credentials) -> Credentials:
        if not old.refresh_token:
            raise reconnect()
        try:
            async with self._oauth() as client:
                token = await client.refresh_token(
                    TOKEN, refresh_token=old.refresh_token.get_secret_value()
                )
            current = Credentials.model_validate(token)
            # Providers need not rotate the refresh token on every refresh.
            return current.model_copy(
                update={"refresh_token": current.refresh_token or old.refresh_token}
            )
        except OAuthError as exc:
            if exc.error == "invalid_grant":
                raise reconnect() from None
            raise unavailable() from None
        except (httpx2.HTTPError, ValueError, KeyError):
            raise unavailable() from None

    async def check(self, token: Credentials) -> None:
        """The protected API returns 403 for a user outside Spotify's dashboard allowlist."""
        async with http.make_client(API, {}) as client:
            await _read(client, token, "/me/top/artists", {"limit": "1"})

    async def artists(self, token: Credentials) -> list[SpotifyArtist]:
        """Everything the shelf looks up, strongest signal first. Each name appears once."""
        async with http.make_client(API, {}) as client:
            pages = await asyncio.gather(
                *(_top(client, token, "artists", span) for span in TIME_RANGES),
                *(_top(client, token, "tracks", span) for span in TIME_RANGES),
            )
            top = [_artist(a, "top") for page in pages[:3] for a in page]
            tracks = [
                _artist(a, "track")
                for page in pages[3:]
                for track in page
                for a in track["artists"]
            ]
            followed = await _followed(client, token)
            liked = await _liked(client, token)
        firsts: dict[str, SpotifyArtist] = {}
        for artist in [*top, *tracks, *followed, *liked]:
            if artist.url:
                firsts.setdefault(artist.name, artist)
        return list(firsts.values())


async def _read(
    client: httpx.AsyncClient, token: Credentials, path: str, params: dict[str, str]
) -> dict[str, Any]:
    try:
        response = await client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {token.access_token.get_secret_value()}"},
        )
        if response.status_code == 403:
            raise not_allowed()
        if response.status_code == 401:
            raise reconnect()
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
    except (httpx.HTTPError, ValueError):
        raise unavailable() from None


def _artist(
    record: dict[str, Any], source: Literal["top", "track", "followed", "liked"]
) -> SpotifyArtist:
    try:
        return SpotifyArtist(
            name=record["name"],
            url=record.get("external_urls", {}).get("spotify", ""),
            source=source,
        )
    except (KeyError, TypeError, ValueError):
        raise unavailable() from None


def _records(body: dict[str, Any], *path: str) -> list[dict[str, Any]]:
    try:
        found: Any = body
        for key in path:
            found = found[key]
        return cast(list[dict[str, Any]], list(cast(Iterable[Any], found)))
    except (KeyError, TypeError):
        raise unavailable() from None


async def _top(
    client: httpx.AsyncClient, token: Credentials, kind: str, span: str
) -> list[dict[str, Any]]:
    params = {"limit": str(PAGE_SIZE), "time_range": span}
    return _records(await _read(client, token, f"/me/top/{kind}", params), "items")


async def _followed(client: httpx.AsyncClient, token: Credentials) -> list[SpotifyArtist]:
    artists: list[SpotifyArtist] = []
    params = {"type": "artist", "limit": str(PAGE_SIZE)}
    for _ in range(MAX_FOLLOWED_PAGES):
        body = await _read(client, token, "/me/following", params)
        artists += [_artist(a, "followed") for a in _records(body, "artists", "items")]
        cursors: dict[str, Any] = body["artists"].get("cursors") or {}
        after: str | None = cursors.get("after")
        if not after:
            break
        params = params | {"after": after}
    return artists


async def _liked(client: httpx.AsyncClient, token: Credentials) -> list[SpotifyArtist]:
    artists: list[SpotifyArtist] = []
    for page in range(MAX_LIKED_PAGES):
        params = {"limit": str(PAGE_SIZE), "offset": str(page * PAGE_SIZE)}
        body = await _read(client, token, "/me/tracks", params)
        for entry in _records(body, "items"):
            track: dict[str, Any] = entry.get("track") or {}
            artists += [_artist(a, "liked") for a in track.get("artists", [])]
        if not body.get("next"):
            break
    return artists


def expired(token: Credentials) -> bool:
    return token.expires_at <= time.time() + 60
