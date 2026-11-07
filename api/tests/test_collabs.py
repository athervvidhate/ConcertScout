"""A tour billed as one name opens each of its Artists, and a real duo stays whole."""

from unittest.mock import AsyncMock

import pytest

from concert_scout import pipeline
from concert_scout.models import ArtistProfile
from concert_scout.names import collab_names

PAGE = "https://open.spotify.com/artist/x"


@pytest.mark.parametrize(
    ("billing", "names"),
    [
        ("Usher Raymond & Chris Brown", ["Usher Raymond", "Chris Brown"]),
        ("Disclosure x Kaytranada", ["Disclosure", "Kaytranada"]),
        ("One, Two + Three", ["One", "Two", "Three"]),
        ("Halsey with Bring Me The Horizon", ["Halsey", "Bring Me The Horizon"]),
        ("Mumford and Sons", []),
        ("Lupe Fiasco", []),
        ("X Ambassadors", []),
        ("Tyler, the Creator", ["Tyler", "the Creator"]),
    ],
)
def test_billings_split_on_collab_joins(billing: str, names: list[str]) -> None:
    assert collab_names(billing) == names


def known(*pages: str) -> AsyncMock:
    async def profile(name: str, _: object) -> ArtistProfile:
        return ArtistProfile(name=name, spotify_url=PAGE if name in pages else None)

    return AsyncMock(side_effect=profile)


async def test_a_real_duo_keeps_its_own_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "find_artist_profile", known("Above & Beyond"))
    profiles = await pipeline.find_artist_profiles("Above & Beyond", AsyncMock())
    assert [p.name for p in profiles] == ["Above & Beyond"]


async def test_a_billed_tour_opens_each_artist_through_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "find_artist_profile", known("Usher", "Chris Brown"))
    monkeypatch.setattr(pipeline.musicbrainz, "filed_name", AsyncMock(return_value="Usher"))
    profiles = await pipeline.find_artist_profiles("Usher Raymond & Chris Brown", AsyncMock())
    assert [(p.name, p.spotify_url) for p in profiles] == [("Usher", PAGE), ("Chris Brown", PAGE)]


async def test_a_musicbrainz_outage_keeps_the_billed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from concert_scout.sources.musicbrainz import MusicBrainzError

    monkeypatch.setattr(pipeline, "find_artist_profile", known("Chris Brown"))
    down = AsyncMock(side_effect=MusicBrainzError("status 503"))
    monkeypatch.setattr(pipeline.musicbrainz, "filed_name", down)
    profiles = await pipeline.find_artist_profiles("Usher Raymond & Chris Brown", AsyncMock())
    assert [p.name for p in profiles] == ["Usher Raymond", "Chris Brown"]
