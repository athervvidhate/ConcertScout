"""Unit, FastAPI route contract, and Supabase RLS tests for Group Scout (/g/[id])."""

import datetime as dt
import math
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import group_scout, matching, pool
from concert_scout.app import create_app
from concert_scout.models import Artist, Concert, Price, SeedArtist
from concert_scout.sources import geocoder
from tests import supabase_stack as stack
from tests.contracts import (
    CONCERTS,
    DAY,
    contract_model,
    forbidden_http,
    install_sources,
    settings_with,
)


def _concert(
    concert_id: str,
    artist_name: str,
    *,
    mbid: str | None = None,
    day: dt.date = DAY,
    price_min: float | None = None,
    genre: str | None = None,
) -> Concert:
    return Concert(
        id=concert_id,
        name=f"{artist_name} Live",
        url=f"https://tickets.example/{concert_id}",
        artists=[Artist(name=artist_name, mbid=mbid, genre=genre)],
        date=day,
        venue="Moss Hall",
        city="Brooklyn",
        region="NY",
        price=Price(min=price_min, max=price_min, currency="USD")
        if price_min is not None
        else None,
    )


def _member(
    member_id: str,
    name: str,
    artists: list[str],
    *,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    max_price: float | None = None,
) -> group_scout.GroupMember:
    return group_scout.GroupMember(
        id=member_id,
        name=name,
        artists=artists,
        start_date=start_date,
        end_date=end_date,
        max_price=max_price,
        joined_at=dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC),
    )


# ---------------------------------------------------------------------------
# Pure Nash social welfare & constraint intersection tests
# ---------------------------------------------------------------------------


def test_nash_welfare_favors_balanced_group_fit_over_one_sided_match() -> None:
    balanced = group_scout.nash_welfare([0.7, 0.7])
    one_sided = group_scout.nash_welfare([1.0, 0.0])

    assert balanced == pytest.approx(0.75)
    assert one_sided == pytest.approx(math.sqrt(1.05 * 0.05))
    assert balanced > one_sided * 3


def test_score_group_concerts_ranks_shared_fit_above_solo_favorite() -> None:
    # Concert A matches both Maya and Sam as a strong 1-hop neighbour (~0.72 each).
    # Concert B is an exact seed (1.0) for Maya, 0.0 for Sam.
    shared = _concert("shared", "Parcels")
    solo_maya = _concert("solo-maya", "Khruangbin")

    maya = _member("m1", "Maya", ["Khruangbin"])
    sam = _member("m2", "Sam", ["Bonobo"])

    tastes = {
        "m1": matching.Taste(
            seeds=[SeedArtist(name="Khruangbin")],
            neighbours=[
                matching.Neighbour(
                    name="Parcels", mbid=None, hops=1, closeness=0.81, seed="Khruangbin"
                )
            ],
            tags=[],
        ),
        "m2": matching.Taste(
            seeds=[SeedArtist(name="Bonobo")],
            neighbours=[
                matching.Neighbour(name="Parcels", mbid=None, hops=1, closeness=0.81, seed="Bonobo")
            ],
            tags=[],
        ),
    }

    _, picks = group_scout.score_group_concerts([solo_maya, shared], [maya, sam], tastes)
    assert [p.concert.id for p in picks] == ["shared", "solo-maya"]
    assert picks[0].everyone_fits is True
    assert picks[1].everyone_fits is False
    assert [(m.name, m.badge, m.via) for m in picks[0].member_matches] == [
        ("Maya", "Similar", "Khruangbin"),
        ("Sam", "Similar", "Bonobo"),
    ]
    assert [(m.name, m.badge, m.matched_artist) for m in picks[1].member_matches] == [
        ("Maya", "Named", "Khruangbin"),
    ]


def test_per_member_badges_reflect_honest_source_signals() -> None:
    c_seed = _concert("c-seed", "Khruangbin")
    c_sim = _concert("c-sim", "Glass Beams")
    c_cobill = _concert("c-cobill", "Hermanos Gutierrez")
    c_sem = _concert("c-sem", "Bicep")
    c_tag = _concert("c-tag", "Local Act", mbid="mbid-local")

    member = _member("m1", "Maya", ["Khruangbin"])
    taste = matching.Taste(
        seeds=[SeedArtist(name="Khruangbin", tags=["psychedelic funk"])],
        neighbours=[
            matching.Neighbour(
                name="Glass Beams", mbid=None, hops=1, closeness=0.9, seed="Khruangbin"
            )
        ],
        tags=[],
        cobilling={
            "Khruangbin": [matching.CoBilledPeer(artist_key="hermanos gutierrez", weight=2)]
        },
        semantic={"bicep": 0.85},
    )

    _, picks = group_scout.score_group_concerts(
        [c_seed, c_sim, c_cobill, c_sem, c_tag],
        [member],
        {"m1": taste},
        artist_tags={"mbid-local": ["psychedelic funk"]},
    )
    badges = {p.concert.id: p.member_matches[0].badge for p in picks}
    assert badges == {
        "c-seed": "Named",
        "c-sim": "Similar",
        "c-cobill": "Co-billed",
        "c-sem": "Sounds close",
        "c-tag": "Style match",
    }


def test_constraints_intersect_dates_and_enforce_adr_0002_strict_price_cap() -> None:
    early = _concert("early", "Act A", day=DAY, price_min=30)
    middle_ok = _concert("mid-ok", "Act B", day=DAY + dt.timedelta(days=3), price_min=45)
    middle_expensive = _concert("mid-high", "Act C", day=DAY + dt.timedelta(days=3), price_min=80)
    middle_unpriced = _concert("mid-none", "Act D", day=DAY + dt.timedelta(days=3), price_min=None)
    late = _concert("late", "Act E", day=DAY + dt.timedelta(days=10), price_min=25)

    maya = _member(
        "m1",
        "Maya",
        ["Act B"],
        start_date=DAY + dt.timedelta(days=1),
        end_date=DAY + dt.timedelta(days=6),
        max_price=60,
    )
    sam = _member(
        "m2",
        "Sam",
        ["Act B"],
        start_date=DAY + dt.timedelta(days=2),
        end_date=DAY + dt.timedelta(days=5),
        max_price=50,
    )

    effective, picks = group_scout.score_group_concerts(
        [early, middle_ok, middle_expensive, middle_unpriced, late],
        [maya, sam],
        {"m1": matching.Taste([], [], []), "m2": matching.Taste([], [], [])},
    )
    assert effective.dates_conflict is False
    assert effective.start_date == DAY + dt.timedelta(days=2)
    assert effective.end_date == DAY + dt.timedelta(days=5)
    assert effective.max_price == 50
    # Missing price (mid-none) must NEVER pass a strict max_price cap (ADR 0002).
    assert [p.concert.id for p in picks] == ["mid-ok"]


def test_disjoint_member_dates_flag_conflict_and_fall_back_to_union_window() -> None:
    d1 = DAY + dt.timedelta(days=2)
    d2 = DAY + dt.timedelta(days=10)
    c1 = _concert("c1", "Act A", day=d1)
    c2 = _concert("c2", "Act B", day=d2)

    maya = _member("m1", "Maya", ["Act A"], start_date=DAY, end_date=DAY + dt.timedelta(days=3))
    sam = _member(
        "m2",
        "Sam",
        ["Act B"],
        start_date=DAY + dt.timedelta(days=8),
        end_date=DAY + dt.timedelta(days=12),
    )

    effective, picks = group_scout.score_group_concerts(
        [c1, c2],
        [maya, sam],
        {"m1": matching.Taste([], [], []), "m2": matching.Taste([], [], [])},
    )
    assert effective.dates_conflict is True
    assert effective.start_date == DAY
    assert effective.end_date == DAY + dt.timedelta(days=12)
    assert {p.concert.id for p in picks} == {"c1", "c2"}


def test_consensus_in_requires_at_least_two_members_all_voting_in() -> None:
    c1 = _concert("c1", "Act A")
    now = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC)
    maya = _member("m1", "Maya", ["Act A"])
    sam = _member("m2", "Sam", ["Act A"])
    tastes = {
        "m1": matching.Taste([SeedArtist(name="Act A")], [], []),
        "m2": matching.Taste([SeedArtist(name="Act A")], [], []),
    }

    _, solo_picks = group_scout.score_group_concerts(
        [c1],
        [maya],
        tastes,
        votes=[
            group_scout.GroupVote(
                room_id="r", member_id="m1", concert_id="c1", vote="in", updated_at=now
            )
        ],
    )
    assert solo_picks[0].consensus_in is False

    _, pair_picks = group_scout.score_group_concerts(
        [c1],
        [maya, sam],
        tastes,
        votes=[
            group_scout.GroupVote(
                room_id="r", member_id="m1", concert_id="c1", vote="in", updated_at=now
            ),
            group_scout.GroupVote(
                room_id="r", member_id="m2", concert_id="c1", vote="in", updated_at=now
            ),
        ],
    )
    assert pair_picks[0].consensus_in is True
    assert pair_picks[0].vote_counts == {"in": 2, "maybe": 0, "pass": 0}


# ---------------------------------------------------------------------------
# FastAPI route contract tests (Redis fallback store, offline)
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    install_sources(monkeypatch)
    app = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        contract_model(),
    )
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as http:
        yield http


async def test_group_lifecycle_create_join_vote_leave_and_cap(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/groups",
        json={
            "place": "San Francisco, CA",
            "title": "SF Weekend Crew",
            "member_name": "Maya",
            "artists": ["Contract Artist"],
            "time_zone": "America/Los_Angeles",
        },
    )
    assert created.status_code == 200
    body = created.json()
    room_id = body["room"]["id"]
    maya_id = body["member_id"]
    assert group_scout.ROOM_ID_RE.fullmatch(room_id)
    assert body["room"]["title"] == "SF Weekend Crew"
    assert len(body["room"]["members"]) == 1
    assert body["room"]["picks"][0]["concert"]["id"] == "contract-one"
    assert body["room"]["picks"][0]["member_matches"][0]["badge"] == "Named"

    # GET returns the room state.
    fetched = await client.get(f"/groups/{room_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == room_id

    # Second friend joins with Second Contract Artist.
    joined = await client.post(
        f"/groups/{room_id}/members",
        json={"name": "Sam", "artists": ["Second Contract Artist"]},
    )
    assert joined.status_code == 200
    sam_id = joined.json()["member_id"]
    assert len(joined.json()["room"]["members"]) == 2

    # Both cast votes and reach consensus on contract-one.
    vote1 = await client.put(
        f"/groups/{room_id}/votes",
        json={"member_id": maya_id, "concert_id": "contract-one", "vote": "in"},
    )
    assert vote1.status_code == 200
    vote2 = await client.put(
        f"/groups/{room_id}/votes",
        json={"member_id": sam_id, "concert_id": "contract-one", "vote": "in"},
    )
    assert vote2.status_code == 200
    pick_one = next(p for p in vote2.json()["picks"] if p["concert"]["id"] == "contract-one")
    assert pick_one["consensus_in"] is True
    assert pick_one["vote_counts"] == {"in": 2, "maybe": 0, "pass": 0}

    # Changing a vote updates the tally cleanly.
    changed = await client.put(
        f"/groups/{room_id}/votes",
        json={"member_id": sam_id, "concert_id": "contract-one", "vote": "maybe"},
    )
    assert changed.status_code == 200
    pick_one = next(p for p in changed.json()["picks"] if p["concert"]["id"] == "contract-one")
    assert pick_one["consensus_in"] is False
    assert pick_one["vote_counts"] == {"in": 1, "maybe": 1, "pass": 0}

    # Fill room up to 6 members; the 7th is refused with 409 group_full.
    for idx in range(3, 7):
        res = await client.post(
            f"/groups/{room_id}/members",
            json={"name": f"Friend {idx}", "artists": ["Contract Artist"]},
        )
        assert res.status_code == 200
    seventh = await client.post(
        f"/groups/{room_id}/members",
        json={"name": "Friend 7", "artists": ["Contract Artist"]},
    )
    assert seventh.status_code == 409
    assert seventh.json()["code"] == "group_full"

    # Leaving removes Sam and cascades Sam's votes.
    left = await client.delete(f"/groups/{room_id}/members/{sam_id}")
    assert left.status_code == 200
    assert len(left.json()["members"]) == 5
    pick_one = next(p for p in left.json()["picks"] if p["concert"]["id"] == "contract-one")
    assert sam_id not in pick_one["member_votes"]
    assert pick_one["vote_counts"] == {"in": 1, "maybe": 0, "pass": 0}


async def test_group_routes_refuse_unknown_room_member_and_concert(
    client: httpx.AsyncClient,
) -> None:
    missing = await client.get("/groups/AAAAAAAAAAAAAAAAAAAAAA")
    assert missing.status_code == 404
    assert missing.json()["code"] == "group_not_found"

    malformed = await client.get("/groups/not-a-valid-id")
    assert malformed.status_code == 404

    created = await client.post(
        "/groups",
        json={
            "place": "San Francisco, CA",
            "member_name": "Maya",
            "artists": ["Contract Artist"],
        },
    )
    room_id = created.json()["room"]["id"]
    member_id = created.json()["member_id"]

    # Unknown concert_id is refused so forged IDs never enter votes (ADR 0002).
    bad_concert = await client.put(
        f"/groups/{room_id}/votes",
        json={"member_id": member_id, "concert_id": "forged-concert-id", "vote": "in"},
    )
    assert bad_concert.status_code == 404
    assert bad_concert.json()["code"] == "concert_not_found"

    # Unknown member_id is refused.
    bad_member = await client.put(
        f"/groups/{room_id}/votes",
        json={
            "member_id": "00000000-0000-0000-0000-000000000000",
            "concert_id": "contract-one",
            "vote": "in",
        },
    )
    assert bad_member.status_code == 403
    assert bad_member.json()["code"] == "member_not_found"

    # Empty artists or invalid dates return 422.
    bad_dates = await client.post(
        "/groups",
        json={
            "place": "San Francisco, CA",
            "member_name": "Maya",
            "artists": ["Contract Artist"],
            "start_date": (DAY + dt.timedelta(days=5)).isoformat(),
            "end_date": DAY.isoformat(),
        },
    )
    assert bad_dates.status_code == 422
    assert bad_dates.json()["code"] == "invalid_group"


async def test_unknown_place_returns_404(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=None))
    res = await client.post(
        "/groups",
        json={"place": "Nowhereville", "member_name": "Maya", "artists": ["Contract Artist"]},
    )
    assert res.status_code == 404
    assert res.json()["code"] == "place_not_found"


async def test_group_create_uses_source_concerts_unchanged(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pool, "find_concerts", AsyncMock(return_value=CONCERTS))
    res = await client.post(
        "/groups",
        json={"place": "San Francisco, CA", "member_name": "Maya", "artists": ["Contract Artist"]},
    )
    assert res.status_code == 200
    returned_ids = {p["concert"]["id"] for p in res.json()["room"]["picks"]}
    assert returned_ids == {c.id for c in CONCERTS}


# ---------------------------------------------------------------------------
# Real Supabase Postgres + RLS integration tests
# ---------------------------------------------------------------------------


@pytest.mark.supabase
async def test_supabase_group_scout_rls_and_cascade(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)
    app = create_app(
        settings_with(
            supabase_url=stack.URL,
            supabase_publishable_key=stack.PUBLISHABLE_KEY,
            supabase_secret_key=SecretStr(stack.secret_key()),
        ),
        stack.stack_transport(httpx.MockTransport(forbidden_http)),
        FakeAsyncRedis(),
        contract_model(),
    )
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as api:
        created = await api.post(
            "/groups",
            json={
                "place": "San Francisco, CA",
                "title": "Supabase RLS Room",
                "member_name": "Maya",
                "artists": ["Contract Artist"],
            },
        )
        assert created.status_code == 200
        room_id = created.json()["room"]["id"]
        maya_id = created.json()["member_id"]

        joined = await api.post(
            f"/groups/{room_id}/members",
            json={"name": "Sam", "artists": ["Second Contract Artist"]},
        )
        assert joined.status_code == 200
        sam_id = joined.json()["member_id"]

        voted = await api.put(
            f"/groups/{room_id}/votes",
            json={"member_id": sam_id, "concert_id": "contract-one", "vote": "in"},
        )
        assert voted.status_code == 200

        # Direct browser/anon writes MUST be rejected by RLS; SELECT works for Realtime.
        anon_headers = {
            "apikey": stack.PUBLISHABLE_KEY,
            "Authorization": f"Bearer {stack.PUBLISHABLE_KEY}",
        }
        async with httpx.AsyncClient(base_url=f"{stack.URL}/rest/v1", headers=anon_headers) as anon:
            read_room = await anon.get(
                "/group_rooms", params={"id": f"eq.{room_id}", "select": "id"}
            )
            assert read_room.status_code == 200
            assert read_room.json() == [{"id": room_id}]

            forged_room = await anon.post(
                "/group_rooms",
                json={"id": "forged-room-id-1234567", "title": "Bad", "place": {}},
            )
            assert forged_room.status_code in (401, 403)

            forged_member = await anon.post(
                "/group_members",
                json={"room_id": room_id, "name": "Intruder", "artists": ["Fake"]},
            )
            assert forged_member.status_code in (401, 403)

            forged_vote = await anon.post(
                "/group_votes",
                json={
                    "room_id": room_id,
                    "member_id": maya_id,
                    "concert_id": "contract-one",
                    "vote": "pass",
                },
            )
            assert forged_vote.status_code in (401, 403)

        # Leaving removes Sam and cascades Sam's vote in Postgres.
        left = await api.delete(f"/groups/{room_id}/members/{sam_id}")
        assert left.status_code == 200
        assert [m["id"] for m in left.json()["members"]] == [maya_id]
        pick_one = next(p for p in left.json()["picks"] if p["concert"]["id"] == "contract-one")
        assert pick_one["vote_counts"] == {"in": 0, "maybe": 0, "pass": 0}
