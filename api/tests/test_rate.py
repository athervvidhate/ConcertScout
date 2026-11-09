"""The rating page saves labels exactly as the command-line judge does."""

from typing import Any

import httpx
import pytest

from concert_scout.models import Artist, Concert, Recommendation
from evals import cases, harness, rate, snapshots
from evals.cases import Search
from evals.harness import SearchRun


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> list[list[Search]]:
    saved: list[list[Search]] = [
        [Search(id="case", text="Like Four Tet in London", must=["Bicep"])]
    ]

    def save(searches: list[Search]) -> None:
        saved.append(searches)

    def batch(_: list[str]) -> dict[str, str]:
        return {"case": "case-snapshot"}

    def load(_: str) -> object:
        return object()

    monkeypatch.setattr(cases, "load", lambda: saved[-1])
    monkeypatch.setattr(cases, "save", save)
    monkeypatch.setattr(rate, "batch_cases", batch)
    monkeypatch.setattr(snapshots, "load", load)

    async def replay(_: Any, __: Any) -> tuple[SearchRun, list[str]]:
        concert = Concert(
            id="c", name="Show", url="https://t.example", artists=[Artist(name="Bonobo")]
        )
        run = SearchRun(
            recommendations=[Recommendation(concert=concert, reason="Warm downtempo.", score=3)],
            names=["Bonobo", "Katseye"],
        )
        return run, []

    monkeypatch.setattr(harness, "replay", replay)
    return saved


def client() -> httpx.AsyncClient:
    app = rate.make_app("batch")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


async def test_a_search_shows_the_poster_first_with_existing_labels(
    stored: list[list[Search]],
) -> None:
    async with client() as api:
        detail = (await api.get("/api/searches/case")).json()
    assert [(a["name"], a["on_poster"], a["label"]) for a in detail["artists"]] == [
        ("Bonobo", True, "neutral"),
        ("Katseye", False, "neutral"),
    ]
    assert detail["artists"][0]["reason"] == "Warm downtempo."
    assert detail["others"] == ["Bicep"]


async def test_saving_writes_the_judge_labels(stored: list[list[Search]]) -> None:
    rating = {
        "labels": {"Bonobo": "good", "Katseye": "bad"},
        "others": [" Bicep "],
        "notes": " ok ",
    }
    async with client() as api:
        response = await api.post("/api/searches/case", json=rating)
    assert response.status_code == 200
    [saved] = stored[-1]
    assert (saved.judged, saved.snapshot) == (True, "case-snapshot")
    assert (saved.must, saved.good, saved.bad, saved.notes) == (
        ["Bicep"],
        ["Bonobo"],
        ["Katseye"],
        "ok",
    )


async def test_an_unknown_search_is_not_found(stored: list[list[Search]]) -> None:
    async with client() as api:
        assert (await api.get("/api/searches/missing")).status_code == 404


async def test_listen_plays_the_exact_artist_page_in_spotifys_player(
    stored: list[list[Search]],
) -> None:
    pages = {"Bonobo": "https://open.spotify.com/artist/0cmWgDlu9CwTgxPhf403hb?si=x"}

    async def find_page(name: str) -> str | None:
        return pages.get(name)

    app = rate.make_app("batch", find_page)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as api:
        found = (await api.get("/api/listen", params={"name": "Bonobo"})).json()
        missing = (await api.get("/api/listen", params={"name": "Katseye"})).json()
    assert found == {"player": "https://open.spotify.com/embed/artist/0cmWgDlu9CwTgxPhf403hb"}
    assert missing == {"player": None}


async def test_listen_is_off_without_spotify_credentials(stored: list[list[Search]]) -> None:
    async with client() as api:
        assert (await api.get("/api/listen", params={"name": "Bonobo"})).json() == {"player": None}


@pytest.mark.parametrize(
    "page",
    [
        None,
        "https://open.spotify.com/album/0cmWgDlu9CwTgxPhf403hb",
        "https://evil.example/artist/abc",
        "https://open.spotify.com/artist/abc/../../x",
    ],
)
def test_only_a_plain_artist_page_becomes_a_player(page: str | None) -> None:
    assert rate.player(page) is None
