"""Artist autocomplete and related-Artist follow-up contracts."""

import datetime as dt
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import catalog, suggest
from concert_scout.models import Artist, Concert, SeedArtist, SimilarArtist
from concert_scout.sources import jambase, lastfm, listenbrainz, musicbrainz
from tests.contracts import install_sources
from tests.test_app import api_for


@pytest.fixture(autouse=True)
def sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


def _listing(concert_id: str, artists: list[str], day: dt.date) -> jambase.Listing:
    return jambase.Listing(
        concert=Concert(
            id=concert_id,
            name=f"{artists[0]} Live",
            url=f"https://tickets.example/{concert_id}",
            artists=[Artist(name=name) for name in artists],
            source="jambase",
            date=day,
            venue="Test Room",
            city="San Francisco",
            region="CA",
        ),
        latitude=37.77,
        longitude=-122.42,
    )


def test_parse_names_handles_repeated_params_compact_csv_and_commas_in_names() -> None:
    assert suggest.parse_names(["Khruangbin", "Tyler, The Creator", "khruangbin"]) == [
        "Khruangbin",
        "Tyler, The Creator",
    ]
    assert suggest.parse_names(["Tyler, The Creator"]) == ["Tyler, The Creator"]
    assert suggest.parse_names(["Khruangbin,Bonobo,Four Tet"]) == [
        "Khruangbin",
        "Bonobo",
        "Four Tet",
    ]
    assert suggest.parse_names(["   ", ""]) == []


async def test_suggest_merges_catalog_and_musicbrainz_and_caches_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    today = dt.datetime.now(dt.UTC).date()
    day = today + dt.timedelta(days=10)
    await catalog.store(
        redis,
        [
            _listing("jambase:1", ["Khruangbin", "Hermanos Gutiérrez"], day),
            _listing("jambase:2", ["Khruangbin", "Glass Beams"], day + dt.timedelta(days=1)),
            _listing("jambase:3", ["Khris Royal"], day + dt.timedelta(days=2)),
        ],
        [],
        today,
    )

    mb_mock = AsyncMock(return_value=["Khruangbin", "Khrung", "Another Khru Act"])
    monkeypatch.setattr(suggest, "musicbrainz_suggest", mb_mock)

    async with api_for(redis) as api:
        first = await api.get("/artists/suggest", params={"q": "khru"})
        second = await api.get("/artists/suggest", params={"q": "Khru"})

    assert first.status_code == 200
    assert first.json()["artists"] == ["Khruangbin", "Khrung", "Another Khru Act"]
    # Second request with equivalent normalized query hits Redis cache with no MusicBrainz call.
    assert second.status_code == 200
    assert second.json() == first.json()
    assert mb_mock.await_count == 1


async def test_suggest_falls_back_to_catalog_when_musicbrainz_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    today = dt.datetime.now(dt.UTC).date()
    await catalog.store(
        redis,
        [_listing("jambase:1", ["Tame Impala", "Tame The Beast"], today + dt.timedelta(days=7))],
        [],
        today,
    )
    monkeypatch.setattr(
        suggest,
        "musicbrainz_suggest",
        AsyncMock(side_effect=musicbrainz.MusicBrainzError("status 503")),
    )

    async with api_for(redis) as api:
        response = await api.get("/artists/suggest", params={"q": "Tame"})

    assert response.status_code == 200
    assert response.json()["artists"] == ["Tame Impala", "Tame The Beast"]


async def test_suggest_single_char_skips_musicbrainz_and_uses_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    today = dt.datetime.now(dt.UTC).date()
    await catalog.store(
        redis,
        [_listing("jambase:1", ["Khruangbin", "Bonobo"], today + dt.timedelta(days=7))],
        [],
        today,
    )
    mb_mock = AsyncMock(return_value=["ShouldNotBeCalled"])
    monkeypatch.setattr(suggest, "musicbrainz_suggest", mb_mock)

    async with api_for(redis) as api:
        response = await api.get("/artists/suggest", params={"q": "k"})

    assert response.status_code == 200
    assert response.json()["artists"] == ["Khruangbin"]
    mb_mock.assert_not_awaited()


async def test_musicbrainz_suggest_dedups_and_paces(monkeypatch: pytest.MonkeyPatch) -> None:
    paced = AsyncMock()
    monkeypatch.setattr("concert_scout.limits.musicbrainz_call", paced)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ws/2/artist"
        assert "khru*" in request.url.params["query"]
        return httpx.Response(
            200,
            json={
                "artists": [
                    {"name": "Khruangbin", "score": 100},
                    {"name": "khruangbin", "score": 90},
                    {"name": "Khris Royal", "score": 82},
                ]
            },
        )

    redis = FakeAsyncRedis()
    async with musicbrainz.make_client(httpx.MockTransport(handler)) as client:
        names = await suggest.musicbrainz_suggest(client, redis, "khru", limit=5)

    assert names == ["Khruangbin", "Khris Royal"]
    paced.assert_awaited_once()


async def test_suggest_validation_and_visitor_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suggest, "SUGGEST_PER_HOUR", 2)
    monkeypatch.setattr(suggest, "musicbrainz_suggest", AsyncMock(return_value=["Bonobo"]))
    redis = FakeAsyncRedis()

    async with api_for(redis) as api:
        blank = await api.get("/artists/suggest", params={"q": "   "})
        missing = await api.get("/artists/suggest")
        first = await api.get("/artists/suggest", params={"q": "bon"})
        second = await api.get("/artists/suggest", params={"q": "bono"})
        third = await api.get("/artists/suggest", params={"q": "bonob"})

    assert blank.status_code == 422
    assert blank.json()["code"] == "invalid_artist"
    assert missing.status_code == 422
    assert missing.json()["code"] == "invalid_artist"
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["code"] == "visitor_limit"


async def test_related_blends_listenbrainz_and_cobilling_and_excludes_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeAsyncRedis()
    today = dt.datetime.now(dt.UTC).date()
    # Co-billing in Catalog links Khruangbin <-> Glass Beams & Hermanos Gutiérrez.
    await catalog.store(
        redis,
        [
            _listing(
                "jambase:1",
                ["Khruangbin", "Glass Beams", "Hermanos Gutiérrez"],
                today + dt.timedelta(days=5),
            ),
            _listing("jambase:2", ["Khruangbin", "Glass Beams"], today + dt.timedelta(days=6)),
        ],
        [],
        today,
    )

    mbids = {"khruangbin": "mbid-khru", "bonobo": "mbid-bonobo"}

    async def resolve_seed(_: httpx.AsyncClient, __: object, name: str) -> SeedArtist:
        return SeedArtist(name=name, mbid=mbids.get(name.casefold()))

    similar_map = {
        "mbid-khru": [
            SimilarArtist(name="Bonobo", mbid="mbid-bonobo", score=100),  # already selected!
            SimilarArtist(name="Parcels", mbid="mbid-parcels", score=90),
            SimilarArtist(name="Toro y Moi", mbid="mbid-toro", score=80),
            SimilarArtist(name="BadBadNotGood", mbid="mbid-bbng", score=70),
            SimilarArtist(name="Skinshape", mbid="mbid-skin", score=60),
        ],
        "mbid-bonobo": [
            SimilarArtist(name="Khruangbin", mbid="mbid-khru", score=100),  # already selected!
            SimilarArtist(name="Four Tet", mbid="mbid-4t", score=95),
            SimilarArtist(name="Parcels", mbid="mbid-parcels", score=85),  # shared by both seeds!
            SimilarArtist(name="Caribou", mbid="mbid-caribou", score=75),
            SimilarArtist(name="Floating Points", mbid="mbid-fp", score=65),
        ],
    }

    async def fake_lb(_: httpx.AsyncClient, __: object, mbid: str) -> list[SimilarArtist]:
        return similar_map.get(mbid, [])

    monkeypatch.setattr(musicbrainz, "resolve", AsyncMock(side_effect=resolve_seed))
    monkeypatch.setattr(listenbrainz, "similar_artists", AsyncMock(side_effect=fake_lb))

    async with api_for(redis) as api:
        response = await api.get(
            "/artists/related", params=[("names", "Khruangbin"), ("names", "Bonobo")]
        )

    assert response.status_code == 200
    artists = response.json()["artists"]
    assert 6 <= len(artists) <= 10
    # Selected Artists never appear in follow-up chips.
    assert "Khruangbin" not in artists
    assert "Bonobo" not in artists
    # Overlap across both seeds pushes Parcels to the top, and co-billed Glass Beams is included.
    assert artists[0] == "Parcels"
    assert "Glass Beams" in artists


async def test_related_follows_the_newest_picks_which_the_picker_sends_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def seed(_: httpx.AsyncClient, __: object, name: str) -> SeedArtist:
        return SeedArtist(name=name, mbid=name)

    resolve = AsyncMock(side_effect=seed)

    async def similar(_: httpx.AsyncClient, __: object, mbid: str) -> list[SimilarArtist]:
        # Every rapper shares one neighbour, which a sum across seeds would put first.
        shared = [SimilarArtist(name="Rap Star", mbid="rap-star", score=95)]
        own = [SimilarArtist(name=f"Like {mbid}", mbid=f"like-{mbid}", score=90)]
        return own if mbid == "Fred again.." else shared + own

    monkeypatch.setattr(musicbrainz, "resolve", resolve)
    monkeypatch.setattr(listenbrainz, "similar_artists", AsyncMock(side_effect=similar))
    rap = [f"Rapper {n}" for n in range(1, 8)]
    async with api_for(FakeAsyncRedis()) as api:
        response = await api.get(
            "/artists/related", params=[("names", n) for n in ["Fred again..", *rap]]
        )

    looked_up = [call.args[2] for call in resolve.await_args_list]
    assert looked_up[0] == "Fred again.." and "Rapper 7" not in looked_up
    assert response.json()["artists"][:2] == ["Like Fred again..", "Rap Star"]


async def test_related_falls_back_to_lastfm_when_listenbrainz_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        musicbrainz,
        "resolve",
        AsyncMock(return_value=SeedArtist(name="Tyler, The Creator", mbid="mbid-tyler")),
    )
    monkeypatch.setattr(
        listenbrainz,
        "similar_artists",
        AsyncMock(side_effect=listenbrainz.ListenBrainzError("status 503")),
    )
    monkeypatch.setattr(
        lastfm,
        "similar_artists",
        AsyncMock(
            return_value=[
                SimilarArtist(name="Frank Ocean", score=0.95),
                SimilarArtist(name="Steve Lacy", score=0.88),
                SimilarArtist(name="Earl Sweatshirt", score=0.84),
                SimilarArtist(name="Kali Uchis", score=0.79),
                SimilarArtist(name="Solange", score=0.72),
                SimilarArtist(name="Thundercat", score=0.69),
            ]
        ),
    )

    async with api_for(lastfm_key=SecretStr("test-lastfm")) as api:
        response = await api.get("/artists/related", params={"names": "Tyler, The Creator"})

    assert response.status_code == 200
    assert response.json()["artists"] == [
        "Frank Ocean",
        "Steve Lacy",
        "Earl Sweatshirt",
        "Kali Uchis",
        "Solange",
        "Thundercat",
    ]


async def test_related_validation_and_visitor_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suggest, "RELATED_PER_HOUR", 2)
    monkeypatch.setattr(
        listenbrainz,
        "similar_artists",
        AsyncMock(return_value=[SimilarArtist(name="Parcels", score=90)]),
    )
    monkeypatch.setattr(
        musicbrainz,
        "resolve",
        AsyncMock(return_value=SeedArtist(name="Khruangbin", mbid="mbid-khru")),
    )
    redis = FakeAsyncRedis()

    async with api_for(redis) as api:
        empty = await api.get("/artists/related")
        blank = await api.get("/artists/related", params={"names": "   "})
        first = await api.get("/artists/related", params={"names": "Khruangbin"})
        second = await api.get("/artists/related", params={"names": "Khruangbin"})
        third = await api.get("/artists/related", params={"names": "Khruangbin"})

    assert empty.status_code == 422
    assert blank.status_code == 422
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["code"] == "visitor_limit"
