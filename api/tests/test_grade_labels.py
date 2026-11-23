"""Contracts for Recommendation.grade across assembly, Shared Posters and Saved Concerts."""

import datetime as dt
import json

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import assemble, share
from concert_scout.app import create_app
from concert_scout.matching import Candidate, Match, Signal
from concert_scout.models import Artist, Concert, Recommendation
from concert_scout.sources import supabase
from concert_scout.sources.supabase import Account, SavedConcert
from tests.contracts import (
    CONCERTS,
    DAY,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)
from tests.test_app import TOKEN, api_for, parse_sse


def _candidate(
    id_: str,
    score: float,
    signal: Signal,
    artist: str | None = None,
    *,
    festival: bool = False,
    lineup_match: list[str] | None = None,
) -> Candidate:
    name = artist or f"Artist {id_}"
    return Candidate(
        concert=Concert(
            id=id_,
            name=name,
            url=f"https://tickets.example/{id_}",
            artists=[Artist(name=name)],
            festival=festival,
        ),
        match=Match(artist=name, signal=signal, score=score, via="Khruangbin"),
        lineup_match=lineup_match or [],
    )


def test_seed_strong_and_fair_grades_match_effective_levels() -> None:
    seed = _candidate("seed", 1.0, "seed", "Khruangbin")
    strong = _candidate("strong", 0.8, "one_hop", "Hermanos Gutiérrez")
    fair = _candidate("fair", 0.5, "tags", "Parcels")

    poster = assemble.from_levels({"seed": 3, "strong": 3, "fair": 2}, [seed, strong, fair])

    assert [(r.concert.id, r.grade, r.score) for r in poster] == [
        ("seed", "seed", 3),
        ("strong", "strong", 3),
        ("fair", "fair", 2),
    ]


def test_a_seed_graded_fair_or_low_still_reads_as_seed() -> None:
    seed_fair = _candidate("seed-fair", 1.0, "seed", "Niall Horan")
    seed_low = _candidate("seed-low", 1.0, "seed", "Harry Styles")

    poster = assemble.from_levels({"seed-fair": 2, "seed-low": 0}, [seed_fair, seed_low])

    assert [(r.concert.id, r.grade, r.score) for r in poster] == [
        ("seed-fair", "seed", 2),
        ("seed-low", "seed", None),
    ]


def test_a_lifted_festival_exposes_its_lifted_grade() -> None:
    lifted = _candidate(
        "lifted-fest",
        0.5,
        "one_hop",
        "Insomniac Countdown",
        festival=True,
        lineup_match=["Alesso", "DJ Snake", "Tchami"],
    )
    unlifted = _candidate(
        "unlifted-fest",
        0.5,
        "one_hop",
        "Small Fest",
        festival=True,
        lineup_match=["Alesso", "DJ Snake"],
    )

    poster = assemble.from_levels({"lifted-fest": 2, "unlifted-fest": 2}, [unlifted, lifted])

    assert [(r.concert.id, r.grade, r.score) for r in poster] == [
        ("lifted-fest", "strong", 2),
        ("unlifted-fest", "fair", 2),
    ]


def test_fallback_and_place_only_recommendations_have_no_grade() -> None:
    rows = [
        _candidate("seed", 1.0, "seed", "Khruangbin"),
        _candidate("near", 0.8, "one_hop", "Parcels"),
    ]
    fallback = assemble.from_matches(rows)
    notable = assemble.from_notable([Candidate(concert=c) for c in CONCERTS[:2]])

    assert [r.grade for r in fallback] == [None, None]
    assert [r.grade for r in notable] == [None, None]


async def test_shared_poster_preserves_grade_and_reads_legacy_ungraded_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch)
    redis = FakeAsyncRedis()
    async with api_for(redis) as api:
        response = await api.post(
            "/search", json={"text": "UKG in SF", "token": TOKEN, "time_zone": "UTC"}
        )
        events = dict(parse_sse(response.text))
        assert [r["grade"] for r in events["poster"]["recommendations"]] == ["strong", "strong"]

        link = (
            await api.post("/share", json={"search_id": events["shareable"]["search_id"]})
        ).json()["id"]
        opened = (await api.get(f"/share/{link}")).json()
        assert [r["grade"] for r in opened["recommendations"]] == ["strong", "strong"]

        # Legacy stored Shared Posters without `grade` still deserialize cleanly with no grade.
        legacy = {
            "made": DAY.isoformat(),
            "reading": None,
            "recommendations": [
                {
                    "concert": CONCERTS[0].model_dump(mode="json", exclude_none=True),
                    "reason": "Legacy reason",
                    "score": 3,
                }
            ],
        }
        await redis.set("share:poster:LEGACY123456", json.dumps(legacy))
        legacy_opened = (await api.get("/share/LEGACY123456")).json()
        assert "grade" not in legacy_opened["recommendations"][0]


async def test_saved_concert_routes_preserve_grade_and_omit_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch)
    stored: dict[str, dict[str, object]] = {}

    async def fake_verify(self: supabase.Verifier, token: str) -> Account:
        return Account(id="acct-1", token=token, authenticated_at=1_700_000_000)

    async def fake_save(
        _client: httpx.AsyncClient,
        _secret: SecretStr,
        _account: Account,
        saves: list[SavedConcert],
    ) -> None:
        for item in saves:
            stored[item.concert.id] = {
                "concert": item.concert.model_dump(mode="json", exclude_none=True),
                "reason": item.reason,
                "grade": item.grade,
            }

    async def fake_list(
        _client: httpx.AsyncClient, _publishable: str, _account: Account
    ) -> list[SavedConcert]:
        return [SavedConcert.model_validate(row) for row in stored.values()]

    monkeypatch.setattr(supabase.Verifier, "verify", fake_verify)
    monkeypatch.setattr(supabase, "save", fake_save)
    monkeypatch.setattr(supabase, "list_saved", fake_list)

    app = create_app(
        settings_with(
            supabase_url="https://supabase.example",
            supabase_publishable_key="pub",
            supabase_secret_key=SecretStr("sec"),
        ),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    headers = {"Authorization": "Bearer valid-token", "Origin": "http://localhost:3000"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000"
    ) as api:
        graded = await api.put(
            f"/account/saved/{CONCERTS[0].id}",
            json={"reason": "Close in style", "grade": "strong"},
            headers=headers,
        )
        assert graded.status_code == 200
        assert graded.json()["grade"] == "strong"

        ungraded = await api.put(
            f"/account/saved/{CONCERTS[1].id}",
            json={"reason": "Coming up nearby"},
            headers=headers,
        )
        assert ungraded.status_code == 200
        assert "grade" not in ungraded.json()

        invalid = await api.put(
            f"/account/saved/{CONCERTS[0].id}",
            json={"reason": "Bad grade", "grade": "99%"},
            headers=headers,
        )
        assert invalid.status_code == 422

        listed = (await api.get("/account/saved", headers=headers)).json()
        by_id = {row["concert"]["id"]: row for row in listed}
        assert by_id[CONCERTS[0].id]["grade"] == "strong"
        assert "grade" not in by_id[CONCERTS[1].id]

        # Guest save import also preserves grade when present and omits it when absent.
        imported = await api.post(
            "/account/saved/import",
            json={
                "saves": [
                    {"concert_id": CONCERTS[0].id, "reason": "Named", "grade": "seed"},
                    {"concert_id": CONCERTS[1].id, "reason": "Fallback"},
                ]
            },
            headers=headers,
        )
        assert imported.status_code == 200
        imported_by_id = {row["concert"]["id"]: row for row in imported.json()["saved"]}
        assert imported_by_id[CONCERTS[0].id]["grade"] == "seed"
        assert "grade" not in imported_by_id[CONCERTS[1].id]


def test_share_upcoming_preserves_grade() -> None:
    today = dt.date(2027, 5, 1)
    future = CONCERTS[0].model_copy(update={"date": dt.date(2027, 5, 10)})
    rec = Recommendation(concert=future, reason="Fits", score=2, grade="strong")
    kept = share.assemble.upcoming([rec], today)
    assert kept[0].grade == "strong"
