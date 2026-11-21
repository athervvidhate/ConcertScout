"""Alerts: one daily email per Account about new Concerts by its Followed Artists and Venues,
and upcoming sales for its Saved Concerts (ADR 0006, Issue #88).

The run matches Lineup names and sale windows in code and reads every fact from the source record.
It never calls a model.
"""

import datetime as dt
import hmac
import logging
import secrets
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Query, Response
from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import BaseModel, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import clock, pool
from concert_scout.models import Concert, Place, Price
from concert_scout.names import normalize
from concert_scout.pipeline import Services
from concert_scout.security import Refused
from concert_scout.sources import resend, supabase, ticketmaster, venues
from concert_scout.sources.supabase import AlertAccount, FollowedArtist, FollowedVenue

logger = logging.getLogger(__name__)

LOCK = "alerts:lock"
RUN_SECONDS = 240
# Resend's free plan sends 100 emails a day, shared with sign-in mail, so Alerts stop well short.
DAILY_EMAILS = 60
# How far ahead an Alert looks, the same as a Search with no dates.
WINDOW = dt.timedelta(days=183)
# How far ahead a Saved Concert sale reminder looks.
SALE_REMINDER_WINDOW = dt.timedelta(hours=36)
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


def _matches_venue(concert: Concert, venue_keys: set[str]) -> bool:
    if not concert.venue or not venue_keys:
        return False
    return (
        venues.venue_key(concert.venue, concert.city) in venue_keys
        or normalize(concert.venue) in venue_keys
    )


def matching(
    concerts: Sequence[Concert],
    followed: Sequence[FollowedArtist],
    followed_venues: Sequence[FollowedVenue] = (),
) -> list[Concert]:
    """Concerts matching a Followed Artist or Followed Venue, deduplicated and soonest first."""
    artist_keys = {artist.artist_key for artist in followed}
    venue_keys = {venue.venue_key for venue in followed_venues}
    seen: set[str] = set()
    found: list[Concert] = []
    for concert in concerts:
        if concert.id in seen:
            continue
        by_artist = any(normalize(a.name) in artist_keys for a in concert.artists)
        by_venue = _matches_venue(concert, venue_keys)
        if by_artist or by_venue:
            seen.add(concert.id)
            found.append(concert)
    return sorted(found, key=lambda c: (c.date or dt.date.max, c.time or dt.time.min))


def _as_utc(moment: dt.datetime) -> dt.datetime:
    return moment.astimezone(dt.UTC) if moment.tzinfo else moment.replace(tzinfo=dt.UTC)


def _sale_key(kind: Literal["presale", "general"], start: dt.datetime, name: str = "") -> str:
    stamp = _as_utc(start).isoformat()
    if kind == "general":
        return f"general:{stamp}"
    return f"presale:{normalize(name)[:140]}:{stamp}"


@dataclass(frozen=True)
class SaleReminder:
    """One upcoming presale or general sale for a Saved Concert."""

    concert: Concert
    sale_key: str
    sale_label: str
    opens_at: dt.datetime
    is_presale: bool


def next_sale_reminder(
    concert: Concert,
    now: dt.datetime,
    reminded: set[tuple[str, str]],
    window: dt.timedelta = SALE_REMINDER_WINDOW,
) -> SaleReminder | None:
    """The next un-reminded non-VIP presale or general sale opening in (now, now + window]."""
    now_utc = _as_utc(now)
    cutoff = now_utc + window
    if concert.general_sale is not None and _as_utc(concert.general_sale) <= now_utc:
        return None

    candidates: list[SaleReminder] = []
    for presale in concert.presales:
        if ticketmaster.NOT_A_PRESALE.search(presale.name):
            continue
        start = _as_utc(presale.start)
        if not (now_utc < start <= cutoff):
            continue
        key = _sale_key("presale", start, presale.name)
        if (concert.id, key) in reminded:
            continue
        candidates.append(
            SaleReminder(
                concert=concert,
                sale_key=key,
                sale_label=presale.name,
                opens_at=start,
                is_presale=True,
            )
        )

    if concert.general_sale is not None:
        start = _as_utc(concert.general_sale)
        if now_utc < start <= cutoff:
            key = _sale_key("general", start)
            if (concert.id, key) not in reminded:
                candidates.append(
                    SaleReminder(
                        concert=concert,
                        sale_key=key,
                        sale_label="General sale",
                        opens_at=start,
                        is_presale=False,
                    )
                )

    if not candidates:
        return None
    return min(candidates, key=lambda r: (r.opens_at, not r.is_presale, r.sale_label))


def upcoming_sale_reminders(
    saved: Sequence[Concert],
    now: dt.datetime,
    reminded: set[tuple[str, str]],
    window: dt.timedelta = SALE_REMINDER_WINDOW,
) -> list[SaleReminder]:
    """Sale reminders for Saved Concerts, deduplicated by concert ID and soonest sale first."""
    seen: set[str] = set()
    reminders: list[SaleReminder] = []
    for concert in saved:
        if concert.id in seen:
            continue
        reminder = next_sale_reminder(concert, now, reminded, window)
        if reminder is not None:
            seen.add(concert.id)
            reminders.append(reminder)
    return sorted(
        reminders,
        key=lambda r: (r.opens_at, r.concert.date or dt.date.max, r.concert.id),
    )


def _clock(day: dt.date, at: dt.time, zone: str | None) -> str:
    """A day and time on the venue's clock, with the venue's zone when the source gives one."""
    clock_text = f"{at:%I:%M %p}".lstrip("0")
    if zone:
        clock_text = f"{clock_text} {dt.datetime.combine(day, at, ZoneInfo(zone)):%Z}"
    return f"{_day(day)} at {clock_text}"


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


def format_sale_time(moment: dt.datetime, timezone: str) -> str:
    """A sale open time formatted in the Account's chosen IANA time zone."""
    local = _as_utc(moment).astimezone(ZoneInfo(timezone))
    return _clock(local.date(), local.time(), timezone)


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
        lineup=", ".join(a.name for a in concert.artists) or concert.name,
        tickets=concert.url,
        when=when(concert),
        where=", ".join(f for f in (concert.venue, concert.city, concert.region) if f) or None,
        price=price(concert.price) if concert.price else None,
        on_sale=on_sale(concert, now),
        image=concert.image,
    )


@dataclass(frozen=True)
class SaleCard:
    """One Saved Concert sale reminder as an Alert shows it."""

    lineup: str
    tickets: str
    when: str | None
    where: str | None
    price: str | None
    sale_notice: str
    image: str | None


def sale_card(reminder: SaleReminder, timezone: str) -> SaleCard:
    concert = reminder.concert
    opens = format_sale_time(reminder.opens_at, timezone)
    return SaleCard(
        lineup=", ".join(a.name for a in concert.artists) or concert.name,
        tickets=concert.url,
        when=when(concert),
        where=", ".join(f for f in (concert.venue, concert.city, concert.region) if f) or None,
        price=price(concert.price) if concert.price else None,
        sale_notice=f"{reminder.sale_label} opens {opens}",
        image=concert.image,
    )


def _concert_who(concert: Concert) -> str:
    return concert.name if concert.festival or not concert.artists else concert.artists[0].name


def subject(
    concerts: Sequence[Concert],
    *,
    has_artists: bool = True,
    has_venues: bool = False,
    sale_reminders: Sequence[SaleReminder] = (),
) -> str:
    if not concerts and sale_reminders:
        if len(sale_reminders) == 1:
            return f"{_concert_who(sale_reminders[0].concert)} goes on sale soon"
        return f"{len(sale_reminders)} Saved Concerts go on sale soon"

    if len(concerts) == 1:
        concert = concerts[0]
        where = f" in {concert.city}" if concert.city else ""
        base = f"{_concert_who(concert)} has a new Concert{where}"
    elif has_artists and has_venues:
        base = f"{len(concerts)} new Concerts from Artists and venues you follow"
    elif has_venues and not has_artists:
        base = f"{len(concerts)} new Concerts at venues you follow"
    else:
        base = f"{len(concerts)} new Concerts from Artists you follow"

    if not sale_reminders:
        return base
    noun = "Saved Concert" if len(sale_reminders) == 1 else "Saved Concerts"
    return f"{base} + {len(sale_reminders)} {noun} on sale soon"


def body(
    cards: Sequence[Card],
    more: int,
    place: Place | None,
    site_url: str,
    unsubscribe_url: str,
    *,
    sale_cards: Sequence[SaleCard] = (),
    more_sales: int = 0,
) -> str:
    """The plain-text part, for mail clients that show no HTML."""
    lines: list[str] = []
    if cards and place is not None:
        intro = (
            f"New Concerts near {place.name} from Artists and venues you follow on Concert Scout."
        )
        lines.extend([intro, ""])
        for shown in cards:
            lines.append(shown.lineup)
            prices = " · ".join(f for f in (shown.price, shown.on_sale) if f) or None
            lines.extend(f for f in (shown.when, shown.where, prices) if f)
            lines.extend([f"Tickets: {shown.tickets}", ""])
        if more:
            lines.extend([f"And {more} more. The next Alert will include them.", ""])

    if sale_cards:
        heading = (
            "Saved Concerts going on sale:"
            if cards
            else "Saved Concerts going on sale soon on Concert Scout."
        )
        lines.extend([heading, ""])
        for shown_sale in sale_cards:
            lines.append(shown_sale.lineup)
            lines.append(shown_sale.sale_notice)
            lines.extend(f for f in (shown_sale.when, shown_sale.where, shown_sale.price) if f)
            lines.extend([f"Tickets: {shown_sale.tickets}", ""])
        if more_sales:
            lines.extend([f"And {more_sales} more Saved Concerts going on sale soon.", ""])

    lines.extend(
        [
            f"Manage your Followed Artists, Followed Venues and Alert place: {site_url}/account",
            f"Stop these emails: {unsubscribe_url}",
        ]
    )
    return "\n".join(lines)


def html(
    title: str,
    cards: Sequence[Card],
    more: int,
    place: Place | None,
    site_url: str,
    unsubscribe_url: str,
    *,
    sale_cards: Sequence[SaleCard] = (),
    more_sales: int = 0,
) -> str:
    """The designed part. It holds the same facts as `body`."""
    if cards and place is not None:
        preview = f"{', '.join(c.lineup for c in cards[:3])}: new Concerts near {place.name}"
    else:
        preview = f"{', '.join(c.lineup for c in sale_cards[:3])}: Saved Concerts going on sale"
    return TEMPLATES.get_template("alert.html").render(
        subject=title,
        preview=preview,
        place=place.name if place else None,
        cards=cards,
        more=more,
        sale_cards=sale_cards,
        more_sales=more_sales,
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
    place: Place | None,
    site_url: str,
    unsubscribe_url: str,
    now: dt.datetime,
    *,
    has_artists: bool = True,
    has_venues: bool = False,
    sale_reminders: Sequence[SaleReminder] = (),
    timezone: str | None = None,
) -> Email:
    """One Alert: at most MAX_CONCERTS_PER_EMAIL Concerts per section, the rest counted for next."""
    shown = concerts[:MAX_CONCERTS_PER_EMAIL]
    cards = [card(c, now) for c in shown]
    more = len(concerts) - len(shown)

    shown_sales = sale_reminders[:MAX_CONCERTS_PER_EMAIL]
    zone = timezone or "UTC"
    sale_cards = [sale_card(r, zone) for r in shown_sales]
    more_sales = len(sale_reminders) - len(shown_sales)

    title = subject(
        shown,
        has_artists=has_artists,
        has_venues=has_venues,
        sale_reminders=shown_sales,
    )
    return Email(
        subject=title,
        text=body(
            cards,
            more,
            place,
            site_url,
            unsubscribe_url,
            sale_cards=sale_cards,
            more_sales=more_sales,
        ),
        html=html(
            title,
            cards,
            more,
            place,
            site_url,
            unsubscribe_url,
            sale_cards=sale_cards,
            more_sales=more_sales,
        ),
    )


@dataclass
class PendingAlert:
    """Everything gathered for one Account before sending its single daily Alert email."""

    account: AlertAccount
    new_concerts: list[Concert] = field(default_factory=list[Concert])
    has_artists: bool = False
    has_venues: bool = False
    sale_reminders: list[SaleReminder] = field(default_factory=list[SaleReminder])

    @property
    def has_content(self) -> bool:
        return bool(self.new_concerts or self.sale_reminders)


def _groups(
    accounts: Sequence[AlertAccount],
) -> dict[tuple[float, float, int | None], list[AlertAccount]]:
    """Accounts sharing an Alert place share one pool."""
    groups: dict[tuple[float, float, int | None], list[AlertAccount]] = {}
    for account in accounts:
        p = account.place
        if p is None:
            continue
        groups.setdefault((round(p.lat, 2), round(p.lon, 2), p.radius_miles), []).append(account)
    return groups


async def _collect_followed(
    services: Services,
    accounts_client: httpx.AsyncClient,
    secret_key: SecretStr,
    accounts: Sequence[AlertAccount],
    pending: dict[str, PendingAlert],
    now: dt.datetime,
    deadline: float,
) -> int:
    """Populate `pending` with new Concerts from Followed Artists and Followed Venues."""
    follow_accounts = [a for a in accounts if a.enabled and a.place is not None]
    if not follow_accounts:
        return 0
    ids = [a.user_id for a in follow_accounts]
    followed = await supabase.followed_by(accounts_client, secret_key, ids)
    followed_venues = await supabase.followed_venues_by(accounts_client, secret_key, ids)
    sent = await supabase.sent_to(accounts_client, secret_key, ids)
    eligible = [
        a for a in follow_accounts if followed.get(a.user_id) or followed_venues.get(a.user_id)
    ]
    places = 0
    for group in _groups(eligible).values():
        if time.monotonic() > deadline:
            break
        assert group[0].place is not None
        names = list({f.name: None for a in group for f in followed.get(a.user_id, [])})
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
        places += 1
        for account in group:
            told = sent.get(account.user_id, set())
            artists = followed.get(account.user_id, [])
            account_venues = followed_venues.get(account.user_id, [])
            new = [c for c in matching(concerts, artists, account_venues) if c.id not in told]
            if not new:
                continue
            artist_keys = {a.artist_key for a in artists}
            venue_keys = {v.venue_key for v in account_venues}
            digest = pending[account.user_id]
            digest.new_concerts = new
            digest.has_artists = any(
                any(normalize(a.name) in artist_keys for a in c.artists) for c in new
            )
            digest.has_venues = any(_matches_venue(c, venue_keys) for c in new)
    return places


async def _collect_sale_reminders(
    accounts_client: httpx.AsyncClient,
    secret_key: SecretStr,
    accounts: Sequence[AlertAccount],
    pending: dict[str, PendingAlert],
    now: dt.datetime,
) -> None:
    """Populate `pending` with upcoming sale reminders for Saved Concerts."""
    reminder_accounts = [
        a
        for a in accounts
        if a.sale_reminders_enabled and a.timezone and clock.known_zone(a.timezone) is not None
    ]
    if not reminder_accounts:
        return
    ids = [a.user_id for a in reminder_accounts]
    saved = await supabase.saved_concerts_by(accounts_client, secret_key, ids)
    reminded = await supabase.sale_reminders_sent_to(accounts_client, secret_key, ids)
    for account in reminder_accounts:
        reminders = upcoming_sale_reminders(
            saved.get(account.user_id, []),
            now,
            reminded.get(account.user_id, set()),
        )
        if reminders:
            pending[account.user_id].sale_reminders = reminders


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
        outcome.accounts = len(accounts)
        pending = {a.user_id: PendingAlert(account=a) for a in accounts}
        outcome.places = await _collect_followed(
            services, accounts_client, secret_key, accounts, pending, now, deadline
        )
        await _collect_sale_reminders(accounts_client, secret_key, accounts, pending, now)
        for account in accounts:
            if time.monotonic() > deadline or outcome.sent >= DAILY_EMAILS:
                break
            digest = pending[account.user_id]
            if digest.has_content and await _send(
                accounts_client,
                secret_key,
                mail,
                digest,
                site_url,
                api_url,
                now,
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
    digest: PendingAlert,
    site_url: str,
    api_url: str,
    now: dt.datetime,
) -> bool:
    account = digest.account
    shown_concerts = digest.new_concerts[:MAX_CONCERTS_PER_EMAIL]
    shown_reminders = digest.sale_reminders[:MAX_CONCERTS_PER_EMAIL]
    try:
        address = await supabase.email_of(accounts_client, secret_key, account.user_id)
        if not address:
            return False
        query = urlencode(
            {"account": account.user_id, "token": unsubscribe_token(secret_key, account.user_id)}
        )
        one_click = f"{api_url}/alerts/unsubscribe?{query}"
        alert = email(
            digest.new_concerts,
            account.place,
            site_url,
            f"{site_url}/unsubscribe?{query}",
            now,
            has_artists=digest.has_artists,
            has_venues=digest.has_venues,
            sale_reminders=digest.sale_reminders,
            timezone=account.timezone,
        )
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
        if shown_concerts:
            await supabase.record_sent(
                accounts_client, secret_key, account.user_id, [c.id for c in shown_concerts]
            )
        if shown_reminders:
            await supabase.record_sale_reminders_sent(
                accounts_client,
                secret_key,
                account.user_id,
                [(r.concert.id, r.sale_key) for r in shown_reminders],
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
            await supabase.disable_all_alerts(accounts_client, secret_key, account)
        except supabase.SupabaseError as exc:
            logger.warning("Unsubscribe failed: %s", exc)
            raise Refused(
                503, "accounts_unavailable", "That did not work. Try again soon."
            ) from None
        return Response(status_code=204)

    return routes
