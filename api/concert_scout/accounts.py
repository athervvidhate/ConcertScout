"""Account routes: the signed-in person's Saved Concerts, and deleting the account.

The owner of every operation is the verified access token's subject. No route accepts an
account ID from the browser.
"""

import asyncio
import logging
import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, Path, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import limits, pool, security
from concert_scout.config import Settings
from concert_scout.models import Concert
from concert_scout.security import Refused
from concert_scout.sources import supabase
from concert_scout.sources.supabase import Account, SavedConcert

logger = logging.getLogger(__name__)

PREFIX = "/account"
MAX_IMPORT = 100
# Ticketmaster allows a few calls a second, and the shared limiter spaces them anyway.
IMPORT_CONCURRENCY = 4
# Deleting an account asks for a sign-in this recent, so an unattended device cannot do it.
RECENT_SIGN_IN = 10 * 60

ConcertId = Annotated[str, Path(pattern=r"^[A-Za-z0-9._:-]{1,100}$")]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class SaveRequest(BaseModel):
    reason: Reason | None = None


class GuestSave(BaseModel):
    concert_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,100}$")]
    reason: Reason | None = None


class ImportRequest(BaseModel):
    saves: Annotated[list[GuestSave], Field(max_length=MAX_IMPORT)]


class Imported(BaseModel):
    saved: list[SavedConcert]
    # Saves the source no longer has, or could not confirm. They stay on the device.
    failed: list[str]


def unavailable() -> Refused:
    return Refused(503, "accounts_unavailable", "Accounts are unavailable. Try again soon.")


def router(
    settings: Settings,
    client: httpx.AsyncClient,
    redis: Redis,
    ticketmaster: httpx.AsyncClient,
) -> APIRouter:
    assert settings.supabase_publishable_key and settings.supabase_secret_key
    publishable, secret = settings.supabase_publishable_key, settings.supabase_secret_key
    verifier = supabase.Verifier(client)
    routes = APIRouter(prefix=PREFIX)

    async def current_account(authorization: Annotated[str, Header()] = "") -> Account:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise Refused(401, "sign_in", "Sign in to use your account.")
        try:
            return await verifier.verify(token)
        except supabase.InvalidToken:
            raise Refused(401, "sign_in", "Your sign-in has expired. Sign in again.") from None
        except supabase.SupabaseError as exc:
            logger.warning("Token check failed: %s", exc)
            raise unavailable() from None

    async def limit(request: Request) -> None:
        """Saves cost Ticketmaster calls, never model spend, so a Redis outage lets them through."""
        ip = security.client_ip(request, settings.client_ip_header)
        try:
            await limits.visitor_call(redis, "saved", ip, limits.SAVES_PER_HOUR)
        except limits.VisitorLimitReached as exc:
            message = "That is a lot of saving. Try again soon."
            raise Refused(429, "visitor_limit", message, exc.retry_after) from None
        except RedisError as exc:
            logger.warning("Visitor limit failed: %s", type(exc).__name__)

    async def source_facts(concert_id: str) -> Concert:
        try:
            return await pool.find_concert(ticketmaster, redis, concert_id)
        except pool.ConcertNotFound:
            message = "Its source no longer lists that Concert."
            raise Refused(404, "concert_not_found", message) from None
        except pool.SourceUnavailable as exc:
            logger.warning("Saved Concert lookup failed: %s", exc)
            message = "That Concert's source is not answering. Try saving again soon."
            raise Refused(503, "source_unavailable", message) from None

    @routes.get("/saved", response_model_exclude_none=True)
    async def list_saved(
        account: Annotated[Account, Depends(current_account)],
    ) -> list[SavedConcert]:
        try:
            return await supabase.list_saved(client, publishable, account)
        except supabase.SupabaseError as exc:
            logger.warning("Saved Concerts read failed: %s", exc)
            raise unavailable() from None

    @routes.put(
        "/saved/{concert_id}", dependencies=[Depends(limit)], response_model_exclude_none=True
    )
    async def save(
        concert_id: ConcertId,
        body: SaveRequest,
        account: Annotated[Account, Depends(current_account)],
    ) -> SavedConcert:
        concert = await source_facts(concert_id)
        try:
            await supabase.save(client, secret, account, [(concert, body.reason)])
        except supabase.SupabaseError as exc:
            logger.warning("Saved Concert write failed: %s", exc)
            raise unavailable() from None
        return SavedConcert(concert=concert, reason=body.reason)

    @routes.delete("/saved/{concert_id}", status_code=204)
    async def remove(
        concert_id: ConcertId, account: Annotated[Account, Depends(current_account)]
    ) -> Response:
        try:
            await supabase.remove_saved(client, publishable, account, concert_id)
        except supabase.SupabaseError as exc:
            logger.warning("Saved Concert removal failed: %s", exc)
            raise unavailable() from None
        return Response(status_code=204)

    @routes.post("/saved/import", dependencies=[Depends(limit)], response_model_exclude_none=True)
    async def import_saves(
        body: ImportRequest, account: Annotated[Account, Depends(current_account)]
    ) -> Imported:
        """Moves a device's guest saves in at sign-in. Importing them again changes nothing."""
        gate = asyncio.Semaphore(IMPORT_CONCURRENCY)
        unique = {save.concert_id: save for save in body.saves}

        async def look_up(save: GuestSave) -> SavedConcert | None:
            async with gate:
                try:
                    concert = await pool.find_concert(ticketmaster, redis, save.concert_id)
                except (pool.ConcertNotFound, pool.SourceUnavailable):
                    return None
            return SavedConcert(concert=concert, reason=save.reason)

        found = await asyncio.gather(*(look_up(save) for save in unique.values()))
        saved = [s for s in found if s]
        if saved:
            try:
                pairs = [(s.concert, s.reason) for s in saved]
                await supabase.save(client, secret, account, pairs)
            except supabase.SupabaseError as exc:
                logger.warning("Saved Concert import failed: %s", exc)
                raise unavailable() from None
        kept = {s.concert.id for s in saved}
        return Imported(saved=saved, failed=[i for i in unique if i not in kept])

    @routes.delete("", status_code=204)
    async def delete_account(account: Annotated[Account, Depends(current_account)]) -> Response:
        if time.time() - account.authenticated_at > RECENT_SIGN_IN:
            message = "Sign in again to delete your account."
            raise Refused(403, "sign_in_again", message)
        try:
            await supabase.delete_user(client, secret, account)
        except supabase.SupabaseError as exc:
            logger.warning("Account deletion failed: %s", exc)
            raise unavailable() from None
        return Response(status_code=204)

    return routes
