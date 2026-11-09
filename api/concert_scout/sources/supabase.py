"""Supabase: who a request belongs to, and what is stored under that account: Saved Concerts,
Followed Artists and Alert settings.

Reads and removals run with the person's own access token, so the database's row policies decide
what they reach. Only writes use the secret key, because their Concert facts come from the source
here, and the owner is always the verified token's subject.
"""

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from pydantic import BaseModel, SecretStr

from concert_scout.models import Concert, Place
from concert_scout.sources.http import USER_AGENT

AUDIENCE = "authenticated"
ALGORITHMS = ["ES256", "RS256"]
KEYS_TTL = 600.0
# A token signed by a new key refetches the key set, but no more often than this.
REFETCH_GAP = 30.0
# Supabase's clock can run slightly ahead of ours, which makes a fresh token look early.
CLOCK_LEEWAY = 10
TABLE = "/rest/v1/saved_concerts"
FOLLOWED = "/rest/v1/followed_artists"
SETTINGS = "/rest/v1/alert_settings"
SENT = "/rest/v1/alerts_sent"


class SupabaseError(Exception):
    """Supabase failed or answered something unreadable. The message never holds a token."""


class InvalidToken(Exception):
    """The access token is not one this project signed, or it has expired."""


@dataclass(frozen=True)
class Account:
    id: str
    token: str
    # When each sign-in method last proved who this is, in Unix seconds.
    authenticated_at: int


class SavedConcert(BaseModel):
    concert: Concert
    reason: str | None = None


class FollowedArtist(BaseModel):
    artist_key: str
    name: str


class AlertSettings(BaseModel):
    place: Place | None = None
    enabled: bool = False


class AlertAccount(BaseModel):
    """An Account with Alerts on, as the daily run reads it."""

    user_id: str
    place: Place


def make_client(url: str, transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    # No retry transport: a repeated write after a lost answer must not be invisible to the caller.
    return httpx.AsyncClient(
        base_url=url.rstrip("/"),
        headers={"User-Agent": USER_AGENT},
        timeout=10.0,
        transport=transport,
    )


class Verifier:
    """Checks access tokens against the project's published signing keys, following rotation."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.issuer = str(client.base_url).rstrip("/") + "/auth/v1"
        self.keys: KeySet | None = None
        self.fetched = 0.0

    async def _keys(self, *, refresh: bool = False) -> KeySet:
        now = time.monotonic()
        stale = self.keys is None or now - self.fetched > KEYS_TTL
        if stale or (refresh and now - self.fetched > REFETCH_GAP):
            try:
                response = await self.client.get("/auth/v1/.well-known/jwks.json")
                response.raise_for_status()
                self.keys = KeySet.import_key_set(response.json())
            except (httpx.HTTPError, ValueError, JoseError) as exc:
                raise SupabaseError(f"signing keys: {type(exc).__name__}") from None
            self.fetched = now
        assert self.keys is not None
        return self.keys

    async def verify(self, token: str) -> Account:
        try:
            try:
                decoded = jwt.decode(token, await self._keys(), algorithms=ALGORITHMS)
            except InvalidKeyIdError:
                decoded = jwt.decode(token, await self._keys(refresh=True), algorithms=ALGORITHMS)
            jwt.JWTClaimsRegistry(
                leeway=CLOCK_LEEWAY,
                iss={"essential": True, "value": self.issuer},
                aud={"essential": True, "value": AUDIENCE},
                sub={"essential": True},
                exp={"essential": True},
                role={"essential": True, "value": AUDIENCE},
            ).validate(decoded.claims)
        except (JoseError, ValueError):
            raise InvalidToken from None
        claims = decoded.claims
        if claims.get("is_anonymous"):
            raise InvalidToken
        methods: list[dict[str, Any]] = claims.get("amr") or []
        moments = [int(m["timestamp"]) for m in methods if "timestamp" in m]
        return Account(id=str(claims["sub"]), token=token, authenticated_at=max(moments, default=0))


def _as_person(account: Account, publishable_key: str) -> dict[str, str]:
    return {"apikey": publishable_key, "Authorization": f"Bearer {account.token}"}


def _as_server(secret_key: SecretStr) -> dict[str, str]:
    return {"apikey": secret_key.get_secret_value()}


async def _send(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    try:
        response = await client.send(request)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SupabaseError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise SupabaseError(type(exc).__name__) from None
    return response


async def list_saved(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> list[SavedConcert]:
    request = client.build_request(
        "GET",
        TABLE,
        params={"select": "concert,reason", "order": "saved_at.asc"},
        headers=_as_person(account, publishable_key),
    )
    response = await _send(client, request)
    try:
        return [SavedConcert.model_validate(row) for row in response.json()]
    except ValueError as exc:
        raise SupabaseError(f"unreadable response: {type(exc).__name__}") from None


async def remove_saved(
    client: httpx.AsyncClient, publishable_key: str, account: Account, concert_id: str
) -> None:
    request = client.build_request(
        "DELETE",
        TABLE,
        params={"concert_id": f"eq.{concert_id}"},
        headers=_as_person(account, publishable_key),
    )
    await _send(client, request)


async def save(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    account: Account,
    saves: list[tuple[Concert, str | None]],
) -> None:
    """Saving a Concert again refreshes its facts and reason and keeps when it was first saved."""
    rows = [
        {
            "user_id": account.id,
            "concert_id": concert.id,
            "concert": concert.model_dump(mode="json", exclude_none=True),
            "reason": reason,
        }
        for concert, reason in saves
    ]
    request = client.build_request(
        "POST",
        TABLE,
        params={"on_conflict": "user_id,concert_id"},
        json=rows,
        headers=_as_server(secret_key)
        | {"Prefer": "resolution=merge-duplicates,return=minimal,missing=default"},
    )
    await _send(client, request)


async def delete_user(client: httpx.AsyncClient, secret_key: SecretStr, account: Account) -> None:
    """Deleting the sign-in identity also deletes every row the account owns."""
    request = client.build_request(
        "DELETE", f"/auth/v1/admin/users/{account.id}", headers=_as_server(secret_key)
    )
    await _send(client, request)


async def keep_awake(client: httpx.AsyncClient, secret_key: SecretStr) -> None:
    """One small database read. A free project pauses after a week without database activity, and
    a paused project stays down until its owner resumes it, so the daily cron makes this call."""
    request = client.build_request(
        "GET", TABLE, params={"select": "concert_id", "limit": 1}, headers=_as_server(secret_key)
    )
    await _send(client, request)


def _rows[T: BaseModel](response: httpx.Response, model: type[T]) -> list[T]:
    try:
        return [model.model_validate(row) for row in response.json()]
    except ValueError as exc:
        raise SupabaseError(f"unreadable response: {type(exc).__name__}") from None


def _among(user_ids: list[str]) -> str:
    return f"in.({','.join(user_ids)})"


async def list_followed(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> list[FollowedArtist]:
    request = client.build_request(
        "GET",
        FOLLOWED,
        params={"select": "artist_key,name", "order": "followed_at.asc"},
        headers=_as_person(account, publishable_key),
    )
    return _rows(await _send(client, request), FollowedArtist)


async def follow(
    client: httpx.AsyncClient, secret_key: SecretStr, account: Account, artist: FollowedArtist
) -> None:
    """Following an Artist again keeps the first follow and its spelling."""
    request = client.build_request(
        "POST",
        FOLLOWED,
        params={"on_conflict": "user_id,artist_key"},
        json=[{"user_id": account.id} | artist.model_dump()],
        headers=_as_server(secret_key) | {"Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    await _send(client, request)


async def unfollow(
    client: httpx.AsyncClient, publishable_key: str, account: Account, artist_key: str
) -> None:
    request = client.build_request(
        "DELETE",
        FOLLOWED,
        params={"artist_key": f"eq.{artist_key}"},
        headers=_as_person(account, publishable_key),
    )
    await _send(client, request)


async def alert_settings(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> AlertSettings:
    request = client.build_request(
        "GET",
        SETTINGS,
        params={"select": "place,enabled"},
        headers=_as_person(account, publishable_key),
    )
    rows = _rows(await _send(client, request), AlertSettings)
    return rows[0] if rows else AlertSettings()


async def set_alert_place(
    client: httpx.AsyncClient, secret_key: SecretStr, user_id: str, place: Place
) -> None:
    """Creates the Account's settings with Alerts off, or changes only the place."""
    row = {
        "user_id": user_id,
        "place": place.model_dump(mode="json"),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    request = client.build_request(
        "POST",
        SETTINGS,
        params={"on_conflict": "user_id"},
        json=[row],
        headers=_as_server(secret_key)
        | {"Prefer": "resolution=merge-duplicates,return=minimal,missing=default"},
    )
    await _send(client, request)


async def set_alerts_enabled(
    client: httpx.AsyncClient, secret_key: SecretStr, user_id: str, enabled: bool
) -> None:
    """Changes an existing row only. The table refuses Alerts switched on without a place."""
    request = client.build_request(
        "PATCH",
        SETTINGS,
        params={"user_id": f"eq.{user_id}"},
        json={"enabled": enabled, "updated_at": dt.datetime.now(dt.UTC).isoformat()},
        headers=_as_server(secret_key) | {"Prefer": "return=minimal"},
    )
    await _send(client, request)


async def accounts_with_alerts(
    client: httpx.AsyncClient, secret_key: SecretStr
) -> list[AlertAccount]:
    request = client.build_request(
        "GET",
        SETTINGS,
        params={"select": "user_id,place", "enabled": "is.true", "order": "updated_at.asc"},
        headers=_as_server(secret_key),
    )
    return _rows(await _send(client, request), AlertAccount)


async def followed_by(
    client: httpx.AsyncClient, secret_key: SecretStr, user_ids: list[str]
) -> dict[str, list[FollowedArtist]]:
    if not user_ids:
        return {}
    request = client.build_request(
        "GET",
        FOLLOWED,
        params={"select": "user_id,artist_key,name", "user_id": _among(user_ids)},
        headers=_as_server(secret_key),
    )
    followed: dict[str, list[FollowedArtist]] = {}
    for row in _rows(await _send(client, request), _FollowedRow):
        followed.setdefault(row.user_id, []).append(FollowedArtist(**row.model_dump()))
    return followed


async def sent_to(
    client: httpx.AsyncClient, secret_key: SecretStr, user_ids: list[str]
) -> dict[str, set[str]]:
    if not user_ids:
        return {}
    request = client.build_request(
        "GET",
        SENT,
        params={"select": "user_id,concert_id", "user_id": _among(user_ids)},
        headers=_as_server(secret_key),
    )
    sent: dict[str, set[str]] = {}
    for row in _rows(await _send(client, request), _SentRow):
        sent.setdefault(row.user_id, set()).add(row.concert_id)
    return sent


async def record_sent(
    client: httpx.AsyncClient, secret_key: SecretStr, user_id: str, concert_ids: list[str]
) -> None:
    request = client.build_request(
        "POST",
        SENT,
        params={"on_conflict": "user_id,concert_id"},
        json=[{"user_id": user_id, "concert_id": c} for c in concert_ids],
        headers=_as_server(secret_key) | {"Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    await _send(client, request)


async def email_of(client: httpx.AsyncClient, secret_key: SecretStr, user_id: str) -> str | None:
    """The Account's confirmed email address, or None when it has none."""
    request = client.build_request(
        "GET", f"/auth/v1/admin/users/{user_id}", headers=_as_server(secret_key)
    )
    try:
        user = (await _send(client, request)).json()
    except ValueError as exc:
        raise SupabaseError(f"unreadable response: {type(exc).__name__}") from None
    confirmed = user.get("email_confirmed_at")
    return user.get("email") if confirmed else None


class _FollowedRow(FollowedArtist):
    user_id: str


class _SentRow(BaseModel):
    user_id: str
    concert_id: str
