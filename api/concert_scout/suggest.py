"""Fast Artist autocomplete and related-Artist follow-ups for the Taste Seed picker."""

import asyncio
import datetime as dt
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import cache, catalog, limits
from concert_scout.models import SeedArtist, SimilarArtist, Text
from concert_scout.names import normalize
from concert_scout.pipeline import Services
from concert_scout.sources import lastfm, listenbrainz, musicbrainz

logger = logging.getLogger(__name__)

SUGGEST_PER_HOUR = 180
RELATED_PER_HOUR = 120

DEFAULT_SUGGEST_LIMIT = 8
MAX_SUGGEST_LIMIT = 10
DEFAULT_RELATED_LIMIT = 8
MAX_RELATED_LIMIT = 10
MAX_SEED_LOOKUPS = 5
MAX_INPUT_NAMES = 20
MAX_NAME_LENGTH = 200
MIN_MB_QUERY_LEN = 2

QUERY_CACHE_TTL = dt.timedelta(hours=24)
CATALOG_INDEX_KEY = "suggest:catalog:index"
CATALOG_INDEX_TTL = dt.timedelta(hours=12)
CATALOG_INDEX_CELLS = 12
CATALOG_INDEX_LIMIT = 2500
CATALOG_WINDOW_DAYS = 90
COBILLING_INDEX_KEY = "suggest:catalog:cobilling"
COBILLING_MAX_LINEUP = 15
COBILLING_PEERS_PER_ARTIST = 12

LISTENBRAINZ_WEIGHT = 1.0
COBILLING_WEIGHT = 0.85
LASTFM_WEIGHT = 0.9

_LUCENE_SPECIAL = re.compile(r'[+\-!(){}\[\]^"~*?:\\/]+')


class ArtistSuggestions(BaseModel):
    """Ordered Artist names for autocomplete or related follow-up chips."""

    artists: list[Text]


class _CatalogIndex(BaseModel):
    names: list[str]


class _CoBillingIndex(BaseModel):
    peers: dict[str, list[SimilarArtist]]


def parse_names(raw: Sequence[str]) -> list[str]:
    """Normalize repeated or compact comma-separated `names` query params.

    Repeated params preserve commas inside names like "Tyler, The Creator". A single compact
    comma-separated value like "Khruangbin,Bonobo" splits on commas without breaking single
    Artist names that contain ", ".
    """
    expanded: list[str] = []
    if len(raw) == 1 and "," in raw[0] and ", " not in raw[0]:
        expanded.extend(raw[0].split(","))
    else:
        expanded.extend(raw)

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in expanded:
        name = " ".join(item.split())
        if not name or len(name) > MAX_NAME_LENGTH:
            continue
        key = normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
        if len(cleaned) >= MAX_INPUT_NAMES:
            break
    return cleaned


def _lucene_query(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
    tokens = [token for token in _LUCENE_SPECIAL.sub(" ", query).split() if token]
    if not tokens:
        return f'artist:"{escaped}"'
    if len(tokens) == 1:
        return f'artist:"{escaped}"^3 OR artist:{tokens[0]}*'
    head = " AND ".join(tokens[:-1])
    return f'artist:"{escaped}"^3 OR artist:({head} AND {tokens[-1]}*)'


async def musicbrainz_suggest(
    client: httpx.AsyncClient, redis: Redis, query: str, limit: int = MAX_SUGGEST_LIMIT
) -> list[str]:
    """Prefix-biased Artist search against MusicBrainz, respecting the shared 1 req/s gate."""
    await limits.musicbrainz_call(redis)
    params: dict[str, str | int] = {"query": _lucene_query(query), "limit": max(limit * 2, 16)}
    try:
        response = await client.get("/artist", params=params)
        response.raise_for_status()
        records: list[dict[str, Any]] = response.json()["artists"]
    except httpx.HTTPStatusError as exc:
        raise musicbrainz.MusicBrainzError(f"status {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise musicbrainz.MusicBrainzError(type(exc).__name__) from None
    except (KeyError, TypeError, ValueError) as exc:
        raise musicbrainz.MusicBrainzError(f"unreadable response: {type(exc).__name__}") from None

    seen: set[str] = set()
    names: list[str] = []
    for record in records:
        raw_name = record.get("name")
        if not isinstance(raw_name, str):
            continue
        name = " ".join(raw_name.split())
        key = normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= limit:
            break
    return names


async def _build_catalog_indexes(redis: Redis) -> tuple[list[str], dict[str, list[SimilarArtist]]]:
    """Read upcoming Catalog listings once per TTL window for autocomplete and co-billing."""
    today = dt.datetime.now(dt.UTC).date()
    end = today + dt.timedelta(days=CATALOG_WINDOW_DAYS)
    try:
        cells = await catalog.busiest_cells(redis, today, end, CATALOG_INDEX_CELLS)
        if not cells:
            return [], {}
        listings = await catalog.listings_in(redis, cells, today, end)
    except RedisError as exc:
        logger.warning("Catalog suggest index failed: %s", type(exc).__name__)
        return [], {}

    counts: dict[str, int] = defaultdict(int)
    display: dict[str, str] = {}
    pair_weights: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for listing in listings:
        concert = listing.concert
        lineup_keys: list[str] = []
        for artist in concert.artists:
            name = " ".join(artist.name.split())
            key = normalize(name)
            if not key:
                continue
            counts[key] += 1
            display.setdefault(key, name)
            if key not in lineup_keys:
                lineup_keys.append(key)

        if 2 <= len(lineup_keys) <= COBILLING_MAX_LINEUP:
            weight = 1.0 if len(lineup_keys) <= 5 else 0.45
            for idx, left in enumerate(lineup_keys):
                for right in lineup_keys[idx + 1 :]:
                    pair_weights[left][right] += weight
                    pair_weights[right][left] += weight

    ordered_keys = sorted(counts, key=lambda key: (-counts[key], display[key].casefold()))
    names = [display[key] for key in ordered_keys[:CATALOG_INDEX_LIMIT]]

    peers: dict[str, list[SimilarArtist]] = {}
    for key, neighbours in pair_weights.items():
        ranked = sorted(
            neighbours.items(), key=lambda item: (-item[1], display[item[0]].casefold())
        )
        peers[key] = [
            SimilarArtist(name=display[peer_key], score=score)
            for peer_key, score in ranked[:COBILLING_PEERS_PER_ARTIST]
        ]

    if names:
        await cache.write(redis, CATALOG_INDEX_KEY, _CatalogIndex(names=names), CATALOG_INDEX_TTL)
        await cache.write(
            redis, COBILLING_INDEX_KEY, _CoBillingIndex(peers=peers), CATALOG_INDEX_TTL
        )
    return names, peers


async def catalog_artists(redis: Redis) -> list[str]:
    """Cached touring Artist names from the JamBase Catalog."""
    if cached := await cache.read(redis, CATALOG_INDEX_KEY, _CatalogIndex):
        return cached.names
    names, _ = await _build_catalog_indexes(redis)
    return names


async def cobilling_peers(redis: Redis, name: str) -> list[SimilarArtist]:
    """Co-billed peers from the cached Catalog Lineups (empty when no Catalog data exists)."""
    key = normalize(name)
    if not key:
        return []
    if cached := await cache.read(redis, COBILLING_INDEX_KEY, _CoBillingIndex):
        return cached.peers.get(key, [])
    _, peers = await _build_catalog_indexes(redis)
    return peers.get(key, [])


def _match_rank(norm_name: str, norm_query: str) -> int | None:
    if norm_name == norm_query:
        return 0
    if norm_name.startswith(norm_query):
        return 1
    if any(word.startswith(norm_query) for word in norm_name.split()):
        return 2
    if norm_query in norm_name:
        return 3
    return None


async def suggest_artists(
    query: str, services: Services, limit: int = DEFAULT_SUGGEST_LIMIT
) -> list[str]:
    """Fast Artist autocomplete blending the Catalog cache and MusicBrainz."""
    cleaned = " ".join(query.split())
    norm_q = normalize(cleaned)
    if not cleaned or not norm_q:
        return []
    cap = max(1, min(limit, MAX_SUGGEST_LIMIT))

    cache_key = f"suggest:q:{norm_q}"
    if cached := await cache.read(services.redis, cache_key, ArtistSuggestions):
        return cached.artists[:cap]

    local_names = await catalog_artists(services.redis)
    catalog_hits: list[tuple[int, int, str]] = []
    for index, name in enumerate(local_names):
        rank = _match_rank(normalize(name), norm_q)
        if rank is not None:
            catalog_hits.append((rank, index, name))
    catalog_hits.sort(key=lambda item: (item[0], item[1]))
    catalog_top = [name for _, _, name in catalog_hits[: MAX_SUGGEST_LIMIT * 2]]

    mb_names: list[str] = []
    mb_ok = False
    if len(cleaned) >= MIN_MB_QUERY_LEN:
        try:
            mb_names = await musicbrainz_suggest(
                services.musicbrainz, services.redis, cleaned, MAX_SUGGEST_LIMIT
            )
            mb_ok = True
        except musicbrainz.MusicBrainzError as exc:
            logger.warning("MusicBrainz suggest failed: %s", exc)

    # Rank combined results: exact match, prefix match, word-start match, then MusicBrainz/Catalog.
    catalog_keys = {normalize(name) for name in catalog_top}
    scored: dict[str, tuple[tuple[int, int, int], str]] = {}

    def record(name: str, source_order: int, position: int) -> None:
        key = normalize(name)
        if not key:
            return
        match_rank = _match_rank(key, norm_q)
        tier = match_rank if match_rank is not None else 4
        # Prefer Artists present in both Catalog and MusicBrainz on prefix/exact ties.
        in_catalog = 0 if key in catalog_keys else 1
        sort_key = (tier, in_catalog if tier <= 2 else source_order, position)
        existing = scored.get(key)
        if existing is None or sort_key < existing[0]:
            scored[key] = (sort_key, name)

    for idx, name in enumerate(mb_names):
        record(name, source_order=0, position=idx)
    for idx, name in enumerate(catalog_top):
        record(name, source_order=1, position=idx)

    merged = [name for _, name in sorted(scored.values(), key=lambda item: item[0])]
    trimmed = merged[:MAX_SUGGEST_LIMIT]

    if mb_ok or (len(cleaned) < MIN_MB_QUERY_LEN and trimmed):
        await cache.write(
            services.redis, cache_key, ArtistSuggestions(artists=trimmed), QUERY_CACHE_TTL
        )
    return trimmed[:cap]


def _normalize_scores(artists: Sequence[SimilarArtist]) -> list[tuple[SimilarArtist, float]]:
    top = max((artist.score for artist in artists), default=0.0) or 1.0
    return [(artist, max(artist.score, 0.0) / top) for artist in artists]


async def _seed_related(
    seed_name: str, services: Services
) -> list[tuple[SimilarArtist, float, float]]:
    """Fetch 1-hop related Artists for one seed from ListenBrainz, Co-Billing, and Last.fm."""
    try:
        resolved = await musicbrainz.resolve(services.musicbrainz, services.redis, seed_name)
    except musicbrainz.MusicBrainzError as exc:
        logger.warning("MusicBrainz resolve failed for related lookup: %s", exc)
        resolved = SeedArtist(name=seed_name)

    lb_similar: list[SimilarArtist] = []
    if resolved.mbid:
        try:
            lb_similar = await listenbrainz.similar_artists(
                services.listenbrainz, services.redis, resolved.mbid
            )
        except listenbrainz.ListenBrainzError as exc:
            logger.warning("ListenBrainz related lookup failed: %s", exc)

    co_billed = await cobilling_peers(services.redis, resolved.name)

    lastfm_similar: list[SimilarArtist] = []
    if not lb_similar and services.lastfm:
        try:
            lastfm_similar = await lastfm.similar_artists(
                services.lastfm, services.redis, resolved.name
            )
        except lastfm.LastfmError as exc:
            logger.warning("Last.fm related fallback failed: %s", exc)

    weighted: list[tuple[SimilarArtist, float, float]] = []
    for artist, ratio in _normalize_scores(lb_similar):
        weighted.append((artist, ratio, LISTENBRAINZ_WEIGHT))
    for artist, ratio in _normalize_scores(co_billed):
        weighted.append((artist, ratio, COBILLING_WEIGHT))
    for artist, ratio in _normalize_scores(lastfm_similar):
        weighted.append((artist, ratio, LASTFM_WEIGHT))
    return weighted


async def related_artists(
    names: Sequence[str], services: Services, limit: int = DEFAULT_RELATED_LIMIT
) -> list[str]:
    """Return 6 to 10 related Artists across the visitor's picked seeds, excluding picked names."""
    parsed = parse_names(names)
    if not parsed:
        return []
    cap = max(1, min(limit, MAX_RELATED_LIMIT))
    excluded = {normalize(name) for name in parsed}

    # Query the most recently picked seeds first so follow-up chips react to the latest taps.
    active_seeds = list(reversed(parsed[-MAX_SEED_LOOKUPS:]))
    groups = await asyncio.gather(*(_seed_related(seed, services) for seed in active_seeds))

    totals: dict[str, float] = defaultdict(float)
    display: dict[str, str] = {}
    for seed_index, group in enumerate(groups):
        recency = 1.0 - 0.05 * seed_index
        per_seed_best: dict[str, tuple[float, str]] = {}
        for artist, ratio, weight in group:
            name = " ".join(artist.name.split())
            key = normalize(name)
            if not key or key in excluded:
                continue
            contribution = ratio * weight * recency
            previous = per_seed_best.get(key)
            if previous is None or contribution > previous[0]:
                per_seed_best[key] = (contribution, name)
        for key, (contribution, name) in per_seed_best.items():
            totals[key] += contribution
            display.setdefault(key, name)

    ranked_keys = sorted(totals, key=lambda key: (-totals[key], display[key].casefold()))
    return [display[key] for key in ranked_keys[:cap]]
