"""Supabase: who a request belongs to, and the Saved Concerts stored under that account.

Reads and removals run with the person's own access token, so the database's row policies decide
what they reach. Only writes use the secret key, because their Concert facts come from the source
here, and the owner is always the verified token's subject.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from pydantic import BaseModel, SecretStr

from concert_scout.models import Concert
from concert_scout.sources.http import USER_AGENT

AUDIENCE = "authenticated"
ALGORITHMS = ["ES256", "RS256"]
KEYS_TTL = 600.0
# A token signed by a new key refetches the key set, but no more often than this.
REFETCH_GAP = 30.0
TABLE = "/rest/v1/saved_concerts"


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
