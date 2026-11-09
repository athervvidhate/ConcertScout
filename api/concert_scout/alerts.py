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
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Query, Response
from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import pool
from concert_scout.models import Concert, Place, Price
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
# Listing names come from outside sources, so every value is escaped into the HTML.
TEMPLATES = Environment(loader=PackageLoader("concert_scout"), autoescape=select_autoescape())


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


def _clock(day: dt.date, at: dt.time, zone: str | None) -> str:
    """A day and time on the venue's clock, with the venue's zone when the source gives one."""
    clock = f"{at:%I:%M %p}".lstrip("0")
    if zone:
        clock = f"{clock} {dt.datetime.combine(day, at, ZoneInfo(zone)):%Z}"
    return f"{_day(day)} at {clock}"


def _day(day: dt.date) -> str:
    return f"{day:%a, %b} {day.day}, {day.year}"


def when(concert: Concert) -> str | None:
    """The date and time on the venue's clock, with the venue's zone. A missing time stays out."""
    if not concert.date:
        return None
    if not concert.time:
        return _day(concert.date)
    return _clock(concert.date, concert.time, concert.time_zone)


def price(value: Price) -> str:
    """The source's price range. Whole amounts drop their cents; a real price keeps them."""
    whole = value.min.is_integer() and value.max.is_integer()

    def amount(number: float) -> str:
        shown = f"{number:,.0f}" if whole else f"{number:,.2f}"
        return f"${shown}" if value.currency == "USD" else f"{shown} {value.currency}"

    low, high = amount(value.min), amount(value.max)
    return low if low == high else f"{low} to {high}"


def on_sale(concert: Concert, now: dt.datetime) -> str | None:
    """When general sale opens, while it is still ahead. Without the venue's zone it stays out,
    since its day could read wrong."""
    sale, zone = concert.general_sale, concert.time_zone
    if not sale or not zone or sale <= now:
        return None
    there = sale.astimezone(ZoneInfo(zone))
    return f"On sale {_clock(there.date(), there.time(), zone)}"


@dataclass(frozen=True)
class Card:
    """One Concert as an Alert shows it. Every value is the source's or left out."""

    lineup: str
    tickets: str
    when: str | None
    where: str | None
    price: str | None
    on_sale: str | None
    image: str | None


def card(concert: Concert, now: dt.datetime) -> Card:
    return Card(
        lineup=", ".join(a.name for a in concert.artists),
        tickets=concert.url,
        when=when(concert),
        where=", ".join(f for f in (concert.venue, concert.city, concert.region) if f) or None,
        price=price(concert.price) if concert.price else None,
        on_sale=on_sale(concert, now),
        image=concert.image,
    )


def subject(concerts: Sequence[Concert]) -> str:
    if len(concerts) == 1:
        concert = concerts[0]
        where = f" in {concert.city}" if concert.city else ""
        return f"{concert.artists[0].name} has a new Concert{where}"
    return f"{len(concerts)} new Concerts from Artists you follow"


def body(
    cards: Sequence[Card], more: int, place: Place, site_url: str, unsubscribe_url: str
) -> str:
    """The plain-text part, for mail clients that show no HTML."""
    lines = [f"New Concerts near {place.name} from Artists you follow on Concert Scout.", ""]
    for shown in cards:
        lines.append(shown.lineup)
        prices = " · ".join(f for f in (shown.price, shown.on_sale) if f) or None
        lines.extend(f for f in (shown.when, shown.where, prices) if f)
        lines.extend([f"Tickets: {shown.tickets}", ""])
    if more:
        lines.extend([f"And {more} more. The next Alert will include them.", ""])
    lines.extend(
        [
            f"Manage your Followed Artists and Alert place: {site_url}/account",
            f"Stop these emails: {unsubscribe_url}",
        ]
    )
    return "\n".join(lines)


def html(
    title: str, cards: Sequence[Card], more: int, place: Place, site_url: str, unsubscribe_url: str
) -> str:
    """The designed part. It holds the same facts as `body`."""
    return TEMPLATES.get_template("alert.html").render(
        subject=title,
        preview=f"{', '.join(c.lineup for c in cards[:3])}: new Concerts near {place.name}",
        place=place.name,
        cards=cards,
        more=more,
        site_url=site_url,
        unsubscribe_url=unsubscribe_url,
    )


@dataclass(frozen=True)
class Email:
    subject: str
    text: str
    html: str


def email(
    concerts: Sequence[Concert],
    place: Place,
    site_url: str,
    unsubscribe_url: str,
    now: dt.datetime,
) -> Email:
    """One Alert: at most MAX_CONCERTS_PER_EMAIL Concerts, the rest counted for the next one."""
    shown = concerts[:MAX_CONCERTS_PER_EMAIL]
    cards = [card(c, now) for c in shown]
    more = len(concerts) - len(shown)
    title = subject(shown)
    return Email(
        subject=title,
        text=body(cards, more, place, site_url, unsubscribe_url),
        html=html(title, cards, more, place, site_url, unsubscribe_url),
    )


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
                    services.musicbrainz,
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
        alert = email(concerts, account.place, site_url, f"{site_url}/unsubscribe?{query}", now)
        await resend.send(
            mail,
            address,
            alert.subject,
            alert.text,
            html=alert.html,
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
