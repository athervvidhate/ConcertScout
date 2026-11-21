"""Supabase: who a request belongs to, and what is stored under that account: Saved Concerts,
Followed Artists and Alert settings.

Reads and removals run with the person's own access token, so the database's row policies decide
what they reach. Only writes use the secret key, because their Concert facts come from the source
here, and the owner is always the verified token's subject.
"""

import datetime as dt
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from pydantic import BaseModel, SecretStr, field_validator

from concert_scout.models import Concert, Place, Reading
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
FOLLOWED_VENUES = "/rest/v1/followed_venues"
SETTINGS = "/rest/v1/alert_settings"
SENT = "/rest/v1/alerts_sent"
SALE_REMINDERS_SENT = "/rest/v1/sale_reminders_sent"
SAVED_SEARCHES = "/rest/v1/saved_searches"
SAVED_SEARCH_SENT = "/rest/v1/saved_search_sent"
TASTE = "/rest/v1/taste_profiles"
COBILLING_RECORD = "/rest/v1/rpc/record_cobilling_bills"
COBILLING_NEIGHBORS = "/rest/v1/rpc/cobilling_neighbors"
EMBEDDINGS_UPSERT = "/rest/v1/rpc/upsert_artist_embeddings"
EMBEDDING_STATE = "/rest/v1/rpc/artist_embedding_state"
EMBEDDINGS_FOR = "/rest/v1/rpc/artist_embeddings_for"
SEMANTIC_SCORES = "/rest/v1/rpc/semantic_scores"


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


# Where a synced Taste came from. Spotify's own account data is never one of them (ADR 0003).
type TasteSource = Literal[
    "seed",
    "csv",
    "exportify",
    "tunemymusic",
    "youtube",
    "lastfm",
    "listenbrainz",
    "history",
    "list",
]


class TasteProfile(BaseModel):
    """An Account's Taste: Artist names, favourites first, the sources they came from, newest
    first, and when it was last saved."""

    sources: list[TasteSource]
    artists: list[str]
    updated_at: dt.datetime


class FollowedVenue(BaseModel):
    venue_key: str
    name: str
    city: str | None = None
    lat: float | None = None
    lon: float | None = None


class AlertSettings(BaseModel):
    place: Place | None = None
    enabled: bool = False
    sale_reminders_enabled: bool = False
    saved_searches_paused: bool = False
    timezone: str | None = None


class AlertAccount(BaseModel):
    """An Account with Alerts on, as the daily run reads it."""

    user_id: str
    place: Place | None = None
    enabled: bool = True
    sale_reminders_enabled: bool = False
    saved_searches_paused: bool = False
    timezone: str | None = None


class SavedSearch(BaseModel):
    """A Search an Account kept to rerun weekly (Issue #89)."""

    id: str
    query_text: str
    reading: Reading
    last_run_at: dt.datetime | None = None
    created_at: dt.datetime


class DueSavedSearch(SavedSearch):
    """A Saved Search ready for its weekly rerun, with its owning Account ID."""

    user_id: str


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


async def list_followed_venues(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> list[FollowedVenue]:
    request = client.build_request(
        "GET",
        FOLLOWED_VENUES,
        params={"select": "venue_key,name,city,lat,lon", "order": "followed_at.asc"},
        headers=_as_person(account, publishable_key),
    )
    return _rows(await _send(client, request), FollowedVenue)


async def follow_venue(
    client: httpx.AsyncClient, secret_key: SecretStr, account: Account, venue: FollowedVenue
) -> None:
    """Following a venue again keeps the first follow and its spelling."""
    request = client.build_request(
        "POST",
        FOLLOWED_VENUES,
        params={"on_conflict": "user_id,venue_key"},
        json=[{"user_id": account.id} | venue.model_dump()],
        headers=_as_server(secret_key) | {"Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    await _send(client, request)


async def unfollow_venue(
    client: httpx.AsyncClient, publishable_key: str, account: Account, venue_key: str
) -> None:
    request = client.build_request(
        "DELETE",
        FOLLOWED_VENUES,
        params={"venue_key": f"eq.{venue_key}"},
        headers=_as_person(account, publishable_key),
    )
    await _send(client, request)


async def alert_settings(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> AlertSettings:
    request = client.build_request(
        "GET",
        SETTINGS,
        params={"select": "place,enabled,sale_reminders_enabled,saved_searches_paused,timezone"},
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


async def set_sale_reminders(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    user_id: str,
    enabled: bool,
    timezone: str | None,
) -> None:
    """Creates the Account's settings row if needed, or updates only sale reminder fields."""
    row: dict[str, Any] = {
        "user_id": user_id,
        "sale_reminders_enabled": enabled,
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    if timezone is not None:
        row["timezone"] = timezone
    request = client.build_request(
        "POST",
        SETTINGS,
        params={"on_conflict": "user_id"},
        json=[row],
        headers=_as_server(secret_key)
        | {"Prefer": "resolution=merge-duplicates,return=minimal,missing=default"},
    )
    await _send(client, request)


async def disable_all_alerts(
    client: httpx.AsyncClient, secret_key: SecretStr, user_id: str
) -> None:
    """Turns off all Alert emails (including Saved Search reruns) for an Account."""
    row = {
        "user_id": user_id,
        "enabled": False,
        "sale_reminders_enabled": False,
        "saved_searches_paused": True,
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


async def get_taste(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> TasteProfile | None:
    request = client.build_request(
        "GET",
        TASTE,
        params={"select": "sources,artists,updated_at"},
        headers=_as_person(account, publishable_key),
    )
    rows = _rows(await _send(client, request), TasteProfile)
    return rows[0] if rows else None


async def put_taste(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    account: Account,
    sources: list[TasteSource],
    artists: list[str],
) -> TasteProfile:
    """Replaces the Account's Taste. Its `updated_at` is the moment of this write."""
    row = {
        "user_id": account.id,
        "sources": sources,
        "artists": artists,
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    request = client.build_request(
        "POST",
        TASTE,
        params={"on_conflict": "user_id"},
        json=[row],
        headers=_as_server(secret_key)
        | {"Prefer": "resolution=merge-duplicates,return=representation"},
    )
    saved = _rows(await _send(client, request), TasteProfile)
    if not saved:
        raise SupabaseError("unreadable response: no row")
    return saved[0]


async def delete_taste(client: httpx.AsyncClient, publishable_key: str, account: Account) -> None:
    request = client.build_request(
        "DELETE",
        TASTE,
        params={"user_id": f"eq.{account.id}"},
        headers=_as_person(account, publishable_key),
    )
    await _send(client, request)


async def accounts_with_alerts(
    client: httpx.AsyncClient, secret_key: SecretStr
) -> list[AlertAccount]:
    request = client.build_request(
        "GET",
        SETTINGS,
        params={
            "select": "user_id,place,enabled,sale_reminders_enabled,timezone",
            "or": "(enabled.is.true,sale_reminders_enabled.is.true)",
            "order": "updated_at.asc",
        },
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


async def followed_venues_by(
    client: httpx.AsyncClient, secret_key: SecretStr, user_ids: list[str]
) -> dict[str, list[FollowedVenue]]:
    if not user_ids:
        return {}
    request = client.build_request(
        "GET",
        FOLLOWED_VENUES,
        params={"select": "user_id,venue_key,name,city,lat,lon", "user_id": _among(user_ids)},
        headers=_as_server(secret_key),
    )
    followed: dict[str, list[FollowedVenue]] = {}
    for row in _rows(await _send(client, request), _FollowedVenueRow):
        followed.setdefault(row.user_id, []).append(FollowedVenue(**row.model_dump()))
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
    if not concert_ids:
        return
    request = client.build_request(
        "POST",
        SENT,
        params={"on_conflict": "user_id,concert_id"},
        json=[{"user_id": user_id, "concert_id": c} for c in concert_ids],
        headers=_as_server(secret_key) | {"Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    await _send(client, request)


async def saved_concerts_by(
    client: httpx.AsyncClient, secret_key: SecretStr, user_ids: list[str]
) -> dict[str, list[Concert]]:
    if not user_ids:
        return {}
    request = client.build_request(
        "GET",
        TABLE,
        params={"select": "user_id,concert", "user_id": _among(user_ids)},
        headers=_as_server(secret_key),
    )
    saved: dict[str, list[Concert]] = {}
    for row in _rows(await _send(client, request), _SavedConcertRow):
        saved.setdefault(row.user_id, []).append(row.concert)
    return saved


async def sale_reminders_sent_to(
    client: httpx.AsyncClient, secret_key: SecretStr, user_ids: list[str]
) -> dict[str, set[tuple[str, str]]]:
    if not user_ids:
        return {}
    request = client.build_request(
        "GET",
        SALE_REMINDERS_SENT,
        params={"select": "user_id,concert_id,sale_key", "user_id": _among(user_ids)},
        headers=_as_server(secret_key),
    )
    sent: dict[str, set[tuple[str, str]]] = {}
    for row in _rows(await _send(client, request), _SaleReminderSentRow):
        sent.setdefault(row.user_id, set()).add((row.concert_id, row.sale_key))
    return sent


async def record_sale_reminders_sent(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    user_id: str,
    keys: Sequence[tuple[str, str]],
) -> None:
    if not keys:
        return
    request = client.build_request(
        "POST",
        SALE_REMINDERS_SENT,
        params={"on_conflict": "user_id,concert_id,sale_key"},
        json=[{"user_id": user_id, "concert_id": c, "sale_key": k} for c, k in keys],
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


class _FollowedVenueRow(FollowedVenue):
    user_id: str


class _SentRow(BaseModel):
    user_id: str
    concert_id: str


class _SavedConcertRow(BaseModel):
    user_id: str
    concert: Concert


class _SaleReminderSentRow(BaseModel):
    user_id: str
    concert_id: str
    sale_key: str


class _UserIdRow(BaseModel):
    user_id: str


class _SavedSearchSentRow(BaseModel):
    saved_search_id: str
    concert_id: str


async def list_saved_searches(
    client: httpx.AsyncClient, publishable_key: str, account: Account
) -> list[SavedSearch]:
    request = client.build_request(
        "GET",
        SAVED_SEARCHES,
        params={
            "select": "id,query_text,reading,last_run_at,created_at",
            "order": "created_at.asc",
        },
        headers=_as_person(account, publishable_key),
    )
    return _rows(await _send(client, request), SavedSearch)


async def create_saved_search(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    account: Account,
    query_text: str,
    reading: Reading,
) -> SavedSearch:
    row = {
        "user_id": account.id,
        "query_text": query_text,
        "reading": reading.model_dump(mode="json", exclude_none=True),
    }
    request = client.build_request(
        "POST",
        SAVED_SEARCHES,
        json=[row],
        headers=_as_server(secret_key) | {"Prefer": "return=representation"},
    )
    created = _rows(await _send(client, request), SavedSearch)
    if not created:
        raise SupabaseError("unreadable response: no row")
    return created[0]


async def delete_saved_search(
    client: httpx.AsyncClient, publishable_key: str, account: Account, saved_search_id: str
) -> None:
    request = client.build_request(
        "DELETE",
        SAVED_SEARCHES,
        params={"id": f"eq.{saved_search_id}"},
        headers=_as_person(account, publishable_key),
    )
    await _send(client, request)


async def due_saved_searches(
    client: httpx.AsyncClient, secret_key: SecretStr, cutoff: dt.datetime
) -> list[DueSavedSearch]:
    """Saved Searches that have never run or last ran at or before `cutoff`."""
    stamp = cutoff.astimezone(dt.UTC).isoformat() if cutoff.tzinfo else cutoff.isoformat()
    request = client.build_request(
        "GET",
        SAVED_SEARCHES,
        params={
            "select": "id,user_id,query_text,reading,last_run_at,created_at",
            "or": f"(last_run_at.is.null,last_run_at.lte.{stamp})",
            "order": "last_run_at.asc.nullsfirst,created_at.asc",
        },
        headers=_as_server(secret_key),
    )
    return _rows(await _send(client, request), DueSavedSearch)


async def paused_saved_search_users(
    client: httpx.AsyncClient, secret_key: SecretStr, user_ids: list[str]
) -> set[str]:
    """Account IDs that paused Saved Search Alerts via unsubscribe."""
    if not user_ids:
        return set()
    request = client.build_request(
        "GET",
        SETTINGS,
        params={
            "select": "user_id",
            "saved_searches_paused": "is.true",
            "user_id": _among(user_ids),
        },
        headers=_as_server(secret_key),
    )
    return {row.user_id for row in _rows(await _send(client, request), _UserIdRow)}


async def saved_search_sent_for(
    client: httpx.AsyncClient, secret_key: SecretStr, saved_search_ids: list[str]
) -> dict[str, set[str]]:
    if not saved_search_ids:
        return {}
    request = client.build_request(
        "GET",
        SAVED_SEARCH_SENT,
        params={
            "select": "saved_search_id,concert_id",
            "saved_search_id": _among(saved_search_ids),
        },
        headers=_as_server(secret_key),
    )
    sent: dict[str, set[str]] = {}
    for row in _rows(await _send(client, request), _SavedSearchSentRow):
        sent.setdefault(row.saved_search_id, set()).add(row.concert_id)
    return sent


async def record_saved_search_sent(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    user_id: str,
    pairs: Sequence[tuple[str, str]],
) -> None:
    if not pairs:
        return
    request = client.build_request(
        "POST",
        SAVED_SEARCH_SENT,
        params={"on_conflict": "saved_search_id,concert_id"},
        json=[
            {"user_id": user_id, "saved_search_id": search_id, "concert_id": concert_id}
            for search_id, concert_id in pairs
        ],
        headers=_as_server(secret_key) | {"Prefer": "resolution=ignore-duplicates,return=minimal"},
    )
    await _send(client, request)


async def mark_saved_search_ran(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    saved_search_ids: Sequence[str],
    ran_at: dt.datetime,
) -> None:
    if not saved_search_ids:
        return
    stamp = ran_at.astimezone(dt.UTC).isoformat() if ran_at.tzinfo else ran_at.isoformat()
    request = client.build_request(
        "PATCH",
        SAVED_SEARCHES,
        params={"id": _among(list(saved_search_ids))},
        json={"last_run_at": stamp},
        headers=_as_server(secret_key) | {"Prefer": "return=minimal"},
    )
    await _send(client, request)


class CoBillingBill(BaseModel):
    """One eligible multi-Artist Concert Lineup queued for co-billing accumulation."""

    concert_id: str
    concert_date: dt.date
    weight: float
    artists: list[str]


class CoBillingEdge(BaseModel):
    """One co-billed peer returned for a normalized seed Artist key."""

    seed: str
    peer: str
    weight: float
    shared_shows: int
    last_seen: dt.date


async def record_cobilling_bills(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    bills: Sequence[CoBillingBill],
) -> int:
    """Atomically record unseen Concert bills and accumulate co-billing edge weights."""
    if not bills:
        return 0
    request = client.build_request(
        "POST",
        COBILLING_RECORD,
        json={"p_bills": [bill.model_dump(mode="json") for bill in bills]},
        headers=_as_server(secret_key),
    )
    response = await _send(client, request)
    try:
        recorded = response.json()
        if not isinstance(recorded, int) or isinstance(recorded, bool):
            raise ValueError("expected integer count")
        return recorded
    except ValueError as exc:
        raise SupabaseError(f"unreadable response: {type(exc).__name__}") from None


async def cobilling_neighbors(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    artists: Sequence[str],
    limit: int = 50,
) -> list[CoBillingEdge]:
    """Top co-billed peers for each normalized seed Artist key, strongest first."""
    if not artists:
        return []
    request = client.build_request(
        "POST",
        COBILLING_NEIGHBORS,
        json={"p_artists": list(artists), "p_limit": limit},
        headers=_as_server(secret_key),
    )
    return _rows(await _send(client, request), CoBillingEdge)


class EmbeddingRow(BaseModel):
    """One Artist's vector to store. `card_hash` is the SHA-256 of what the vector came from."""

    artist_key: str
    mbid: str | None = None
    tier: Literal[1, 2]
    card_hash: str
    embedding: list[float]


class EmbeddingState(BaseModel):
    artist_key: str
    tier: Literal[1, 2]
    card_hash: str


class StoredEmbedding(BaseModel):
    artist_key: str
    tier: Literal[1, 2]
    card_hash: str
    embedding: list[float]

    @field_validator("embedding", mode="before")
    @classmethod
    def from_text(cls, value: object) -> object:
        """Postgres sends a vector as the text `[x,y,...]`."""
        return json.loads(value) if isinstance(value, str) else value


class SemanticScore(BaseModel):
    artist_key: str
    cosine: float


async def upsert_embeddings(
    client: httpx.AsyncClient, secret_key: SecretStr, rows: Sequence[EmbeddingRow]
) -> int:
    """Store or replace vectors. Returns how many rows were written."""
    if not rows:
        return 0
    request = client.build_request(
        "POST",
        EMBEDDINGS_UPSERT,
        json={"p_rows": [row.model_dump(mode="json") for row in rows]},
        headers=_as_server(secret_key),
    )
    response = await _send(client, request)
    try:
        written = response.json()
        if not isinstance(written, int) or isinstance(written, bool):
            raise ValueError("expected integer count")
        return written
    except ValueError as exc:
        raise SupabaseError(f"unreadable response: {type(exc).__name__}") from None


async def embedding_states(
    client: httpx.AsyncClient, secret_key: SecretStr, artists: Sequence[str]
) -> list[EmbeddingState]:
    """The tier and card hash already stored for these normalized Artist keys."""
    if not artists:
        return []
    request = client.build_request(
        "POST",
        EMBEDDING_STATE,
        json={"p_artists": list(artists)},
        headers=_as_server(secret_key),
    )
    return _rows(await _send(client, request), EmbeddingState)


async def stored_embeddings(
    client: httpx.AsyncClient, secret_key: SecretStr, artists: Sequence[str]
) -> list[StoredEmbedding]:
    """The stored vectors for these normalized Artist keys."""
    if not artists:
        return []
    request = client.build_request(
        "POST",
        EMBEDDINGS_FOR,
        json={"p_artists": list(artists)},
        headers=_as_server(secret_key),
    )
    return _rows(await _send(client, request), StoredEmbedding)


async def semantic_scores(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    query: Sequence[float],
    artists: Sequence[str],
    floor: float,
) -> list[SemanticScore]:
    """Exact cosine similarity to the query for the Artists among these keys that reach `floor`."""
    if not artists:
        return []
    request = client.build_request(
        "POST",
        SEMANTIC_SCORES,
        json={"p_query": json.dumps(list(query)), "p_artists": list(artists), "p_floor": floor},
        headers=_as_server(secret_key),
    )
    return _rows(await _send(client, request), SemanticScore)
