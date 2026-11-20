"""An Account's synced Taste Profile and the For You shelf.

The Taste Profile is the confirmed Artist names of a Taste, favourites first, kept on the Account
so every device sees it. Spotify account data never reaches it (ADR 0003): the source is one of
the non-Spotify imports, and the table refuses anything else.

For You matches those names to the Concert pool by code alone: exact Lineup names, the closest
similar Artists and Artists who have shared bills with them. It makes no model call (ADR 0002).
"""

import asyncio
import datetime as dt
import logging
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from redis.exceptions import RedisError

from concert_scout import clock, cobilling, limits, matching, pool, security, similarity
from concert_scout.config import Settings
from concert_scout.models import Concert, Name, Place, SeedArtist
from concert_scout.names import normalize
from concert_scout.pipeline import IMPORTED_SEEDS, Services
from concert_scout.security import Refused
from concert_scout.sources import musicbrainz, supabase, ticketmaster
from concert_scout.sources.supabase import Account, TasteProfile, TasteSource

logger = logging.getLogger(__name__)

# Paths whose bad requests are about a Taste or a place, not a Saved Concert.
PATHS = frozenset({"/account/taste", "/account/for-you", "/for-you"})
MAX_TASTE = 100
# The shelf looks this far ahead. A shelf is a glance, so it stays short.
UPCOMING_DAYS = 60
MAX_SHELF = 20
# One tour's dates cannot fill the shelf.
MAX_PER_ARTIST = 3
FOR_YOU_PER_HOUR = 60
SYNC_PER_HOUR = 60

type Signal = Literal["seed", "one_hop", "co_billed"]
# Only these say a Concert suits the Taste. Tags and genres are broader, so they stay out.
SIGNALS: tuple[Signal, ...] = ("seed", "one_hop", "co_billed")

type Turn = Callable[[Request], Awaitable[None]]


class TasteBody(BaseModel):
    source: TasteSource
    artists: Annotated[list[Name], Field(min_length=1, max_length=MAX_TASTE)]


class Near(BaseModel):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class AccountForYouRequest(BaseModel):
    """A place the browser shared. Without one, the Account's Alert place is used."""

    near: Near | None = None
    # The browser's zone, so "today" means the visitor's own day.
    time_zone: Annotated[str, StringConstraints(max_length=64)]


class GuestForYouRequest(BaseModel):
    """A device's own Taste and the place its visitor shared."""

    artists: Annotated[list[Name], Field(min_length=1, max_length=MAX_TASTE)]
    near: Near
    time_zone: Annotated[str, StringConstraints(max_length=64)]


class ForYouConcert(BaseModel):
    """A Concert and the one Artist in its Lineup that suits the Taste. `via` names the Taste's
    own Artist behind it, which is the Artist itself for an exact match."""

    concert: Concert
    artist: str
    signal: Signal
    via: str


class ForYou(BaseModel):
    place: str
    concerts: list[ForYouConcert]


def distinct(names: Sequence[str]) -> list[str]:
    """Each Artist once, under its first spelling, favourites still first."""
    first: dict[str, str] = {}
    for name in names:
        if key := normalize(name):
            first.setdefault(key, name)
    return list(first.values())


def _plain(concert: Concert) -> Concert:
    """The Concert without its genres. A shared genre is not a reason, only a name is."""
    plain = {"genre": None, "subgenre": None}
    artists = [artist.model_copy(update=plain) for artist in concert.artists]
    return concert.model_copy(update={"artists": artists})


async def _seed(name: str, services: Services) -> SeedArtist:
    try:
        return await musicbrainz.resolve(services.musicbrainz, services.redis, name)
    except musicbrainz.MusicBrainzError as exc:
        # The name alone still matches the pool, so a dead MusicBrainz only loses its neighbours.
        logger.warning("MusicBrainz failed: %s", exc)
        return SeedArtist(name=name)


async def _taste(names: Sequence[str], services: Services) -> matching.Taste:
    """Only the favourites get lookups. The rest match the pool by name, as in a Search."""
    top = names[:IMPORTED_SEEDS]
    seeds = await asyncio.gather(*(_seed(name, services) for name in top))
    neighbours = await similarity.find_neighbours(
        services.listenbrainz, services.lastfm, services.redis, seeds, hops=1
    )
    peers = await cobilling.find_peers(services.supabase, services.supabase_secret_key, top)
    rest = [SeedArtist(name=name) for name in names[IMPORTED_SEEDS:]]
    return matching.Taste([*seeds, *rest], neighbours, [], cobilling=peers)


def shelf(
    concerts: Sequence[Concert], taste: matching.Taste, names: Sequence[str]
) -> list[ForYouConcert]:
    """The Concerts whose Lineup suits the Taste. Exact names come first, then the closest
    neighbours and bill-mates. Within a tie the Taste's own order decides, then the date."""
    by_id = {concert.id: concert for concert in concerts}
    rank = {normalize(name): place for place, name in enumerate(names)}
    candidates = matching.score_concerts([_plain(c) for c in concerts], taste, {})
    fits = [c for c in candidates if c.match and c.match.signal in SIGNALS]

    def order(item: matching.Candidate) -> tuple[float, int, dt.date]:
        assert item.match
        first = rank.get(normalize(item.match.via or ""), len(rank))
        return (-item.match.score, first, item.concert.date or dt.date.max)

    kept: list[ForYouConcert] = []
    dates: Counter[str] = Counter()
    for item in sorted(fits, key=order):
        match = item.match
        assert match
        artist = normalize(match.artist)
        if dates[artist] >= MAX_PER_ARTIST:
            continue
        dates[artist] += 1
        kept.append(
            ForYouConcert(
                concert=by_id[item.concert.id],
                artist=match.artist,
                signal=match.signal,  # pyright: ignore[reportArgumentType]
                via=match.via or match.artist,
            )
        )
    return kept[:MAX_SHELF]


async def find_for_you(
    services: Services, artists: Sequence[str], where: Place, time_zone: str
) -> ForYou:
    """Concerts in the next 60 days from the pool near `where`. It spends no model call."""
    names = distinct(artists)
    now = clock.now_in(time_zone)
    last = now.date() + dt.timedelta(days=UPCOMING_DAYS)
    try:
        concerts = await pool.find_concerts(
            services.ticketmaster, services.musicbrainz, services.redis, where, [], None, last, now
        )
    except ticketmaster.TicketmasterError:
        message = "Ticketmaster is not responding. Try again soon."
        raise Refused(503, "ticketmaster_unavailable", message) from None
    except limits.DailyLimitReached as exc:
        message = "We have used today's Ticketmaster allowance. Try again tomorrow."
        raise Refused(429, "ticketmaster_limit", message, exc.retry_after) from None
    taste = await _taste(names, services)
    return ForYou(place=where.name, concerts=shelf(concerts, taste, names))


def _turns(settings: Settings, services: Services) -> Callable[[str, int], Turn]:
    def turn(bucket: str, cap: int) -> Turn:
        async def take(request: Request) -> None:
            """These cost lookups, never model spend, so a Redis outage lets them through."""
            ip = security.client_ip(request, settings.client_ip_header)
            try:
                await limits.visitor_call(services.redis, bucket, ip, cap)
            except limits.VisitorLimitReached as exc:
                message = "That is a lot of lookups. Try again soon."
                raise Refused(429, "visitor_limit", message, exc.retry_after) from None
            except RedisError as exc:
                logger.warning("Visitor limit failed: %s", type(exc).__name__)

        return take

    return turn


def guest_router(settings: Settings, services: Services) -> APIRouter:
    """For a device's own Taste, with no Account. The Taste is not kept."""
    routes = APIRouter()
    turn = _turns(settings, services)("for_you", FOR_YOU_PER_HOUR)

    @routes.post("/for-you", response_model_exclude_none=True)
    async def for_you(request: Request, body: GuestForYouRequest) -> ForYou:
        await turn(request)
        where = Place(name="Near you", lat=body.near.lat, lon=body.near.lon)
        return await find_for_you(services, body.artists, where, body.time_zone)

    return routes


def account_routes(
    settings: Settings,
    client: httpx.AsyncClient,
    services: Services,
    current_account: Callable[..., Awaitable[Account]],
) -> APIRouter:
    """The signed-in person's Taste Profile and shelf, mounted under `/account`."""
    assert settings.supabase_publishable_key and settings.supabase_secret_key
    publishable, secret = settings.supabase_publishable_key, settings.supabase_secret_key
    turns = _turns(settings, services)
    sync_turn = turns("taste_sync", SYNC_PER_HOUR)
    shelf_turn = turns("for_you", FOR_YOU_PER_HOUR)
    routes = APIRouter()
    unavailable = Refused(503, "accounts_unavailable", "Accounts are unavailable. Try again soon.")

    @routes.get("/taste")
    async def read_taste(
        account: Annotated[Account, Depends(current_account)],
    ) -> TasteProfile | None:
        try:
            return await supabase.get_taste(client, publishable, account)
        except supabase.SupabaseError as exc:
            logger.warning("Taste Profile read failed: %s", exc)
            raise unavailable from None

    @routes.put("/taste", dependencies=[Depends(sync_turn)])
    async def keep_taste(
        body: TasteBody, account: Annotated[Account, Depends(current_account)]
    ) -> TasteProfile:
        try:
            return await supabase.put_taste(
                client, secret, account, body.source, distinct(body.artists)
            )
        except supabase.SupabaseError as exc:
            logger.warning("Taste Profile write failed: %s", exc)
            raise unavailable from None

    @routes.delete("/taste", status_code=204)
    async def clear_taste(account: Annotated[Account, Depends(current_account)]) -> Response:
        try:
            await supabase.delete_taste(client, publishable, account)
        except supabase.SupabaseError as exc:
            logger.warning("Taste Profile removal failed: %s", exc)
            raise unavailable from None
        return Response(status_code=204)

    @routes.post("/for-you", dependencies=[Depends(shelf_turn)], response_model_exclude_none=True)
    async def for_you(
        body: AccountForYouRequest, account: Annotated[Account, Depends(current_account)]
    ) -> ForYou:
        try:
            profile = await supabase.get_taste(client, publishable, account)
            if profile is None:
                raise Refused(404, "taste_not_found", "Add your Taste to see Concerts for you.")
            where = (
                Place(name="Near you", lat=body.near.lat, lon=body.near.lon)
                if body.near
                else (await supabase.alert_settings(client, publishable, account)).place
            )
        except supabase.SupabaseError as exc:
            logger.warning("Taste Profile read failed: %s", exc)
            raise unavailable from None
        if where is None:
            message = "Share your location or choose an Alert place to see Concerts for you."
            raise Refused(422, "for_you_needs_place", message)
        return await find_for_you(services, profile.artists, where, body.time_zone)

    return routes
