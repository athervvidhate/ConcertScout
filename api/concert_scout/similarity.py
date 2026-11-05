import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

import httpx
from redis.asyncio import Redis

from concert_scout.matching import Neighbour
from concert_scout.models import SeedArtist, SimilarArtist
from concert_scout.sources import lastfm, listenbrainz

logger = logging.getLogger(__name__)

# Two hops start from this many of a seed's closest neighbours.
SECOND_HOP_FROM = 15
# ListenBrainz Labs publishes no rate limit, so a Search stays gentle with it.
MAX_CONCURRENT = 4

type Lookup = Callable[[SeedArtist | SimilarArtist], Awaitable[list[SimilarArtist]]]


async def find_neighbours(
    listenbrainz_client: httpx.AsyncClient,
    lastfm_client: httpx.AsyncClient | None,
    redis: Redis,
    seeds: Sequence[SeedArtist],
) -> list[Neighbour]:
    """Every seed's neighbours at one and two hops. Failures leave a seed with fewer, never raise."""
    slots = asyncio.Semaphore(MAX_CONCURRENT)

    async def from_listenbrainz(artist: SeedArtist | SimilarArtist) -> list[SimilarArtist]:
        if artist.mbid is None:
            return []
        async with slots:
            return await listenbrainz.similar_artists(listenbrainz_client, redis, artist.mbid)

    lookups: list[Lookup] = [from_listenbrainz]

    if lastfm_client:
        client = lastfm_client

        async def from_lastfm(artist: SeedArtist | SimilarArtist) -> list[SimilarArtist]:
            return await lastfm.similar_artists(client, redis, artist.name)

        lookups.append(from_lastfm)

    found = await asyncio.gather(*(_neighbours(seed, lookups) for seed in seeds))
    return [neighbour for group in found for neighbour in group]


def closest(neighbours: Sequence[Neighbour], count: int) -> list[str]:
    """The names of the closest neighbours, with one hop always ahead of two."""
    ranked = sorted(neighbours, key=lambda n: (n.hops, -n.closeness))
    return list(dict.fromkeys(n.name for n in ranked))[:count]


async def _neighbours(seed: SeedArtist, lookups: Sequence[Lookup]) -> list[Neighbour]:
    for lookup in lookups:
        try:
            first_hop = await lookup(seed)
        except (listenbrainz.ListenBrainzError, lastfm.LastfmError) as exc:
            logger.warning("Similar Artists failed: %s", exc)
            continue
        if first_hop:
            # The second hop stays on the source that answered, so a dead one costs a single call.
            sources = first_hop[:SECOND_HOP_FROM]
            second_hop = await asyncio.gather(*(_second_hop(a, lookup) for a in sources))
            return _ranked(seed, first_hop, second_hop)
    return []


async def _second_hop(artist: SimilarArtist, lookup: Lookup) -> list[SimilarArtist]:
    try:
        return await lookup(artist)
    except (listenbrainz.ListenBrainzError, lastfm.LastfmError) as exc:
        logger.warning("Similar Artists failed: %s", exc)
        return []


def _ranked(
    seed: SeedArtist, first_hop: list[SimilarArtist], second_hop: list[list[SimilarArtist]]
) -> list[Neighbour]:
    closeness = _closeness(first_hop)
    neighbours = [
        Neighbour(name=a.name, mbid=a.mbid, hops=1, closeness=near, seed=seed.name)
        for a, near in zip(first_hop, closeness, strict=True)
    ]
    for link, artists in zip(closeness, second_hop, strict=False):
        neighbours += [
            Neighbour(name=a.name, mbid=a.mbid, hops=2, closeness=link * near, seed=seed.name)
            for a, near in zip(artists, _closeness(artists), strict=True)
        ]
    return neighbours


def _closeness(artists: list[SimilarArtist]) -> list[float]:
    """Each Artist's score as a share of the top one, because sources score on different scales."""
    top = max((a.score for a in artists), default=0) or 1
    return [a.score / top for a in artists]
