"""Alerts: one daily email per Account about new Concerts by its Followed Artists (ADR 0006).

The run matches Lineup names in code and reads every fact from the source record. It never calls
a model.
"""

import datetime as dt
import hmac
import logging
import secrets
import time
from collections.abc import Sequence
from typing import Annotated
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import pool
from concert_scout.models import Concert, Place
from concert_scout.names import normalize
from concert_scout.pipeline import Services
from concert_scout.security import Refused
from concert_scout.sources import resend, supabase
from concert_scout.sources.supabase import AlertAccount, FollowedArtist

logger = logging.getLogger(__name__)

LOCK = "alerts:lock"
RUN_SECONDS = 240
# Resend's free plan sends 100 emails a day, shared with sign-in mail, so Alerts stop well short.
DAILY_EMAILS = 60
# How far ahead an Alert looks, the same as a Search with no dates.
WINDOW = dt.timedelta(days=183)
MAX_CONCERTS_PER_EMAIL = 20
PURPOSE = b"alert-unsubscribe:"


class Outcome(BaseModel):
    accounts: int = 0
    places: int = 0
    sent: int = 0
    error: str | None = None


def unsubscribe_token(key: SecretStr, user_id: str) -> str:
    return hmac.new(
        key.get_secret_value().encode(), PURPOSE + user_id.encode(), "sha256"
    ).hexdigest()


def valid_token(key: SecretStr, user_id: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(key, user_id), token)


def matching(concerts: Sequence[Concert], followed: Sequence[FollowedArtist]) -> list[Concert]:
    """Concerts whose source Lineup names a Followed Artist, soonest first."""
    keys = {artist.artist_key for artist in followed}
    found = [c for c in concerts if any(normalize(a.name) in keys for a in c.artists)]
    return sorted(found, key=lambda c: (c.date or dt.date.max, c.time or dt.time.min))


def when(concert: Concert) -> str | None:
    """The date and time on the venue's clock, with the venue's zone. A missing time stays out."""
    if not concert.date:
        return None
    day = f"{concert.date:%a, %b} {concert.date.day}, {concert.date.year}"
    if not concert.time:
        return day
    clock = f"{concert.time:%I:%M %p}".lstrip("0")
    if concert.time_zone:
        zone = dt.datetime.combine(concert.date, concert.time, ZoneInfo(concert.time_zone))
        clock = f"{clock} {zone:%Z}"
    return f"{day} at {clock}"


def subject(concerts: Sequence[Concert]) -> str:
    if len(concerts) == 1:
        concert = concerts[0]
        where = f" in {concert.city}" if concert.city else ""
        return f"{concert.artists[0].name} has a new Concert{where}"
    return f"{len(concerts)} new Concerts from Artists you follow"


def body(concerts: Sequence[Concert], place: Place, site_url: str, unsubscribe_url: str) -> str:
    lines = [f"New Concerts near {place.name} from Artists you follow on Concert Scout.", ""]
    for concert in concerts[:MAX_CONCERTS_PER_EMAIL]:
        lines.append(", ".join(a.name for a in concert.artists))
        lines.extend(
            fact
            for fact in (
                when(concert),
                ", ".join(f for f in (concert.venue, concert.city, concert.region) if f) or None,
                f"Tickets: {concert.url}",
            )
            if fact
        )
        lines.append("")
    if len(concerts) > MAX_CONCERTS_PER_EMAIL:
        more = len(concerts) - MAX_CONCERTS_PER_EMAIL
        lines.extend([f"And {more} more. The next Alert will include them.", ""])
    lines.extend(
        [
            f"Manage your Followed Artists and Alert place: {site_url}/account",
            f"Stop these emails: {unsubscribe_url}",
        ]
    )
    return "\n".join(lines)


def _groups(
    accounts: Sequence[AlertAccount],
) -> dict[tuple[float, float, int | None], list[AlertAccount]]:
    """Accounts sharing an Alert place share one pool."""
    groups: dict[tuple[float, float, int | None], list[AlertAccount]] = {}
    for account in accounts:
        p = account.place
        groups.setdefault((round(p.lat, 2), round(p.lon, 2), p.radius_miles), []).append(account)
    return groups


async def run(
    services: Services,
    accounts_client: httpx.AsyncClient,
    secret_key: SecretStr,
    mail: httpx.AsyncClient,
    site_url: str,
    api_url: str,
    now: dt.datetime,
) -> Outcome:
    """One locked run. A failure for one place or Account skips it until tomorrow."""
    deadline = time.monotonic() + RUN_SECONDS
    token = secrets.token_hex(16)
    try:
        if not await services.redis.set(LOCK, token, nx=True, ex=RUN_SECONDS + 60):
            return Outcome(error="alerts already running")
    except RedisError:
        return Outcome(error="cache unavailable")
    outcome = Outcome()
    try:
        accounts = await supabase.accounts_with_alerts(accounts_client, secret_key)
        ids = [a.user_id for a in accounts]
        followed = await supabase.followed_by(accounts_client, secret_key, ids)
        sent = await supabase.sent_to(accounts_client, secret_key, ids)
        outcome.accounts = len(accounts)
        for group in _groups([a for a in accounts if followed.get(a.user_id)]).values():
            if time.monotonic() > deadline or outcome.sent >= DAILY_EMAILS:
                break
            names = list({f.name: None for a in group for f in followed[a.user_id]})
            try:
                concerts = await pool.find_concerts(
                    services.ticketmaster,
                    services.redis,
                    group[0].place,
                    names,
                    None,
                    now.date() + WINDOW,
                    now,
                )
            except (httpx.HTTPError, pool.SourceUnavailable) as exc:
                logger.warning("Alert pool failed: %s", type(exc).__name__)
                continue
            outcome.places += 1
            for account in group:
                if outcome.sent >= DAILY_EMAILS:
                    break
                told = sent.get(account.user_id, set())
                new = [c for c in matching(concerts, followed[account.user_id]) if c.id not in told]
                if new and await _send(
                    accounts_client, secret_key, mail, account, new, site_url, api_url, now
                ):
                    outcome.sent += 1
    except supabase.SupabaseError as exc:
        outcome.error = str(exc)
    finally:
        await _release(services.redis, token)
    logger.info("Alerts %s", outcome.model_dump_json(exclude_defaults=True))
    return outcome


async def _send(
    accounts_client: httpx.AsyncClient,
    secret_key: SecretStr,
    mail: httpx.AsyncClient,
    account: AlertAccount,
    concerts: list[Concert],
    site_url: str,
    api_url: str,
    now: dt.datetime,
) -> bool:
    shown = concerts[:MAX_CONCERTS_PER_EMAIL]
    try:
        address = await supabase.email_of(accounts_client, secret_key, account.user_id)
        if not address:
            return False
        query = urlencode(
            {"account": account.user_id, "token": unsubscribe_token(secret_key, account.user_id)}
        )
        one_click = f"{api_url}/alerts/unsubscribe?{query}"
        await resend.send(
            mail,
            address,
            subject(shown),
            body(concerts, account.place, site_url, f"{site_url}/unsubscribe?{query}"),
            sender=resend.ALERT_SENDER,
            headers={
                "List-Unsubscribe": f"<{one_click}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
            # A retried run the same day cannot send this Account a second email.
            idempotency_key=f"alert-{account.user_id}-{now.date()}",
        )
        # Recorded only once Resend has the email, so a failed send loses nothing.
        await supabase.record_sent(
            accounts_client, secret_key, account.user_id, [c.id for c in shown]
        )
    except (supabase.SupabaseError, resend.ResendError) as exc:
        logger.warning("Alert for one Account failed: %s", exc)
        return False
    return True


async def _release(redis: Redis, token: str) -> None:
    try:
        async with redis.pipeline() as pipe:
            await pipe.watch(LOCK)
            if await pipe.get(LOCK) == token.encode():
                pipe.multi()
                pipe.delete(LOCK)
                await pipe.execute()
    except RedisError:
        pass


def router(accounts_client: httpx.AsyncClient, secret_key: SecretStr) -> APIRouter:
    """Stopping Alerts without a sign-in, so the signed token is the only proof."""
    routes = APIRouter(prefix="/alerts")

    # The email's link opens a page whose button posts here, and mail apps post here directly for
    # one-click unsubscribe (RFC 8058). Opening a link alone changes nothing, because mail
    # scanners open links.
    @routes.post("/unsubscribe", status_code=204)
    async def unsubscribe(
        account: Annotated[str, Query(max_length=64)], token: Annotated[str, Query(max_length=64)]
    ) -> Response:
        if not valid_token(secret_key, account, token):
            raise Refused(403, "unsubscribe_link", "This link is not valid.")
        try:
            await supabase.set_alerts_enabled(accounts_client, secret_key, account, False)
        except supabase.SupabaseError as exc:
            logger.warning("Unsubscribe failed: %s", exc)
            raise Refused(
                503, "accounts_unavailable", "That did not work. Try again soon."
            ) from None
        return Response(status_code=204)

    return routes
