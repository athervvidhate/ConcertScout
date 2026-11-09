"""A silver standard for Searches that name an Artist: who two outside services call similar.

Deezer's related Artists and Last.fm's similar Artists come from listening data that the
pipeline never reads, because it asks ListenBrainz and calls Last.fm only when ListenBrainz has
nothing. So agreement with them is evidence the pipeline did not grade its own homework. It is
consistency, not quality: both services favour popular Artists, and neither knows the visitor.

Deezer allows only private, non-commercial use, so its answers stay in the private Snapshot
folder and never reach the app or a page.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fakeredis import FakeAsyncRedis

from concert_scout.assemble import POSTER_SIZE
from concert_scout.names import normalize
from concert_scout.sources import http, lastfm
from evals import snapshots

DEEZER_URL = "https://api.deezer.com"
# Deezer publishes no limit; a reported 50 requests per 5 seconds is well above this pace.
DEEZER_GAP_SECONDS = 0.2
CACHE = snapshots.SNAPSHOTS / "silver-cache.json"


class Silver:
    """Neighbours per seed, cached on disk so repeat eval runs make no calls."""

    def __init__(self, lastfm_key: str | None) -> None:
        self.deezer = http.make_client(DEEZER_URL, {})
        self.lastfm = lastfm.make_client(lastfm_key) if lastfm_key else None
        self.cache: dict[str, list[str]] = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    async def aclose(self) -> None:
        await self.deezer.aclose()
        if self.lastfm:
            await self.lastfm.aclose()
        snapshots.SNAPSHOTS.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, sort_keys=True))

    async def neighbours(self, seeds: Sequence[str]) -> set[str]:
        """Normalized names either service lists as directly similar to any seed."""
        found: set[str] = set()
        for seed in seeds:
            found |= set(await self._cached(f"deezer:{normalize(seed)}", self._deezer, seed))
            if self.lastfm:
                found |= set(await self._cached(f"lastfm:{normalize(seed)}", self._lastfm, seed))
        return found - {normalize(seed) for seed in seeds}

    async def _cached(
        self, key: str, fetch: Callable[[str], Awaitable[list[str]]], seed: str
    ) -> list[str]:
        if key not in self.cache:
            self.cache[key] = await fetch(seed)
        return self.cache[key]

    async def _deezer(self, seed: str) -> list[str]:
        """Deezer joins by name, so a shared name takes the Artist with the most fans."""
        found = await self._deezer_get("/search/artist", {"q": seed})
        same = [a for a in found if normalize(a["name"]) == normalize(seed)]
        if not same:
            return []
        artist = max(same, key=lambda a: a.get("nb_fan", 0))
        related = await self._deezer_get(f"/artist/{artist['id']}/related", {"limit": "50"})
        return [normalize(a["name"]) for a in related]

    async def _deezer_get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        await asyncio.sleep(DEEZER_GAP_SECONDS)
        response = await self.deezer.get(path, params=params)
        response.raise_for_status()
        return response.json().get("data", [])

    async def _lastfm(self, seed: str) -> list[str]:
        assert self.lastfm
        similar = await lastfm.similar_artists(self.lastfm, FakeAsyncRedis(), seed)
        return [normalize(a.name) for a in similar]


def recall(poster: set[str], available: set[str], seeds: int) -> float | None:
    """Silver Artists on the Poster, out of those playing, capped by the Poster's open places.

    Seeds take their places on the Poster first, so a Search with 20 silver Artists playing can
    show at most the rest.
    """
    room = min(len(available), max(POSTER_SIZE - seeds, 0))
    return len(poster & available) / room if room else None
