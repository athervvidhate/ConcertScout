"""Instant Poster Sculpting: short-lived pool sessions, source-fact filters and Rocchio steering.

Every filter evaluates strictly against source facts (ADR 0002): a Concert missing a source price
or a verified venue capacity tier never falsely passes a cap or room-size filter. Filter-only
sculpts reuse cached Jev grades and existing reasons with zero vendor or model calls.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Annotated, Literal

import anyio
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import (
    assemble,
    cobilling,
    embeddings,
    limits,
    matching,
    ranker,
    share,
    similarity,
    telemetry,
)
from concert_scout.models import (
    ArtistProfile,
    Candidates,
    Concert,
    Name,
    Poster,
    Reading,
    SeedArtist,
)
from concert_scout.names import normalize
from concert_scout.sources import embedder as embedding_api
from concert_scout.sources import musicbrainz, supabase, venues

if TYPE_CHECKING:
    from concert_scout.pipeline import Services

logger = logging.getLogger(__name__)

# Short-lived pool session TTL: 30 minutes, separate from the 90-day Shared Poster snapshot.
SESSION_TTL = dt.timedelta(minutes=30)
MAX_POOL_SIZE = 1500
MAX_BOOST_ARTISTS = 5
MAX_EXCLUDE_ARTISTS = 10
MAX_METADATA_KEYS = 600

# Rocchio relevance feedback weights: q' = normalize(q + 0.6 * v_liked - 0.5 * v_disliked).
ROCCHIO_BETA = 0.6
ROCCHIO_GAMMA = 0.5

# Strictly verified venue tiers that qualify for "Intimate rooms".
INTIMATE_TIERS: frozenset[venues.VenueTier] = frozenset({"Intimate club", "Club / Ballroom"})

# Monotonic room-size scale for the Discovery curve (0.0 = intimate club, 1.0 = arena/stadium).
TIER_POPULARITY: dict[venues.VenueTier, float] = {
    "Intimate club": 0.0,
    "Club / Ballroom": 0.25,
    "Theater": 0.5,
    "Amphitheater / Large hall": 0.75,
    "Arena / Stadium": 1.0,
}

# Friday = 4, Saturday = 5, Sunday = 6 on the venue's local calendar.
WEEKEND_WEEKDAYS = frozenset({4, 5, 6})

DiscoveryMode = Literal["balanced", "familiar", "deep_cuts"]


class SessionExpired(Exception):
    """The pool session for this Search ID is missing or older than 30 minutes."""


class StoredNeighbour(BaseModel):
    name: str
    mbid: str | None = None
    hops: Literal[1, 2]
    closeness: float
    seed: str


class StoredCoBilledPeer(BaseModel):
    artist_key: str
    weight: float
    shared_shows: int = 1


class StoredTaste(BaseModel):
    """Serializable Taste snapshot kept in `session:{search_id}`. No Spotify data."""

    seeds: list[SeedArtist] = []
    neighbours: list[StoredNeighbour] = []
    tags: list[str] = []
    genres: list[str] = []
    cobilling: dict[str, list[StoredCoBilledPeer]] = {}
    semantic: dict[str, float] = {}

    @classmethod
    def from_taste(cls, taste: matching.Taste) -> StoredTaste:
        return cls(
            seeds=list(taste.seeds),
            neighbours=[
                StoredNeighbour(
                    name=n.name,
                    mbid=n.mbid,
                    hops=n.hops,
                    closeness=n.closeness,
                    seed=n.seed,
                )
                for n in taste.neighbours
            ],
            tags=list(taste.tags),
            genres=list(taste.genres),
            cobilling={
                seed: [
                    StoredCoBilledPeer(
                        artist_key=p.artist_key,
                        weight=p.weight,
                        shared_shows=p.shared_shows,
                    )
                    for p in peers
                ]
                for seed, peers in taste.cobilling.items()
            },
            semantic=dict(taste.semantic),
        )

    def to_taste(self) -> matching.Taste:
        return matching.Taste(
            seeds=list(self.seeds),
            neighbours=[
                matching.Neighbour(
                    name=n.name,
                    mbid=n.mbid,
                    hops=n.hops,
                    closeness=n.closeness,
                    seed=n.seed,
                )
                for n in self.neighbours
            ],
            tags=list(self.tags),
            genres=list(self.genres),
            cobilling={
                seed: [
                    matching.CoBilledPeer(
                        artist_key=p.artist_key,
                        weight=p.weight,
                        shared_shows=p.shared_shows,
                    )
                    for p in peers
                ]
                for seed, peers in self.cobilling.items()
            },
            semantic=dict(self.semantic),
        )


class PoolSession(BaseModel):
    """Short-lived Search pool kept in Redis for Sculpting.

    Never holds visitor coordinates, IP addresses, or Spotify OAuth data.
    """

    reading: Reading
    pool: list[Concert]
    artist_tags: dict[str, list[str]] = {}
    query_embedding: list[float] | None = None
    taste: StoredTaste = Field(default_factory=StoredTaste)
    grades: dict[str, int] = {}
    reasons: dict[str, str] = {}
    artist_listeners: dict[str, int] = {}
    venue_tiers: dict[str, venues.VenueTier] = {}
    has_taste: bool = True


class SculptRequest(BaseModel):
    """Strict bounds on a Poster Sculpt request."""

    model_config = ConfigDict(extra="forbid")

    discovery: DiscoveryMode = "balanced"
    max_price: Annotated[float, Field(gt=0, le=10_000)] | None = None
    weekends_only: bool = False
    intimate_only: bool = False
    hide_festivals: bool = False
    boost_artists: Annotated[list[Name], Field(max_length=MAX_BOOST_ARTISTS)] = []
    exclude_artists: Annotated[list[Name], Field(max_length=MAX_EXCLUDE_ARTISTS)] = []


class SculptMeta(BaseModel):
    """Source-fact counts from applying the Sculpt filters."""

    pool_total: int
    filtered_total: int
    unpriced_count: int = 0
    unknown_room_count: int = 0
    eliminated_by: str | None = None


class SculptResponse(BaseModel):
    search_id: str
    poster: Poster
    candidates: Candidates
    meta: SculptMeta


def session_key(search_id: str) -> str:
    return f"session:{search_id}"


async def save_session(redis: Redis, search_id: str, session: PoolSession) -> None:
    """Persist a Search's Concert pool in Redis for 30 minutes."""
    trimmed = (
        session.model_copy(update={"pool": session.pool[:MAX_POOL_SIZE]})
        if len(session.pool) > MAX_POOL_SIZE
        else session
    )
    await redis.set(session_key(search_id), trimmed.model_dump_json(), ex=SESSION_TTL)


async def load_session(redis: Redis, search_id: str) -> PoolSession:
    """Load an active pool session from Redis, or raise `SessionExpired`."""
    raw = await redis.get(session_key(search_id))
    if raw is None:
        raise SessionExpired
    return PoolSession.model_validate_json(raw)


async def load_cached_metadata(
    redis: Redis, concerts: Sequence[Concert]
) -> tuple[dict[str, int], dict[str, venues.VenueTier]]:
    """Read already-cached Last.fm listener counts and verified venue tiers from Redis.

    Makes zero external network calls and fails soft on Redis errors.
    """
    artist_keys: list[str] = []
    seen_artists: set[str] = set()
    venue_pairs: list[tuple[str, str]] = []
    seen_venues: set[str] = set()
    for concert in concerts:
        for artist in concert.artists:
            norm = normalize(artist.name)
            if norm and norm not in seen_artists and len(artist_keys) < MAX_METADATA_KEYS:
                seen_artists.add(norm)
                artist_keys.append(norm)
        if concert.venue:
            vkey = venues.venue_key(concert.venue, concert.city)
            if vkey and vkey not in seen_venues and len(venue_pairs) < MAX_METADATA_KEYS:
                seen_venues.add(vkey)
                venue_pairs.append((vkey, venues.cache_key(concert.venue, concert.city)))

    listeners: dict[str, int] = {}
    tiers: dict[str, venues.VenueTier] = {}
    try:
        if artist_keys:
            raw_artists = await redis.mget([f"artist:lastfm:{key}" for key in artist_keys])
            for key, raw in zip(artist_keys, raw_artists, strict=True):
                if not raw:
                    continue
                try:
                    profile = ArtistProfile.model_validate_json(raw)
                except ValueError:
                    continue
                if profile.listeners is not None:
                    listeners[key] = profile.listeners
        if venue_pairs:
            raw_venues = await redis.mget([ckey for _, ckey in venue_pairs])
            for (vkey, _), raw in zip(venue_pairs, raw_venues, strict=True):
                if not raw:
                    continue
                try:
                    character = venues.VenueCharacter.model_validate_json(raw)
                except ValueError:
                    continue
                if character.tier is not None:
                    tiers[vkey] = character.tier
    except RedisError as exc:
        logger.warning("Cached sculpt metadata unavailable: %s", type(exc).__name__)
    return listeners, tiers


def rocchio_shift(
    query: Sequence[float],
    liked: Sequence[Sequence[float]],
    disliked: Sequence[Sequence[float]],
    *,
    beta: float = ROCCHIO_BETA,
    gamma: float = ROCCHIO_GAMMA,
) -> list[float]:
    """Rocchio feedback: `q' = normalize(q + beta * mean(liked) - gamma * mean(disliked))`."""
    dims = len(query)
    if dims == 0:
        return []
    shifted = list(query)
    if liked:
        scale = beta / len(liked)
        for vec in liked:
            if len(vec) == dims:
                for i in range(dims):
                    shifted[i] += scale * vec[i]
    if disliked:
        scale = gamma / len(disliked)
        for vec in disliked:
            if len(vec) == dims:
                for i in range(dims):
                    shifted[i] -= scale * vec[i]
    try:
        return embedding_api.unit(shifted)
    except embedding_api.EmbedderError:
        return list(query)


def _venue_tier_of(
    concert: Concert, venue_tiers: Mapping[str, venues.VenueTier]
) -> venues.VenueTier | None:
    if not concert.venue:
        return None
    key = venues.venue_key(concert.venue, concert.city)
    if key in venue_tiers:
        return venue_tiers[key]
    fallback = venues.venue_key(concert.venue, None)
    return venue_tiers.get(fallback)


def apply_filters(
    concerts: Sequence[Concert],
    req: SculptRequest,
    venue_tiers: Mapping[str, venues.VenueTier],
) -> tuple[list[Concert], SculptMeta]:
    """Apply hard source-fact filters strictly in Python. Missing facts never falsely pass."""
    pool_total = len(concerts)
    current = list(concerts)
    eliminated_by: str | None = None
    unpriced_count = 0
    unknown_room_count = 0

    def record_elimination(name: str, before: int, after: int) -> None:
        nonlocal eliminated_by
        if before > 0 and after == 0 and eliminated_by is None:
            eliminated_by = name

    if req.exclude_artists:
        excluded = {normalize(name) for name in req.exclude_artists if normalize(name)}
        before = len(current)
        current = [c for c in current if not any(normalize(a.name) in excluded for a in c.artists)]
        record_elimination("exclude_artists", before, len(current))

    if req.hide_festivals:
        before = len(current)
        current = [c for c in current if not c.festival]
        record_elimination("hide_festivals", before, len(current))

    if req.weekends_only:
        before = len(current)
        # `concert.date` is already on the venue's local calendar (models.py).
        current = [
            c for c in current if c.date is not None and c.date.weekday() in WEEKEND_WEEKDAYS
        ]
        record_elimination("weekends_only", before, len(current))

    if req.intimate_only:
        before = len(current)
        kept: list[Concert] = []
        for concert in current:
            tier = _venue_tier_of(concert, venue_tiers)
            if tier is None:
                unknown_room_count += 1
            elif tier in INTIMATE_TIERS:
                kept.append(concert)
        current = kept
        record_elimination("intimate_only", before, len(current))

    if req.max_price is not None:
        before = len(current)
        kept = []
        for concert in current:
            if concert.price is None:
                unpriced_count += 1
            elif concert.price.min <= req.max_price:
                kept.append(concert)
        current = kept
        record_elimination("max_price", before, len(current))

    meta = SculptMeta(
        pool_total=pool_total,
        filtered_total=len(current),
        unpriced_count=unpriced_count,
        unknown_room_count=unknown_room_count,
        eliminated_by=eliminated_by,
    )
    return current, meta


def _popularity_signal(
    concert: Concert,
    artist_listeners: Mapping[str, int],
    venue_tiers: Mapping[str, venues.VenueTier],
) -> float | None:
    """Normalized popularity in [0, 1] from cached Last.fm listeners and verified venue tier."""
    signals: list[float] = []
    if concert.artists:
        listener_counts = [
            artist_listeners[key]
            for a in concert.artists
            if (key := normalize(a.name)) in artist_listeners
        ]
        if listener_counts:
            top = max(listener_counts)
            # log10 scale: 100 listeners -> 0.0, ~3M+ listeners -> 1.0.
            signals.append(min(1.0, max(0.0, (math.log10(max(top, 100)) - 2.0) / 4.5)))
    tier = _venue_tier_of(concert, venue_tiers)
    if tier is not None:
        signals.append(TIER_POPULARITY[tier])
    if not signals:
        return None
    return sum(signals) / len(signals)


def apply_discovery(
    candidates: Sequence[matching.Candidate],
    discovery: DiscoveryMode,
    artist_listeners: Mapping[str, int],
    venue_tiers: Mapping[str, venues.VenueTier],
) -> list[matching.Candidate]:
    """Adjust candidate match scores along the Discovery curve (balanced / familiar / deep_cuts)."""
    if discovery == "balanced":
        return list(candidates)

    adjusted: list[matching.Candidate] = []
    for candidate in candidates:
        pop = _popularity_signal(candidate.concert, artist_listeners, venue_tiers)
        if pop is None:
            adjusted.append(candidate)
            continue
        if discovery == "deep_cuts":
            delta = 0.25 * (1.0 - pop) - 0.10 * pop
        else:  # familiar
            delta = 0.25 * pop - 0.10 * (1.0 - pop)

        if candidate.match is not None:
            new_score = max(0.01, candidate.match.score + delta)
            new_support = max(0.01, candidate.match.support + delta)
            adjusted.append(
                candidate.model_copy(
                    update={
                        "match": candidate.match.model_copy(
                            update={"score": new_score, "support": new_support}
                        )
                    }
                )
            )
        else:
            # Place-only Concerts have no Match; order them by a synthetic popularity score.
            artist_name = candidate.concert.artists[0].name if candidate.concert.artists else ""
            adjusted.append(
                candidate.model_copy(
                    update={
                        "match": matching.Match(
                            artist=artist_name,
                            signal="genre",
                            score=max(0.01, 0.5 + delta),
                            support=max(0.01, 0.5 + delta),
                        )
                    }
                )
            )
    return adjusted


def _steered_reading(reading: Reading, req: SculptRequest) -> Reading:
    excluded = {normalize(name) for name in req.exclude_artists}
    existing = [a for a in reading.artists if normalize(a) not in excluded]
    seen = {normalize(a) for a in existing}
    for artist in req.boost_artists:
        norm = normalize(artist)
        if norm and norm not in seen and norm not in excluded:
            seen.add(norm)
            existing.append(artist)
    return reading.model_copy(update={"artists": existing[:20]})


async def _steered_taste(
    session: PoolSession,
    req: SculptRequest,
    filtered_pool: Sequence[Concert],
    services: Services,
) -> tuple[matching.Taste, list[float] | None]:
    """Rocchio query shift + Co-Billing & ListenBrainz neighbour injection for boosted Artists."""
    base = session.taste.to_taste()
    excluded = {normalize(name) for name in req.exclude_artists}

    # Drop excluded Artists from seeds, neighbours and co-billing.
    seeds = [s for s in base.seeds if normalize(s.name) not in excluded]
    neighbours = [n for n in base.neighbours if normalize(n.name) not in excluded]
    cobilled: dict[str, list[matching.CoBilledPeer]] = {
        seed: [p for p in peers if normalize(p.artist_key) not in excluded]
        for seed, peers in base.cobilling.items()
        if normalize(seed) not in excluded
    }
    semantic = {k: v for k, v in base.semantic.items() if k not in excluded}
    query_vec = session.query_embedding

    # Add boosted Artists as seeds and pull their Co-Billing + ListenBrainz/Last.fm neighbours.
    if req.boost_artists:
        existing_seed_keys = {normalize(s.name) for s in seeds}
        new_boosts = [
            name
            for name in req.boost_artists
            if (norm := normalize(name)) and norm not in existing_seed_keys and norm not in excluded
        ]

        async def resolve_boost(name: str) -> SeedArtist:
            # Prefer an MBID already in the pool to avoid unnecessary MusicBrainz calls.
            norm = normalize(name)
            for concert in session.pool:
                for artist in concert.artists:
                    if normalize(artist.name) == norm and artist.mbid:
                        return SeedArtist(
                            name=artist.name,
                            mbid=artist.mbid,
                            tags=list(session.artist_tags.get(artist.mbid, [])),
                        )
            try:
                return await musicbrainz.resolve(services.musicbrainz, services.redis, name)
            except musicbrainz.MusicBrainzError as exc:
                logger.warning("Sculpt MusicBrainz resolve failed: %s", exc)
                return SeedArtist(name=name)

        async def fetch_boost_cobilling() -> dict[str, list[matching.CoBilledPeer]]:
            if not (services.supabase and services.supabase_secret_key and req.boost_artists):
                return {}
            return await cobilling.find_peers(
                services.supabase, services.supabase_secret_key, req.boost_artists
            )

        resolved_boosts, extra_cobilling = await asyncio.gather(
            asyncio.gather(*(resolve_boost(name) for name in new_boosts)),
            fetch_boost_cobilling(),
        )
        seeds.extend(resolved_boosts)
        for seed_name, peers in extra_cobilling.items():
            cobilled[seed_name] = [p for p in peers if normalize(p.artist_key) not in excluded]

        if resolved_boosts:
            try:
                extra_neighbours = await similarity.find_neighbours(
                    services.listenbrainz, services.lastfm, services.redis, resolved_boosts
                )
                neighbours.extend(n for n in extra_neighbours if normalize(n.name) not in excluded)
            except Exception as exc:  # Similarity is best-effort during sculpt.
                logger.warning("Sculpt similarity lookup failed: %s", type(exc).__name__)

    # Rocchio vector update when embeddings & Supabase are active.
    if (
        query_vec
        and (req.boost_artists or req.exclude_artists)
        and services.supabase
        and services.supabase_secret_key
    ):
        liked_keys = [k for n in req.boost_artists if (k := normalize(n))]
        disliked_keys = [k for n in req.exclude_artists if (k := normalize(n))]
        all_keys = list(dict.fromkeys([*liked_keys, *disliked_keys]))
        try:
            stored = await supabase.stored_embeddings(
                services.supabase, services.supabase_secret_key, all_keys
            )
            by_key = {row.artist_key: row.embedding for row in stored}
            liked_vecs = [by_key[k] for k in liked_keys if k in by_key]
            disliked_vecs = [by_key[k] for k in disliked_keys if k in by_key]
            if liked_vecs or disliked_vecs:
                query_vec = rocchio_shift(query_vec, liked_vecs, disliked_vecs)
                artist_names = [a.name for c in filtered_pool for a in c.artists]
                semantic = await embeddings.pool_scores(
                    services.supabase, services.supabase_secret_key, query_vec, artist_names
                )
                semantic = {k: v for k, v in semantic.items() if k not in excluded}
        except supabase.SupabaseError as exc:
            logger.warning("Sculpt Rocchio lookup failed: %s", exc)

    steered = replace(
        base,
        seeds=seeds,
        neighbours=neighbours,
        cobilling=cobilled,
        semantic=semantic,
    )
    return steered, query_vec


async def sculpt_poster(
    search_id: str,
    req: SculptRequest,
    services: Services,
) -> SculptResponse:
    """Sculpt an active Poster session with hard filters, Discovery curve and Rocchio steering."""
    session = await load_session(services.redis, search_id)
    filtered, meta = apply_filters(session.pool, req, session.venue_tiers)

    taste_shifted = bool(req.boost_artists or req.exclude_artists)
    new_search_id = share.new_search_id()

    if not filtered:
        updated_session = session.model_copy()
        await save_session(services.redis, new_search_id, updated_session)
        return SculptResponse(
            search_id=new_search_id,
            poster=Poster(recommendations=[]),
            candidates=Candidates(names=[], total=0),
            meta=meta,
        )

    with telemetry.search() as usage:
        try:
            steered_reading = (
                _steered_reading(session.reading, req) if taste_shifted else session.reading
            )
            if taste_shifted:
                taste, _ = await _steered_taste(session, req, filtered, services)
            else:
                taste = session.taste.to_taste()

            use_taste = session.has_taste or bool(req.boost_artists)
            if use_taste and taste:
                scored = matching.score_concerts(filtered, taste, session.artist_tags)
                adjusted = apply_discovery(
                    scored, req.discovery, session.artist_listeners, session.venue_tiers
                )
                shortlist = matching.shortlist(adjusted)
            else:
                notable = matching.notable(filtered)
                if req.discovery != "balanced":
                    adjusted = apply_discovery(
                        notable, req.discovery, session.artist_listeners, session.venue_tiers
                    )
                    shortlist = matching.shortlist(adjusted)
                else:
                    shortlist = notable

            merged_grades = dict(session.grades)
            merged_reasons = dict(session.reasons)

            if not use_taste or not taste:
                recommendations = assemble.from_notable(shortlist)
            else:
                rows = ranker.rows(shortlist, session.artist_tags)
                ungraded = {cid: row for cid, row in rows.items() if cid not in merged_grades}
                has_cached_for_shortlist = any(cid in merged_grades for cid in rows)

                # Filter-only sculpts reuse cached Jev grades with zero model calls when available.
                # Taste-shifted sculpts (or newly surfaced candidates) grade only ungraded rows.
                should_grade = bool(ungraded) and (taste_shifted or not has_cached_for_shortlist)
                if should_grade:
                    try:
                        new_levels = await ranker.grade(services.jev, steered_reading, ungraded)
                        merged_grades.update(new_levels)
                    except ranker.RankerError as exc:
                        logger.warning("Sculpt ranker failed: %s", exc)

                shortlist_grades = {
                    c.concert.id: merged_grades[c.concert.id]
                    for c in shortlist
                    if c.concert.id in merged_grades
                }
                if shortlist_grades:
                    poster_recs = assemble.from_levels(shortlist_grades, shortlist)
                else:
                    poster_recs = assemble.from_matches(shortlist)

                # Reuse cached reasons; explain only newly promoted recs on taste-shifted sculpts.
                candidates_by_id = {c.concert.id: c for c in shortlist}
                recommendations = [
                    rec.model_copy(update={"reason": merged_reasons[rec.concert.id]})
                    if rec.concert.id in merged_reasons
                    else rec
                    for rec in poster_recs
                ]

                if taste_shifted:
                    need_explain = [
                        (idx, ranker.row(candidates_by_id[rec.concert.id], session.artist_tags))
                        for idx, rec in enumerate(recommendations)
                        if rec.concert.id not in merged_reasons
                        and rec.concert.id in candidates_by_id
                    ]
                    named = [(idx, r) for idx, r in need_explain if r.artist]
                    if named:
                        try:
                            written = await ranker.explain(
                                steered_reading, [r for _, r in named], services.model
                            )
                            for (idx, _), text in zip(named, written, strict=True):
                                if text:
                                    rec = recommendations[idx]
                                    recommendations[idx] = rec.model_copy(update={"reason": text})
                                    merged_reasons[rec.concert.id] = text
                        except ranker.RankerError as exc:
                            logger.warning("Sculpt reasons failed: %s", exc)
        finally:
            with anyio.CancelScope(shield=True):
                await limits.record_spend(services.redis, usage.cost)

    # Persist updated session with accumulated grades & reasons so chained sculpts stay cheap.
    updated_session = session.model_copy(
        update={"grades": merged_grades, "reasons": merged_reasons}
    )
    await save_session(services.redis, new_search_id, updated_session)

    # Keep the sculpted Poster shareable via POST /share.
    if recommendations:
        made = share.Made(
            made=dt.datetime.now(dt.UTC).date(),
            reading=session.reading,
            recommendations=recommendations,
        )
        try:
            await share.keep(services.redis, made, search_id=new_search_id)
        except RedisError as exc:
            logger.warning("Sculpted Poster not kept for sharing: %s", type(exc).__name__)

    return SculptResponse(
        search_id=new_search_id,
        poster=Poster(recommendations=recommendations),
        candidates=Candidates(names=matching.candidate_names(shortlist), total=len(shortlist)),
        meta=meta,
    )
