"""Fallback and partial-result contracts, without inventing any vendor response body."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis

from concert_scout import similarity
from concert_scout.models import SeedArtist, SimilarArtist
from concert_scout.sources import lastfm, listenbrainz
from tests.contracts import forbidden_http

SEED = SeedArtist(name="Seed", mbid="seed")
NEAR = SimilarArtist(name="Near", mbid="near", score=1)


@pytest.mark.parametrize("labs", [[], listenbrainz.ListenBrainzError("down")])
async def test_missing_primary_similarity_falls_back_without_losing_the_seed(
    monkeypatch: pytest.MonkeyPatch,
    labs: list[SimilarArtist] | Exception,
) -> None:
    first = (
        AsyncMock(side_effect=labs) if isinstance(labs, Exception) else AsyncMock(return_value=labs)
    )
    backup = AsyncMock(side_effect=[[NEAR], []])
    monkeypatch.setattr(listenbrainz, "similar_artists", first)
    monkeypatch.setattr(lastfm, "similar_artists", backup)
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_http)) as client:
        found = await similarity.find_neighbours(client, client, FakeAsyncRedis(), [SEED])
    assert [(n.name, n.seed, n.hops) for n in found] == [("Near", "Seed", 1)]


async def test_a_failed_second_hop_keeps_the_first_and_does_not_switch_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = AsyncMock(side_effect=[[NEAR], listenbrainz.ListenBrainzError("down")])
    backup = AsyncMock(side_effect=AssertionError("must not change sources"))
    monkeypatch.setattr(listenbrainz, "similar_artists", primary)
    monkeypatch.setattr(lastfm, "similar_artists", backup)
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_http)) as client:
        found = await similarity.find_neighbours(client, client, FakeAsyncRedis(), [SEED])
    assert [(n.name, n.hops) for n in found] == [("Near", 1)]
    backup.assert_not_awaited()
