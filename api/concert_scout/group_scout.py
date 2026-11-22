"""Group Scout (/g/[id]): multiplayer Concert planning for 2 to 6 friends.

Each room holds a source-backed Concert pool for a place (ADR 0002), up to 6 friends' Tastes
(never Spotify account data, ADR 0003), optional dates and budget caps, and live In/Maybe/Pass
votes. Ranking is 100% deterministic with zero LLM calls, using Nash social welfare across every
member's hybrid match score so Concerts loved by the whole group beat ones that leave half the
group out.
"""

import asyncio
import datetime as dt
import logging
import math
import re
import secrets
import uuid
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, Protocol, Self

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, SecretStr, StringConstraints, model_validator
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import (
    clock,
    cobilling,
    embeddings,
    limits,
    matching,
    pool,
    security,
    similarity,
)
from concert_scout.config import Settings
from concert_scout.models import Concert, Name, Place, Reading, SeedArtist
from concert_scout.names import normalize
from concert_scout.pipeline import IMPORTED_SEEDS, Services
from concert_scout.security import Refused
from concert_scout.sources import (
    geocoder,
    listenbrainz,
    musicbrainz,
    ticketmaster,
)

logger = logging.getLogger(__name__)

# 128-bit random capability IDs (16 bytes -> 22 URL-safe base64 chars), matching share.SEARCH_ID.
ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

MAX_MEMBERS = 6
MAX_TASTE = 100
MAX_POOL_CONCERTS = 250
MAX_RANKED_PICKS = 30
NASH_EPSILON = 0.05
ROOM_TTL = dt.timedelta(days=30)
FURTHEST_AHEAD = dt.timedelta(days=400)

GROUPS_CREATE_PER_HOUR = 30
GROUPS_READ_PER_HOUR = 300
GROUPS_MUTATE_PER_HOUR = 180

ROOMS_TABLE = "/rest/v1/group_rooms"
MEMBERS_TABLE = "/rest/v1/group_members"
VOTES_TABLE = "/rest/v1/group_votes"

type VoteChoice = Literal["in", "maybe", "pass"]
type MatchBadge = Literal["Named", "Similar", "Co-billed", "Sounds close", "Style match"]

SIGNAL_BADGES: dict[matching.Signal, MatchBadge] = {
    "seed": "Named",
    "one_hop": "Similar",
    "two_hops": "Similar",
    "co_billed": "Co-billed",
    "semantic": "Sounds close",
    "tags": "Style match",
    "genre": "Style match",
}

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=48)]
RoomTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ConcertId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class GroupMember(BaseModel):
    """One friend in a Group Scout room."""

    id: str
    name: str
    artists: list[str]
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: float | None = None
    joined_at: dt.datetime


class GroupVote(BaseModel):
    """One member's vote on a Concert in the room."""

    room_id: str
    member_id: str
    concert_id: str
    vote: VoteChoice
    updated_at: dt.datetime


class StoredRoom(BaseModel):
    """The room record stored in Postgres (or Redis fallback)."""

    id: str
    title: str
    place: Place
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: float | None = None
    concerts: list[Concert] = []
    created_at: dt.datetime
    expires_at: dt.datetime


class EffectiveConstraints(BaseModel):
    """The group's combined date window and tightest budget cap."""

    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: float | None = None
    dates_conflict: bool = False


class MemberMatch(BaseModel):
    """Why a Concert fits one friend, derived strictly from source signals."""

    member_id: str
    name: str
    signal: matching.Signal
    badge: MatchBadge
    via: str | None = None
    matched_artist: str


class GroupPick(BaseModel):
    """One ranked Concert on the Group Poster, with per-member badges and live votes."""

    concert: Concert
    everyone_fits: bool
    member_matches: list[MemberMatch]
    lineup_match: list[str] = []
    member_votes: dict[str, VoteChoice] = {}
    vote_counts: dict[VoteChoice, int] = Field(
        default_factory=lambda: {"in": 0, "maybe": 0, "pass": 0}
    )
    consensus_in: bool = False


class GroupRoomState(BaseModel):
    """Everything the browser needs to render and interact with a Group Scout room."""

    id: str
    title: str
    place: Place
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: float | None = None
    effective: EffectiveConstraints
    members: list[GroupMember]
    picks: list[GroupPick]
    pool_total: int
    created_at: dt.datetime
    expires_at: dt.datetime


class CreateGroupRequest(BaseModel):
    place: Name
    title: RoomTitle | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: Annotated[float, Field(gt=0, le=10_000)] | None = None
    member_name: DisplayName
    artists: Annotated[list[Name], Field(min_length=1, max_length=MAX_TASTE)]
    member_start_date: dt.date | None = None
    member_end_date: dt.date | None = None
    member_max_price: Annotated[float, Field(gt=0, le=10_000)] | None = None
    time_zone: Annotated[str, StringConstraints(max_length=64)] = "UTC"

    @model_validator(mode="after")
    def dates_hold_together(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        if (
            self.member_start_date
            and self.member_end_date
            and self.member_end_date < self.member_start_date
        ):
            raise ValueError("member_end_date is before member_start_date")
        furthest = clock.now_in(self.time_zone).date() + FURTHEST_AHEAD
        for day in (self.start_date, self.end_date, self.member_start_date, self.member_end_date):
            if day and day > furthest:
                raise ValueError("dates too far ahead")
        return self


class JoinGroupRequest(BaseModel):
    name: DisplayName
    artists: Annotated[list[Name], Field(min_length=1, max_length=MAX_TASTE)]
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: Annotated[float, Field(gt=0, le=10_000)] | None = None

    @model_validator(mode="after")
    def dates_hold_together(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self


class UpdateGroupRequest(BaseModel):
    """Update a room's search location, title, date range, or budget cap."""

    place: Name | None = None
    title: RoomTitle | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: Annotated[float, Field(gt=0, le=10_000)] | None = None
    clear_dates: bool = False
    clear_max_price: bool = False
    time_zone: Annotated[str, StringConstraints(max_length=64)] = "UTC"

    @model_validator(mode="after")
    def dates_hold_together(self) -> Self:
        if (
            not self.clear_dates
            and self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date is before start_date")
        furthest = clock.now_in(self.time_zone).date() + FURTHEST_AHEAD
        for day in (self.start_date, self.end_date):
            if day and day > furthest:
                raise ValueError("dates too far ahead")
        return self


class UpdateMemberRequest(BaseModel):
    """Update a friend's Artists or personal date/budget preferences inside a room."""

    artists: Annotated[list[Name], Field(min_length=1, max_length=MAX_TASTE)]
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    max_price: Annotated[float, Field(gt=0, le=10_000)] | None = None
    clear_dates: bool = False
    clear_max_price: bool = False

    @model_validator(mode="after")
    def dates_hold_together(self) -> Self:
        if (
            not self.clear_dates
            and self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date is before start_date")
        return self


class VoteRequest(BaseModel):
    member_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    concert_id: ConcertId
    vote: VoteChoice


class GroupMembershipResponse(BaseModel):
    room: GroupRoomState
    member_id: str


class RoomRecord(BaseModel):
    """A full room snapshot stored in Redis when Supabase is unconfigured."""

    room: StoredRoom
    members: list[GroupMember] = []
    votes: list[GroupVote] = []


class GroupStoreError(Exception):
    """Group storage could not be reached or answered unexpectedly."""


class GroupStore(Protocol):
    """Persistence contract for Group Scout rooms, members and votes."""

    async def create_room(self, room: StoredRoom, creator: GroupMember) -> GroupMember: ...

    async def get_room(
        self, room_id: str, now: dt.datetime
    ) -> tuple[StoredRoom, list[GroupMember], list[GroupVote]] | None: ...

    async def add_member(self, room_id: str, member: GroupMember) -> GroupMember: ...

    async def update_room(self, room: StoredRoom) -> None: ...

    async def update_member(self, room_id: str, member: GroupMember) -> GroupMember | None: ...

    async def upsert_vote(
        self, room_id: str, member_id: str, concert_id: str, vote: VoteChoice, now: dt.datetime
    ) -> None: ...

    async def delete_member(self, room_id: str, member_id: str) -> bool: ...


def distinct_artists(names: Sequence[str]) -> list[str]:
    """Deduplicate Artist names by normalized form while keeping preference order."""
    seen: dict[str, str] = {}
    for name in names:
        cleaned = name.strip()
        if cleaned and (key := normalize(cleaned)):
            seen.setdefault(key, cleaned)
    return list(seen.values())[:MAX_TASTE]


def new_room_id() -> str:
    """A 22-character 128-bit random capability ID for a Group Scout room."""
    return secrets.token_urlsafe(16)


def nash_welfare(scores: Sequence[float], epsilon: float = NASH_EPSILON) -> float:
    """Geometric mean of (epsilon + s_m) across members so nobody is zeroed out."""
    if not scores:
        return epsilon
    clamped = [min(1.0, max(0.0, s)) for s in scores]
    product = math.prod(epsilon + s for s in clamped)
    return float(product ** (1.0 / len(clamped)))


def effective_constraints(
    room_start: dt.date | None,
    room_end: dt.date | None,
    room_max_price: float | None,
    members: Sequence[GroupMember],
) -> EffectiveConstraints:
    """Intersect member date windows and take the tightest max_price.

    When date windows are disjoint, sets `dates_conflict=True` and falls back to the room's
    window (or the union of member windows) so the group still sees candidate Concerts.
    """
    starts = [d for d in (room_start, *(m.start_date for m in members)) if d is not None]
    ends = [d for d in (room_end, *(m.end_date for m in members)) if d is not None]
    prices = [p for p in (room_max_price, *(m.max_price for m in members)) if p is not None]

    eff_start = max(starts) if starts else None
    eff_end = min(ends) if ends else None
    eff_price = min(prices) if prices else None

    if eff_start is not None and eff_end is not None and eff_start > eff_end:
        fallback_start = room_start or min(starts)
        fallback_end = room_end or max(ends)
        return EffectiveConstraints(
            start_date=fallback_start,
            end_date=fallback_end,
            max_price=eff_price,
            dates_conflict=True,
        )

    return EffectiveConstraints(
        start_date=eff_start,
        end_date=eff_end,
        max_price=eff_price,
        dates_conflict=False,
    )


def filter_concerts(
    concerts: Sequence[Concert],
    effective: EffectiveConstraints,
    today: dt.date | None = None,
) -> list[Concert]:
    """Filter Concerts strictly by source-reported dates and prices (ADR 0002).

    A Concert with no reported price never passes a strict max_price cap.
    """
    kept: list[Concert] = []
    for concert in concerts:
        if today is not None and concert.date is not None and concert.date < today:
            continue
        if effective.start_date is not None:
            if concert.date is None or concert.date < effective.start_date:
                continue
        if effective.end_date is not None:
            if concert.date is None or concert.date > effective.end_date:
                continue
        if effective.max_price is not None:
            if concert.price is None or concert.price.min > effective.max_price:
                continue
        kept.append(concert)
    return kept


def badge_for_signal(signal: matching.Signal) -> MatchBadge:
    return SIGNAL_BADGES[signal]


def score_group_concerts(
    concerts: Sequence[Concert],
    members: Sequence[GroupMember],
    member_tastes: Mapping[str, matching.Taste],
    artist_tags: Mapping[str, Sequence[str]] = {},
    *,
    room_start: dt.date | None = None,
    room_end: dt.date | None = None,
    room_max_price: float | None = None,
    today: dt.date | None = None,
    votes: Sequence[GroupVote] = (),
    limit: int = MAX_RANKED_PICKS,
) -> tuple[EffectiveConstraints, list[GroupPick]]:
    """Rank eligible Concerts by Nash social welfare across every member's hybrid Taste score."""
    effective = effective_constraints(room_start, room_end, room_max_price, members)
    eligible = filter_concerts(concerts, effective, today=today)
    if not eligible:
        return effective, []

    per_member: dict[str, dict[str, matching.Candidate]] = {}
    for member in members:
        taste = member_tastes.get(member.id) or matching.Taste([], [], [])
        scored = matching.score_concerts(eligible, taste, artist_tags)
        per_member[member.id] = {candidate.concert.id: candidate for candidate in scored}

    votes_by_concert: dict[str, dict[str, VoteChoice]] = {}
    valid_member_ids = {member.id for member in members}
    for vote in votes:
        if vote.member_id in valid_member_ids:
            votes_by_concert.setdefault(vote.concert_id, {})[vote.member_id] = vote.vote

    ranked_rows: list[tuple[tuple[float, int, float, dt.date, str], GroupPick]] = []
    for concert in eligible:
        scores: list[float] = []
        matches: list[MemberMatch] = []
        lineup_names: list[str] = []
        total_support = 0.0

        for member in members:
            candidate = per_member[member.id][concert.id]
            match = candidate.match
            if match is None:
                scores.append(0.0)
                continue
            scores.append(min(1.0, max(0.0, match.score)))
            total_support += match.support
            matches.append(
                MemberMatch(
                    member_id=member.id,
                    name=member.name,
                    signal=match.signal,
                    badge=badge_for_signal(match.signal),
                    via=match.via,
                    matched_artist=match.artist,
                )
            )
            for name in candidate.lineup_match:
                if name not in lineup_names:
                    lineup_names.append(name)

        welfare = nash_welfare(scores) if members else NASH_EPSILON
        everyone_fits = bool(members) and all(score > 0 for score in scores)

        member_votes = dict(votes_by_concert.get(concert.id, {}))
        vote_counts: dict[VoteChoice, int] = {
            "in": sum(1 for v in member_votes.values() if v == "in"),
            "maybe": sum(1 for v in member_votes.values() if v == "maybe"),
            "pass": sum(1 for v in member_votes.values() if v == "pass"),
        }
        consensus_in = len(members) >= 2 and all(
            member_votes.get(member.id) == "in" for member in members
        )

        pick = GroupPick(
            concert=concert,
            everyone_fits=everyone_fits,
            member_matches=matches,
            lineup_match=lineup_names,
            member_votes=member_votes,
            vote_counts=vote_counts,
            consensus_in=consensus_in,
        )
        sort_key = (
            -round(welfare, 9),
            -len(matches),
            -round(total_support, 9),
            concert.date or dt.date.max,
            concert.id,
        )
        ranked_rows.append((sort_key, pick))

    ranked_rows.sort(key=lambda pair: pair[0])
    top = [pick for _, pick in ranked_rows[:limit]]
    shown_ids = {pick.concert.id for pick in top}
    # Keep any Concert that already received votes visible even if new joins shifted the cutoff.
    for _, pick in ranked_rows[limit:]:
        if pick.member_votes and pick.concert.id not in shown_ids:
            top.append(pick)
            shown_ids.add(pick.concert.id)
    return effective, top


# ---------------------------------------------------------------------------
# Persistence stores (Supabase Postgres primary, Redis fallback for dev/tests)
# ---------------------------------------------------------------------------


def _server_headers(secret_key: SecretStr) -> dict[str, str]:
    return {"apikey": secret_key.get_secret_value()}


async def _send_supabase(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    try:
        response = await client.send(request)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GroupStoreError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise GroupStoreError(type(exc).__name__) from None
    return response


class SupabaseGroupStore:
    """Persists Group Scout rooms, members and votes in Supabase Postgres via REST API."""

    def __init__(self, client: httpx.AsyncClient, secret_key: SecretStr) -> None:
        self._client = client
        self._secret = secret_key

    async def create_room(self, room: StoredRoom, creator: GroupMember) -> GroupMember:
        room_row = {
            "id": room.id,
            "title": room.title,
            "place": room.place.model_dump(mode="json", exclude_none=True),
            "start_date": room.start_date.isoformat() if room.start_date else None,
            "end_date": room.end_date.isoformat() if room.end_date else None,
            "max_price": room.max_price,
            "concerts": [c.model_dump(mode="json", exclude_none=True) for c in room.concerts],
            "created_at": room.created_at.isoformat(),
            "expires_at": room.expires_at.isoformat(),
        }
        room_req = self._client.build_request(
            "POST",
            ROOMS_TABLE,
            json=[room_row],
            headers=_server_headers(self._secret) | {"Prefer": "return=minimal"},
        )
        await _send_supabase(self._client, room_req)
        return await self.add_member(room.id, creator)

    async def get_room(
        self, room_id: str, now: dt.datetime
    ) -> tuple[StoredRoom, list[GroupMember], list[GroupVote]] | None:
        room_req = self._client.build_request(
            "GET",
            ROOMS_TABLE,
            params={
                "select": (
                    "id,title,place,start_date,end_date,max_price,concerts,created_at,expires_at"
                ),
                "id": f"eq.{room_id}",
            },
            headers=_server_headers(self._secret),
        )
        room_res = await _send_supabase(self._client, room_req)
        try:
            rows = room_res.json()
        except ValueError as exc:
            raise GroupStoreError(f"unreadable room: {type(exc).__name__}") from None
        if not rows:
            return None
        try:
            room = StoredRoom.model_validate(rows[0])
        except ValueError as exc:
            raise GroupStoreError(f"unreadable room: {type(exc).__name__}") from None
        if room.expires_at <= now:
            return None

        members_req = self._client.build_request(
            "GET",
            MEMBERS_TABLE,
            params={
                "select": "id,name,artists,start_date,end_date,max_price,joined_at",
                "room_id": f"eq.{room_id}",
                "order": "joined_at.asc",
            },
            headers=_server_headers(self._secret),
        )
        votes_req = self._client.build_request(
            "GET",
            VOTES_TABLE,
            params={
                "select": "room_id,member_id,concert_id,vote,updated_at",
                "room_id": f"eq.{room_id}",
            },
            headers=_server_headers(self._secret),
        )
        members_res, votes_res = await asyncio.gather(
            _send_supabase(self._client, members_req),
            _send_supabase(self._client, votes_req),
        )
        try:
            members = [GroupMember.model_validate(r) for r in members_res.json()]
            votes = [GroupVote.model_validate(r) for r in votes_res.json()]
        except ValueError as exc:
            raise GroupStoreError(f"unreadable members/votes: {type(exc).__name__}") from None
        return room, members, votes

    async def add_member(self, room_id: str, member: GroupMember) -> GroupMember:
        row = {
            "id": member.id,
            "room_id": room_id,
            "name": member.name,
            "artists": member.artists,
            "start_date": member.start_date.isoformat() if member.start_date else None,
            "end_date": member.end_date.isoformat() if member.end_date else None,
            "max_price": member.max_price,
            "joined_at": member.joined_at.isoformat(),
        }
        request = self._client.build_request(
            "POST",
            MEMBERS_TABLE,
            json=[row],
            headers=_server_headers(self._secret) | {"Prefer": "return=representation"},
        )
        response = await _send_supabase(self._client, request)
        try:
            saved = [GroupMember.model_validate(r) for r in response.json()]
        except ValueError as exc:
            raise GroupStoreError(f"unreadable member: {type(exc).__name__}") from None
        if not saved:
            raise GroupStoreError("no member returned")
        return saved[0]

    async def update_room(self, room: StoredRoom) -> None:
        row = {
            "title": room.title,
            "place": room.place.model_dump(mode="json", exclude_none=True),
            "start_date": room.start_date.isoformat() if room.start_date else None,
            "end_date": room.end_date.isoformat() if room.end_date else None,
            "max_price": room.max_price,
            "concerts": [c.model_dump(mode="json", exclude_none=True) for c in room.concerts],
        }
        request = self._client.build_request(
            "PATCH",
            ROOMS_TABLE,
            params={"id": f"eq.{room.id}"},
            json=row,
            headers=_server_headers(self._secret) | {"Prefer": "return=minimal"},
        )
        await _send_supabase(self._client, request)

    async def update_member(self, room_id: str, member: GroupMember) -> GroupMember | None:
        row = {
            "artists": member.artists,
            "start_date": member.start_date.isoformat() if member.start_date else None,
            "end_date": member.end_date.isoformat() if member.end_date else None,
            "max_price": member.max_price,
        }
        request = self._client.build_request(
            "PATCH",
            MEMBERS_TABLE,
            params={"room_id": f"eq.{room_id}", "id": f"eq.{member.id}"},
            json=row,
            headers=_server_headers(self._secret) | {"Prefer": "return=representation"},
        )
        response = await _send_supabase(self._client, request)
        try:
            saved = [GroupMember.model_validate(r) for r in response.json()]
        except ValueError as exc:
            raise GroupStoreError(f"unreadable member: {type(exc).__name__}") from None
        return saved[0] if saved else None

    async def upsert_vote(
        self, room_id: str, member_id: str, concert_id: str, vote: VoteChoice, now: dt.datetime
    ) -> None:
        row = {
            "room_id": room_id,
            "member_id": member_id,
            "concert_id": concert_id,
            "vote": vote,
            "updated_at": now.isoformat(),
        }
        request = self._client.build_request(
            "POST",
            VOTES_TABLE,
            params={"on_conflict": "room_id,member_id,concert_id"},
            json=[row],
            headers=_server_headers(self._secret)
            | {"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        await _send_supabase(self._client, request)

    async def delete_member(self, room_id: str, member_id: str) -> bool:
        request = self._client.build_request(
            "DELETE",
            MEMBERS_TABLE,
            params={"room_id": f"eq.{room_id}", "id": f"eq.{member_id}"},
            headers=_server_headers(self._secret) | {"Prefer": "return=representation"},
        )
        response = await _send_supabase(self._client, request)
        try:
            deleted: list[Any] = response.json()
        except ValueError as exc:
            raise GroupStoreError(f"unreadable delete: {type(exc).__name__}") from None
        return bool(deleted)


class RedisGroupStore:
    """Redis-backed Group Scout storage used when Supabase is unconfigured (dev/unit tests)."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(room_id: str) -> str:
        return f"group:room:{room_id}"

    async def _read(self, room_id: str) -> RoomRecord | None:
        try:
            raw = await self._redis.get(self._key(room_id))
        except RedisError as exc:
            raise GroupStoreError(type(exc).__name__) from None
        if raw is None:
            return None
        try:
            return RoomRecord.model_validate_json(raw)
        except ValueError as exc:
            raise GroupStoreError(type(exc).__name__) from None

    async def _write(self, record: RoomRecord) -> None:
        try:
            await self._redis.set(self._key(record.room.id), record.model_dump_json(), ex=ROOM_TTL)
        except RedisError as exc:
            raise GroupStoreError(type(exc).__name__) from None

    async def create_room(self, room: StoredRoom, creator: GroupMember) -> GroupMember:
        await self._write(RoomRecord(room=room, members=[creator], votes=[]))
        return creator

    async def get_room(
        self, room_id: str, now: dt.datetime
    ) -> tuple[StoredRoom, list[GroupMember], list[GroupVote]] | None:
        record = await self._read(room_id)
        if record is None or record.room.expires_at <= now:
            return None
        return record.room, record.members, record.votes

    async def add_member(self, room_id: str, member: GroupMember) -> GroupMember:
        record = await self._read(room_id)
        if record is None:
            raise GroupStoreError("room missing")
        record.members.append(member)
        await self._write(record)
        return member

    async def update_room(self, room: StoredRoom) -> None:
        record = await self._read(room.id)
        if record is None:
            raise GroupStoreError("room missing")
        record.room = room
        valid_ids = {c.id for c in room.concerts}
        record.votes = [v for v in record.votes if v.concert_id in valid_ids]
        await self._write(record)

    async def update_member(self, room_id: str, member: GroupMember) -> GroupMember | None:
        record = await self._read(room_id)
        if record is None:
            return None
        updated = False
        next_members: list[GroupMember] = []
        for existing in record.members:
            if existing.id == member.id:
                next_members.append(member)
                updated = True
            else:
                next_members.append(existing)
        if not updated:
            return None
        record.members = next_members
        await self._write(record)
        return member

    async def upsert_vote(
        self, room_id: str, member_id: str, concert_id: str, vote: VoteChoice, now: dt.datetime
    ) -> None:
        record = await self._read(room_id)
        if record is None:
            raise GroupStoreError("room missing")
        remaining = [
            existing
            for existing in record.votes
            if not (existing.member_id == member_id and existing.concert_id == concert_id)
        ]
        remaining.append(
            GroupVote(
                room_id=room_id,
                member_id=member_id,
                concert_id=concert_id,
                vote=vote,
                updated_at=now,
            )
        )
        record.votes = remaining
        await self._write(record)

    async def delete_member(self, room_id: str, member_id: str) -> bool:
        record = await self._read(room_id)
        if record is None:
            return False
        kept_members = [m for m in record.members if m.id != member_id]
        if len(kept_members) == len(record.members):
            return False
        record.members = kept_members
        record.votes = [v for v in record.votes if v.member_id != member_id]
        await self._write(record)
        return True


# ---------------------------------------------------------------------------
# Deterministic hybrid Taste building across all members (zero LLM calls)
# ---------------------------------------------------------------------------


async def _resolve_seed(name: str, services: Services) -> SeedArtist:
    try:
        return await musicbrainz.resolve(services.musicbrainz, services.redis, name)
    except musicbrainz.MusicBrainzError as exc:
        logger.warning("Group Scout MusicBrainz failed: %s", exc)
        return SeedArtist(name=name)


async def _semantic_for_member(
    artists: Sequence[str],
    pool_artist_names: Sequence[str],
    services: Services,
) -> dict[str, float]:
    if not (
        artists
        and pool_artist_names
        and services.embedder
        and services.supabase
        and services.supabase_secret_key
    ):
        return {}
    reading = Reading(artists=list(artists[:IMPORTED_SEEDS]))
    vector = await embeddings.query_vector(services.embedder, services.redis, reading)
    if vector is None:
        return {}
    return await embeddings.pool_scores(
        services.supabase, services.supabase_secret_key, vector, pool_artist_names
    )


async def _build_member_tastes(
    members: Sequence[GroupMember],
    concerts: Sequence[Concert],
    services: Services,
) -> tuple[dict[str, matching.Taste], dict[str, list[str]]]:
    """Resolve seeds, 1-hop neighbours, co-billing peers, pool tags and semantic vectors."""
    if not members:
        return {}, {}

    top_by_member: dict[str, list[str]] = {
        member.id: distinct_artists(member.artists)[:IMPORTED_SEEDS] for member in members
    }
    unique_top: list[str] = list(
        dict.fromkeys(name for names in top_by_member.values() for name in names)
    )

    tag_fetch = listenbrainz.TagFetch(services.listenbrainz, services.redis)
    tag_fetch.add(concerts)

    pool_names = list(
        dict.fromkeys(artist.name for concert in concerts for artist in concert.artists)
    )

    async def resolve_all_seeds() -> dict[str, SeedArtist]:
        resolved = await asyncio.gather(*(_resolve_seed(name, services) for name in unique_top))
        return {
            normalize(name): seed
            for name, seed in zip(unique_top, resolved, strict=True)
            if normalize(name)
        }

    async def safe_tags() -> dict[str, list[str]]:
        try:
            return await tag_fetch.tags()
        except listenbrainz.ListenBrainzError as exc:
            logger.warning("Group Scout tags failed: %s", exc)
            return {}

    seeds_by_key, peers_by_seed, artist_tags, semantic_list = await asyncio.gather(
        resolve_all_seeds(),
        cobilling.find_peers(services.supabase, services.supabase_secret_key, unique_top),
        safe_tags(),
        asyncio.gather(
            *(_semantic_for_member(member.artists, pool_names, services) for member in members)
        ),
    )

    all_resolved_seeds = list(seeds_by_key.values())
    all_neighbours = await similarity.find_neighbours(
        services.listenbrainz, services.lastfm, services.redis, all_resolved_seeds, hops=1
    )
    neighbours_by_seed: dict[str, list[matching.Neighbour]] = {}
    for neighbour in all_neighbours:
        neighbours_by_seed.setdefault(normalize(neighbour.seed), []).append(neighbour)

    peers_by_key: dict[str, list[matching.CoBilledPeer]] = {
        normalize(seed_name): list(peers)
        for seed_name, peers in peers_by_seed.items()
        if normalize(seed_name)
    }

    tastes: dict[str, matching.Taste] = {}
    for member, semantic in zip(members, semantic_list, strict=True):
        cleaned = distinct_artists(member.artists)
        top_names = top_by_member[member.id]
        top_keys = {normalize(name) for name in top_names}
        member_seeds: list[SeedArtist] = []
        member_neighbours: list[matching.Neighbour] = []
        member_peers: dict[str, list[matching.CoBilledPeer]] = {}

        for name in top_names:
            key = normalize(name)
            seed = seeds_by_key.get(key) or SeedArtist(name=name)
            # Keep the member's own seed name as well so exact matching never loses it if MB
            # returned a canonical alias.
            member_seeds.append(seed)
            if normalize(seed.name) != key:
                member_seeds.append(SeedArtist(name=name))
            member_neighbours.extend(neighbours_by_seed.get(key, ()))
            if normalize(seed.name) != key:
                member_neighbours.extend(neighbours_by_seed.get(normalize(seed.name), ()))
            if peers := peers_by_key.get(key):
                member_peers[name] = peers

        for name in cleaned:
            if normalize(name) not in top_keys:
                member_seeds.append(SeedArtist(name=name))

        tastes[member.id] = matching.Taste(
            seeds=member_seeds,
            neighbours=member_neighbours,
            tags=[],
            cobilling=member_peers,
            semantic=semantic,
        )

    return tastes, artist_tags


async def _assemble_state(
    room: StoredRoom,
    members: Sequence[GroupMember],
    votes: Sequence[GroupVote],
    services: Services,
    today: dt.date,
) -> GroupRoomState:
    tastes, artist_tags = await _build_member_tastes(members, room.concerts, services)
    effective, picks = score_group_concerts(
        room.concerts,
        members,
        tastes,
        artist_tags,
        room_start=room.start_date,
        room_end=room.end_date,
        room_max_price=room.max_price,
        today=today,
        votes=votes,
    )
    return GroupRoomState(
        id=room.id,
        title=room.title,
        place=room.place,
        start_date=room.start_date,
        end_date=room.end_date,
        max_price=room.max_price,
        effective=effective,
        members=list(members),
        picks=picks,
        pool_total=len(room.concerts),
        created_at=room.created_at,
        expires_at=room.expires_at,
    )


# ---------------------------------------------------------------------------
# FastAPI router (/groups)
# ---------------------------------------------------------------------------


def _default_store(services: Services) -> GroupStore:
    if services.supabase and services.supabase_secret_key:
        return SupabaseGroupStore(services.supabase, services.supabase_secret_key)
    return RedisGroupStore(services.redis)


def router(
    settings: Settings,
    services: Services,
    store: GroupStore | None = None,
) -> APIRouter:
    """Group Scout endpoints, usable by guests with zero Account or Spotify data."""
    routes = APIRouter(prefix="/groups")
    active_store = store or _default_store(services)
    unavailable = Refused(
        503, "group_unavailable", "Group Scout storage is unavailable. Try again soon."
    )
    not_found = Refused(
        404, "group_not_found", "That Group Scout room is not here. Its link may have expired."
    )

    async def limit(request: Request, bucket: str, cap: int) -> None:
        ip = security.client_ip(request, settings.client_ip_header)
        try:
            await limits.visitor_call(services.redis, bucket, ip, cap)
        except limits.VisitorLimitReached as exc:
            message = "That is a lot of Group Scout requests. Try again soon."
            raise Refused(429, "visitor_limit", message, exc.retry_after) from None
        except RedisError as exc:
            logger.warning("Group Scout limit failed: %s", type(exc).__name__)

    async def load_room(
        room_id: str, now: dt.datetime
    ) -> tuple[StoredRoom, list[GroupMember], list[GroupVote]]:
        if not ROOM_ID_RE.fullmatch(room_id):
            raise not_found
        try:
            loaded = await active_store.get_room(room_id, now)
        except GroupStoreError as exc:
            logger.warning("Group Scout read failed: %s", exc)
            raise unavailable from None
        if loaded is None:
            raise not_found
        return loaded

    @routes.post("", response_model=GroupMembershipResponse, response_model_exclude_none=True)
    async def create_group(request: Request, body: CreateGroupRequest) -> GroupMembershipResponse:
        await limit(request, "groups_create", GROUPS_CREATE_PER_HOUR)
        cleaned_artists = distinct_artists(body.artists)
        if not cleaned_artists:
            raise Refused(422, "invalid_group", "Add at least one Artist to your Taste.")

        try:
            place = await geocoder.geocode(services.geocoder, services.redis, body.place)
        except geocoder.GeocoderError as exc:
            logger.warning("Group Scout geocode failed: %s", exc)
            raise Refused(
                503, "geocoder_unavailable", "Place lookup is not answering. Try again soon."
            ) from None
        if place is None:
            raise Refused(404, "place_not_found", "We could not find that place. Try a city name.")

        now_local = clock.now_in(body.time_zone)
        try:
            concerts = await pool.find_concerts(
                services.ticketmaster,
                services.musicbrainz,
                services.redis,
                place,
                cleaned_artists[:IMPORTED_SEEDS],
                body.start_date,
                body.end_date,
                now_local,
            )
        except ticketmaster.TicketmasterError:
            raise Refused(
                503, "ticketmaster_unavailable", "Ticketmaster is not responding. Try again soon."
            ) from None
        except limits.DailyLimitReached as exc:
            raise Refused(
                429,
                "ticketmaster_limit",
                "We have used today's Ticketmaster allowance. Try again tomorrow.",
                exc.retry_after,
            ) from None

        now_utc = dt.datetime.now(dt.UTC)
        room = StoredRoom(
            id=new_room_id(),
            title=body.title or place.name,
            place=place,
            start_date=body.start_date,
            end_date=body.end_date,
            max_price=body.max_price,
            concerts=list(concerts[:MAX_POOL_CONCERTS]),
            created_at=now_utc,
            expires_at=now_utc + ROOM_TTL,
        )
        creator = GroupMember(
            id=str(uuid.uuid4()),
            name=body.member_name,
            artists=cleaned_artists,
            start_date=body.member_start_date,
            end_date=body.member_end_date,
            max_price=body.member_max_price,
            joined_at=now_utc,
        )
        try:
            saved_creator = await active_store.create_room(room, creator)
        except GroupStoreError as exc:
            logger.warning("Group Scout create failed: %s", exc)
            raise unavailable from None

        state = await _assemble_state(room, [saved_creator], [], services, now_local.date())
        return GroupMembershipResponse(room=state, member_id=saved_creator.id)

    @routes.get("/{room_id}", response_model=GroupRoomState, response_model_exclude_none=True)
    async def read_group(request: Request, room_id: str) -> GroupRoomState:
        await limit(request, "groups_read", GROUPS_READ_PER_HOUR)
        now_utc = dt.datetime.now(dt.UTC)
        room, members, votes = await load_room(room_id, now_utc)
        return await _assemble_state(room, members, votes, services, now_utc.date())

    @routes.patch("/{room_id}", response_model=GroupRoomState, response_model_exclude_none=True)
    async def update_group(
        request: Request, room_id: str, body: UpdateGroupRequest
    ) -> GroupRoomState:
        await limit(request, "groups_mutate", GROUPS_MUTATE_PER_HOUR)
        now_utc = dt.datetime.now(dt.UTC)
        now_local = clock.now_in(body.time_zone)
        room, members, votes = await load_room(room_id, now_utc)

        next_place = room.place
        place_changed = False
        if body.place is not None and body.place.strip().casefold() != room.place.name.casefold():
            try:
                geocoded = await geocoder.geocode(services.geocoder, services.redis, body.place)
            except geocoder.GeocoderError as exc:
                logger.warning("Group Scout geocode failed: %s", exc)
                raise Refused(
                    503,
                    "geocoder_unavailable",
                    "Place lookup is not answering. Try again soon.",
                ) from None
            if geocoded is None:
                raise Refused(
                    404, "place_not_found", "We could not find that place. Try a city name."
                )
            next_place = geocoded
            place_changed = True

        next_start = (
            None
            if body.clear_dates
            else (body.start_date if "start_date" in body.model_fields_set else room.start_date)
        )
        next_end = (
            None
            if body.clear_dates
            else (body.end_date if "end_date" in body.model_fields_set else room.end_date)
        )
        if next_start and next_end and next_end < next_start:
            raise Refused(422, "invalid_group", "End date must be on or after the start date.")

        next_price = (
            None
            if body.clear_max_price
            else (body.max_price if "max_price" in body.model_fields_set else room.max_price)
        )
        next_title = body.title or (
            next_place.name if place_changed and room.title == room.place.name else room.title
        )

        dates_changed = next_start != room.start_date or next_end != room.end_date
        next_concerts = room.concerts
        if place_changed or dates_changed:
            seed_artists = distinct_artists(
                [artist for member in members for artist in member.artists[:IMPORTED_SEEDS]]
            )[:IMPORTED_SEEDS]
            try:
                fetched = await pool.find_concerts(
                    services.ticketmaster,
                    services.musicbrainz,
                    services.redis,
                    next_place,
                    seed_artists,
                    next_start,
                    next_end,
                    now_local,
                )
            except ticketmaster.TicketmasterError:
                raise Refused(
                    503,
                    "ticketmaster_unavailable",
                    "Ticketmaster is not responding. Try again soon.",
                ) from None
            except limits.DailyLimitReached as exc:
                raise Refused(
                    429,
                    "ticketmaster_limit",
                    "We have used today's Ticketmaster allowance. Try again tomorrow.",
                    exc.retry_after,
                ) from None
            next_concerts = list(fetched[:MAX_POOL_CONCERTS])

        updated_room = room.model_copy(
            update={
                "title": next_title,
                "place": next_place,
                "start_date": next_start,
                "end_date": next_end,
                "max_price": next_price,
                "concerts": next_concerts,
            }
        )
        try:
            await active_store.update_room(updated_room)
        except GroupStoreError as exc:
            logger.warning("Group Scout room update failed: %s", exc)
            raise unavailable from None

        valid_ids = {c.id for c in next_concerts}
        kept_votes = [v for v in votes if v.concert_id in valid_ids]
        return await _assemble_state(updated_room, members, kept_votes, services, now_local.date())

    @routes.patch(
        "/{room_id}/members/{member_id}",
        response_model=GroupRoomState,
        response_model_exclude_none=True,
    )
    async def update_member_profile(
        request: Request, room_id: str, member_id: str, body: UpdateMemberRequest
    ) -> GroupRoomState:
        await limit(request, "groups_mutate", GROUPS_MUTATE_PER_HOUR)
        if not UUID_RE.fullmatch(member_id):
            raise Refused(404, "member_not_found", "That friend is not in this room.")
        cleaned_artists = distinct_artists(body.artists)
        if not cleaned_artists:
            raise Refused(422, "invalid_group", "Add at least one Artist to your Taste.")

        now_utc = dt.datetime.now(dt.UTC)
        room, members, votes = await load_room(room_id, now_utc)
        existing = next((m for m in members if m.id == member_id), None)
        if existing is None:
            raise Refused(404, "member_not_found", "That friend is not in this room.")

        next_start = (
            None
            if body.clear_dates
            else (body.start_date if "start_date" in body.model_fields_set else existing.start_date)
        )
        next_end = (
            None
            if body.clear_dates
            else (body.end_date if "end_date" in body.model_fields_set else existing.end_date)
        )
        if next_start and next_end and next_end < next_start:
            raise Refused(422, "invalid_group", "End date must be on or after the start date.")
        next_price = (
            None
            if body.clear_max_price
            else (body.max_price if "max_price" in body.model_fields_set else existing.max_price)
        )

        candidate = existing.model_copy(
            update={
                "artists": cleaned_artists,
                "start_date": next_start,
                "end_date": next_end,
                "max_price": next_price,
            }
        )
        try:
            saved = await active_store.update_member(room.id, candidate)
        except GroupStoreError as exc:
            logger.warning("Group Scout member update failed: %s", exc)
            raise unavailable from None
        if saved is None:
            raise Refused(404, "member_not_found", "That friend is not in this room.")

        updated_members = [saved if m.id == member_id else m for m in members]
        return await _assemble_state(room, updated_members, votes, services, now_utc.date())

    @routes.post(
        "/{room_id}/members",
        response_model=GroupMembershipResponse,
        response_model_exclude_none=True,
    )
    async def join_group(
        request: Request, room_id: str, body: JoinGroupRequest
    ) -> GroupMembershipResponse:
        await limit(request, "groups_mutate", GROUPS_MUTATE_PER_HOUR)
        cleaned_artists = distinct_artists(body.artists)
        if not cleaned_artists:
            raise Refused(422, "invalid_group", "Add at least one Artist to your Taste.")

        now_utc = dt.datetime.now(dt.UTC)
        room, members, votes = await load_room(room_id, now_utc)
        if len(members) >= MAX_MEMBERS:
            raise Refused(
                409,
                "group_full",
                f"This Group Scout room is full ({MAX_MEMBERS} friends max).",
            )

        member = GroupMember(
            id=str(uuid.uuid4()),
            name=body.name,
            artists=cleaned_artists,
            start_date=body.start_date,
            end_date=body.end_date,
            max_price=body.max_price,
            joined_at=now_utc,
        )
        try:
            saved = await active_store.add_member(room.id, member)
        except GroupStoreError as exc:
            logger.warning("Group Scout join failed: %s", exc)
            raise unavailable from None

        updated_members = [*members, saved]
        state = await _assemble_state(room, updated_members, votes, services, now_utc.date())
        return GroupMembershipResponse(room=state, member_id=saved.id)

    @routes.put("/{room_id}/votes", response_model=GroupRoomState, response_model_exclude_none=True)
    async def cast_vote(request: Request, room_id: str, body: VoteRequest) -> GroupRoomState:
        await limit(request, "groups_mutate", GROUPS_MUTATE_PER_HOUR)
        if not UUID_RE.fullmatch(body.member_id):
            raise Refused(403, "member_not_found", "Join this room before voting.")

        now_utc = dt.datetime.now(dt.UTC)
        room, members, votes = await load_room(room_id, now_utc)
        if not any(m.id == body.member_id for m in members):
            raise Refused(403, "member_not_found", "Join this room before voting.")
        if not any(c.id == body.concert_id for c in room.concerts):
            raise Refused(404, "concert_not_found", "That Concert is not in this room.")

        try:
            await active_store.upsert_vote(
                room.id, body.member_id, body.concert_id, body.vote, now_utc
            )
        except GroupStoreError as exc:
            logger.warning("Group Scout vote failed: %s", exc)
            raise unavailable from None

        updated_votes = [
            existing
            for existing in votes
            if not (existing.member_id == body.member_id and existing.concert_id == body.concert_id)
        ]
        updated_votes.append(
            GroupVote(
                room_id=room.id,
                member_id=body.member_id,
                concert_id=body.concert_id,
                vote=body.vote,
                updated_at=now_utc,
            )
        )
        return await _assemble_state(room, members, updated_votes, services, now_utc.date())

    @routes.delete(
        "/{room_id}/members/{member_id}",
        response_model=GroupRoomState,
        response_model_exclude_none=True,
    )
    async def leave_group(request: Request, room_id: str, member_id: str) -> GroupRoomState:
        await limit(request, "groups_mutate", GROUPS_MUTATE_PER_HOUR)
        if not UUID_RE.fullmatch(member_id):
            raise Refused(404, "member_not_found", "That friend is not in this room.")

        now_utc = dt.datetime.now(dt.UTC)
        room, members, votes = await load_room(room_id, now_utc)
        try:
            removed = await active_store.delete_member(room.id, member_id)
        except GroupStoreError as exc:
            logger.warning("Group Scout leave failed: %s", exc)
            raise unavailable from None
        if not removed:
            raise Refused(404, "member_not_found", "That friend is not in this room.")

        remaining_members = [m for m in members if m.id != member_id]
        remaining_votes = [v for v in votes if v.member_id != member_id]
        return await _assemble_state(
            room, remaining_members, remaining_votes, services, now_utc.date()
        )

    return routes
