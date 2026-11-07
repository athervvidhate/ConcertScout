"""Official OAuth and minimal Spotify metadata. Never imported by the Search pipeline."""

import time
from typing import Any, cast

import httpx
import httpx2
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from pydantic import BaseModel, SecretStr

from concert_scout.sources import http

AUTHORIZE = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "user-top-read user-follow-read"


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
    followed: bool = False


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

    async def artists(self, token: Credentials) -> list[SpotifyArtist]:
        artists: list[SpotifyArtist] = []
        async with http.make_client(API, {}) as client:
            for path, params in (
                ("/me/top/artists", {"limit": "50", "time_range": "medium_term"}),
                ("/me/following", {"type": "artist", "limit": "50"}),
            ):
                try:
                    response = await client.get(
                        path,
                        params=params,
                        headers={
                            "Authorization": f"Bearer {token.access_token.get_secret_value()}"
                        },
                    )
                    if response.status_code == 403:
                        raise not_allowed()
                    if response.status_code == 401:
                        raise reconnect()
                    response.raise_for_status()
                    body: dict[str, Any] = response.json()
                    records = (
                        body["artists"]["items"] if path.endswith("following") else body["items"]
                    )
                    artists.extend(
                        SpotifyArtist(
                            name=r["name"],
                            url=r["external_urls"]["spotify"],
                            followed=path.endswith("following"),
                        )
                        for r in records
                    )
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    raise unavailable() from None
        # Top Artists first, then followed Artists. The shelf only does exact-name lookups.
        firsts: dict[str, SpotifyArtist] = {}
        for artist in artists:
            firsts.setdefault(artist.name, artist)
        return list(firsts.values())


def expired(token: Credentials) -> bool:
    return token.expires_at <= time.time() + 60
