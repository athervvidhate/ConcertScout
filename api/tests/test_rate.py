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
