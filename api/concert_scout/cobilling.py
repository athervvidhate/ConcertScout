"""Live Co-Billing Graph mined from Catalog and Ticketmaster Lineups.

Promoters and booking agents curate openers and co-headliners to match each other's live
audiences. This module extracts bill-size-weighted Lineups, records them into Supabase with
per-Concert deduplication, and queries co-billed peers in one batched RPC per Search.

All network calls gracefully no-op whenever Supabase is unconfigured or unavailable.
"""

import datetime as dt
import logging
from collections.abc import Sequence

import httpx
from pydantic import SecretStr

from concert_scout.matching import CoBilledPeer
from concert_scout.models import Concert
from concert_scout.names import normalize
from concert_scout.sources import supabase

logger = logging.getLogger(__name__)

MIN_LINEUP = 2
CLUB_MAX = 5
SHOWCASE_MAX = 15
FESTIVAL_MAX = 40

CLUB_WEIGHT = 1.0
SHOWCASE_WEIGHT = 0.45
FESTIVAL_WEIGHT = 0.15

MAX_KEY_LENGTH = 200
INGEST_BATCH_SIZE = 100
NEIGHBOR_LIMIT = 50


def bill_weight(artist_count: int) -> float:
    """Weight for a Lineup by its distinct Artist count.

    2..5 Artists (club/theater bill) = 1.0, 6..15 (showcase/mini-fest) = 0.45,
    16..40 (mid festival) = 0.15, and solo or >40-Artist mega-festivals = 0.0.
    """
    if artist_count < MIN_LINEUP or artist_count > FESTIVAL_MAX:
        return 0.0
    if artist_count <= CLUB_MAX:
        return CLUB_WEIGHT
    if artist_count <= SHOWCASE_MAX:
        return SHOWCASE_WEIGHT
    return FESTIVAL_WEIGHT


def extract_bills(concerts: Sequence[Concert], today: dt.date) -> list[supabase.CoBillingBill]:
    """Eligible deduplicated Concert Lineups ready for co-billing accumulation.

    Deduplicates Concerts by ID within the batch, normalizes and sorts Artist keys so pairs
    are canonical, and drops solo shows and >40-Artist mega-festivals.
    """
    seen_ids: set[str] = set()
    bills: list[supabase.CoBillingBill] = []
    for concert in concerts:
        concert_id = concert.id.strip()
        if not concert_id or len(concert_id) > MAX_KEY_LENGTH or concert_id in seen_ids:
            continue
        seen_ids.add(concert_id)
        artists = sorted(
            {
                key
                for artist in concert.artists
                if (key := normalize(artist.name)) and len(key) <= MAX_KEY_LENGTH
            }
        )
        weight = bill_weight(len(artists))
        if weight <= 0:
            continue
        bills.append(
            supabase.CoBillingBill(
                concert_id=concert_id,
                concert_date=concert.date or today,
                weight=weight,
                artists=artists,
            )
        )
    return bills


async def ingest_concerts(
    client: httpx.AsyncClient | None,
    secret_key: SecretStr | None,
    concerts: Sequence[Concert],
    today: dt.date,
) -> int:
    """Record unseen Concert bills into Supabase and accumulate co-billing edge weights.

    Gracefully no-ops when Supabase is unconfigured or unavailable, returning 0 on error.
    """
    if not client or not secret_key:
        return 0
    bills = extract_bills(concerts, today)
    if not bills:
        return 0
    recorded = 0
    for start in range(0, len(bills), INGEST_BATCH_SIZE):
        batch = bills[start : start + INGEST_BATCH_SIZE]
        try:
            recorded += await supabase.record_cobilling_bills(client, secret_key, batch)
        except supabase.SupabaseError as exc:
            logger.warning("Co-billing ingest failed: %s", exc)
            break
    return recorded


async def find_peers(
    client: httpx.AsyncClient | None,
    secret_key: SecretStr | None,
    seeds: Sequence[str],
    limit: int = NEIGHBOR_LIMIT,
) -> dict[str, list[CoBilledPeer]]:
    """Batched co-billing peers for seed Artist names, keyed by each seed's display name.

    Gracefully returns an empty mapping when Supabase is unconfigured or unavailable.
    """
    if not client or not secret_key:
        return {}
    by_key: dict[str, str] = {}
    for name in seeds:
        key = normalize(name)
        if key and len(key) <= MAX_KEY_LENGTH:
            by_key.setdefault(key, name)
    if not by_key:
        return {}
    try:
        edges = await supabase.cobilling_neighbors(client, secret_key, list(by_key), limit)
    except supabase.SupabaseError as exc:
        logger.warning("Co-billing lookup failed: %s", exc)
        return {}
    peers: dict[str, list[CoBilledPeer]] = {}
    for edge in edges:
        if seed_name := by_key.get(edge.seed):
            peers.setdefault(seed_name, []).append(
                CoBilledPeer(
                    artist_key=edge.peer,
                    weight=edge.weight,
                    shared_shows=edge.shared_shows,
                )
            )
    return peers
