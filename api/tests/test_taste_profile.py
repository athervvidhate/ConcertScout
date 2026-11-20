"""Account-synced Taste Profile and the For You shelf: ownership, the Spotify boundary and a
shelf built from names and bills alone, with no model call.

The shelf contracts substitute the pool and the similarity sources at their typed boundaries.
The ownership contracts run against the real local Supabase stack (`make check-accounts`).
"""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr, ValidationError
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import cobilling, similarity, taste_profile
from concert_scout.app import create_app
from concert_scout.matching import CoBilledPeer, Neighbour, Taste
from concert_scout.models import Artist, Concert, SeedArtist
from concert_scout.sources import musicbrainz
from tests import supabase_stack as stack
from tests.contracts import (
    CONCERTS,
    PLACE,
    forbidden_http,
    install_sources,
    settings_with,
)

ORIGIN = "http://localhost:3000"
NEAR = {"lat": PLACE.lat, "lon": PLACE.lon}
DAY = CONCERTS[0].date or dt.date.today()


def concert(
    id: str, *names: str, day: int = 0, genre: str | None = None, festival: bool = False
) -> Concert:
    return Concert(
        id=id,
        name=f"Concert {id}",
        url=f"https://tickets.example/{id}",
        artists=[Artist(name=name, genre=genre, subgenre=genre) for name in names],
        date=DAY + dt.timedelta(days=day),
        festival=festival,
    )


def taste(
    *names: str, neighbours: list[Neighbour] | None = None, peers: dict[str, list[CoBilledPeer]]
) -> Taste:
    return Taste([SeedArtist(name=n) for n in names], neighbours or [], [], cobilling=peers)


def forbid_model(_: Any, __: AgentInfo) -> Any:
    raise AssertionError("For You must not call a model")


# --- What suits a Taste --------------------------------------------------------------------


def test_exact_names_come_first_then_the_closest_neighbours_then_bill_mates() -> None:
    pool = [
        concert("bill-mate", "Opener Friend"),
        concert("neighbour", "Near Neighbour"),
        concert("exact", "Favourite"),
        concert("stranger", "Nobody Asked"),
    ]
    liked = taste(
        "Favourite",
        neighbours=[
            Neighbour(name="Near Neighbour", mbid=None, hops=1, closeness=1.0, seed="Favourite")
        ],
        peers={"Favourite": [CoBilledPeer(artist_key="opener friend", weight=1.0)]},
    )

    found = taste_profile.shelf(pool, liked, ["Favourite"])

    assert [(f.concert.id, f.signal, f.via) for f in found] == [
        ("exact", "seed", "Favourite"),
        ("neighbour", "one_hop", "Favourite"),
        ("bill-mate", "co_billed", "Favourite"),
    ]
    assert found[1].artist == "Near Neighbour"


def test_a_shared_genre_alone_is_never_a_reason() -> None:
    pool = [
        concert("favourite", "Favourite", genre="Rock"),
        concert("same-genre", "Another Rock Band", genre="Rock"),
    ]

    found = taste_profile.shelf(pool, taste("Favourite", peers={}), ["Favourite"])

    assert [f.concert.id for f in found] == ["favourite"]
    # The Concert keeps every source fact, genres included.
    assert found[0].concert == pool[0]


def test_two_hop_neighbours_do_not_reach_the_shelf() -> None:
    far = Neighbour(name="Far Away", mbid=None, hops=2, closeness=1.0, seed="Favourite")
    found = taste_profile.shelf(
        [concert("far", "Far Away")], taste("Favourite", neighbours=[far], peers={}), ["Favourite"]
    )
    assert found == []


def test_favourites_lead_among_exact_matches_and_one_tour_cannot_fill_the_shelf() -> None:
    pool = [concert(f"tour-{n}", "Second", day=n) for n in range(5)]
    pool.append(concert("first", "First", day=30))
    names = ["First", "Second"]

    found = taste_profile.shelf(pool, taste(*names, peers={}), names)

    assert [f.concert.id for f in found] == ["first", "tour-0", "tour-1", "tour-2"]


def test_the_shelf_is_short() -> None:
    names = [f"Artist {n}" for n in range(40)]
    pool = [concert(f"c{n}", name, day=n) for n, name in enumerate(names)]
    assert len(taste_profile.shelf(pool, taste(*names, peers={}), names)) == taste_profile.MAX_SHELF


def test_distinct_keeps_the_first_spelling_and_the_order() -> None:
    assert taste_profile.distinct(["The Strokes", "  ", "Phoebe Bridgers", "strokes"]) == [
        "The Strokes",
        "Phoebe Bridgers",
    ]


# --- The Spotify boundary ------------------------------------------------------------------


@pytest.mark.parametrize("source", ["spotify", "spotify_oauth", ""])
def test_no_spotify_source_can_be_synced(source: str) -> None:
    with pytest.raises(ValidationError):
        taste_profile.TasteBody.model_validate({"source": source, "artists": ["Contract Artist"]})


# --- The guest shelf, with no model --------------------------------------------------------


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


@pytest.fixture
def unmatched_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """MusicBrainz knows no one by these names, so each stays as typed."""

    async def resolve(_: httpx.AsyncClient, __: object, name: str) -> SeedArtist:
        return SeedArtist(name=name)

    monkeypatch.setattr(musicbrainz, "resolve", resolve)


@pytest.fixture
async def guest(sources: None) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        FunctionModel(forbid_model),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000"
    ) as client:
        yield client


async def test_a_guest_with_local_taste_sees_exact_matches_and_calls_no_model(
    guest: httpx.AsyncClient,
) -> None:
    response = await guest.post(
        "/for-you", json={"artists": ["Contract Artist"], "near": NEAR, "time_zone": "UTC"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["place"] == "Near you"
    assert [row["concert"]["id"] for row in body["concerts"]] == ["contract-one", "contract-three"]
    assert {row["signal"] for row in body["concerts"]} == {"seed"}
    # The Concert is the source record, not something the shelf wrote.
    assert body["concerts"][0]["concert"] == CONCERTS[0].model_dump(mode="json", exclude_none=True)


async def test_similar_artists_and_bill_mates_reach_the_shelf_through_one_hop(
    guest: httpx.AsyncClient, unmatched_names: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    neighbours = AsyncMock(
        return_value=[
            Neighbour(
                name="Second Contract Artist", mbid=None, hops=1, closeness=1.0, seed="Seed Artist"
            )
        ]
    )
    monkeypatch.setattr(similarity, "find_neighbours", neighbours)

    response = await guest.post(
        "/for-you", json={"artists": ["Seed Artist"], "near": NEAR, "time_zone": "UTC"}
    )

    assert [(r["concert"]["id"], r["signal"]) for r in response.json()["concerts"]] == [
        ("contract-two", "one_hop")
    ]
    assert neighbours.await_args and neighbours.await_args.kwargs["hops"] == 1

    peers = AsyncMock(
        return_value={"Seed Artist": [CoBilledPeer(artist_key="contract artist", weight=1.0)]}
    )
    monkeypatch.setattr(similarity, "find_neighbours", AsyncMock(return_value=[]))
    monkeypatch.setattr(cobilling, "find_peers", peers)
    response = await guest.post(
        "/for-you", json={"artists": ["Seed Artist"], "near": NEAR, "time_zone": "UTC"}
    )
    rows = response.json()["concerts"]
    assert {(r["concert"]["id"], r["signal"], r["via"]) for r in rows} == {
        ("contract-one", "co_billed", "Seed Artist"),
        ("contract-three", "co_billed", "Seed Artist"),
    }


async def test_only_the_favourites_get_lookups(
    guest: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    neighbours = AsyncMock(return_value=[])
    monkeypatch.setattr(similarity, "find_neighbours", neighbours)
    names = [f"Artist {n}" for n in range(30)] + ["Contract Artist"]

    response = await guest.post(
        "/for-you", json={"artists": names, "near": NEAR, "time_zone": "UTC"}
    )

    assert neighbours.await_args
    assert len(neighbours.await_args.args[3]) == taste_profile.IMPORTED_SEEDS
    # A name past the favourites still matches the pool by name.
    assert [r["concert"]["id"] for r in response.json()["concerts"]] == [
        "contract-one",
        "contract-three",
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"artists": [], "near": NEAR, "time_zone": "UTC"},
        {"artists": ["Contract Artist"], "time_zone": "UTC"},
        {"artists": ["Contract Artist"], "near": {"lat": 400, "lon": 0}, "time_zone": "UTC"},
        {"artists": ["x"] * 101, "near": NEAR, "time_zone": "UTC"},
    ],
)
async def test_a_shelf_needs_a_taste_and_a_place(
    guest: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    response = await guest.post("/for-you", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_taste"


async def test_a_visitor_is_limited_on_lookups(
    sources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(taste_profile, "FOR_YOU_PER_HOUR", 2)
    app = create_app(
        settings_with(),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        FunctionModel(forbid_model),
    )
    body = {"artists": ["Contract Artist"], "near": NEAR, "time_zone": "UTC"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000"
    ) as client:
        codes = [(await client.post("/for-you", json=body)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- Ownership, against the real Supabase stack --------------------------------------------

supabase = pytest.mark.supabase


@pytest.fixture
async def api(sources: None) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        settings_with(
            supabase_url=stack.URL,
            supabase_publishable_key=stack.PUBLISHABLE_KEY,
            supabase_secret_key=SecretStr(stack.secret_key()),
        ),
        stack.stack_transport(httpx.MockTransport(forbidden_http)),
        FakeAsyncRedis(),
        FunctionModel(forbid_model),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000"
    ) as client:
        yield client


def server() -> httpx.Client:
    """The Data API with the server's own key, past every row policy."""
    return httpx.Client(base_url=f"{stack.URL}/rest/v1", headers={"apikey": stack.secret_key()})


def bearer(person: stack.Person) -> dict[str, str]:
    return {"Authorization": f"Bearer {person.token}", "Origin": ORIGIN}


async def put_taste(
    api: httpx.AsyncClient, person: stack.Person, *artists: str, source: str = "seed"
) -> httpx.Response:
    return await api.put(
        "/account/taste", json={"source": source, "artists": list(artists)}, headers=bearer(person)
    )


@supabase
async def test_a_taste_profile_follows_the_account_to_another_device(
    api: httpx.AsyncClient,
) -> None:
    person = stack.new_person()
    empty = await api.get("/account/taste", headers=bearer(person))
    assert empty.status_code == 200
    assert empty.json() is None

    saved = await put_taste(api, person, "Contract Artist", " contract  artist ", "Other Artist")
    assert saved.status_code == 200

    elsewhere = stack.Person(person.id, person.email, stack.sign_in(person.email))
    read = await api.get("/account/taste", headers=bearer(elsewhere))
    profile = read.json()
    assert profile["source"] == "seed"
    # Two spellings of one Artist are one, favourites still first.
    assert profile["artists"] == ["Contract Artist", "Other Artist"]
    assert profile["updated_at"] == saved.json()["updated_at"]

    replaced = await put_taste(api, person, "Only One", source="youtube")
    assert replaced.json()["artists"] == ["Only One"]
    assert (await api.get("/account/taste", headers=bearer(person))).json()["source"] == "youtube"


@supabase
async def test_spotify_data_cannot_be_synced_by_the_api_or_the_database(
    api: httpx.AsyncClient,
) -> None:
    person = stack.new_person()
    refused = await put_taste(api, person, "Contract Artist", source="spotify")
    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_taste"

    # Even the server's own key cannot write one past the table's check.
    row = {"user_id": person.id, "source": "spotify", "artists": ["Contract Artist"]}
    with server() as rest:
        assert rest.post("/taste_profiles", json=row).status_code == 400
    assert (await api.get("/account/taste", headers=bearer(person))).json() is None


@supabase
async def test_one_account_cannot_read_write_or_clear_another_accounts_taste(
    api: httpx.AsyncClient,
) -> None:
    owner, other = stack.new_person(), stack.new_person()
    await put_taste(api, owner, "Contract Artist")

    assert (await api.get("/account/taste", headers=bearer(other))).json() is None
    assert (await api.delete("/account/taste", headers=bearer(other))).status_code == 204
    assert (await api.get("/account/taste", headers=bearer(owner))).json()["artists"] == [
        "Contract Artist"
    ]

    # Straight to the Data API with the public key, the policies still hold.
    with stack.rest(other.token) as rest:
        assert rest.get("/taste_profiles", params={"select": "user_id"}).json() == []
    with stack.rest(owner.token) as rest:
        forged = {"user_id": owner.id, "source": "seed", "artists": ["Forged"]}
        assert rest.post("/taste_profiles", json=forged).status_code in (401, 403)
        edit = {"user_id": f"eq.{owner.id}"}
        patched = rest.patch("/taste_profiles", params=edit, json={"artists": ["Forged"]})
        assert patched.status_code in (401, 403)
    assert (await api.get("/account/taste", headers=bearer(owner))).json()["artists"] == [
        "Contract Artist"
    ]


@supabase
async def test_clearing_and_deleting_the_account_remove_the_taste(api: httpx.AsyncClient) -> None:
    person = stack.new_person()
    await put_taste(api, person, "Contract Artist")
    cleared = await api.delete("/account/taste", headers=bearer(person))
    assert cleared.status_code == 204
    assert (await api.get("/account/taste", headers=bearer(person))).json() is None

    await put_taste(api, person, "Contract Artist")
    fresh = stack.Person(person.id, person.email, stack.sign_in(person.email))
    deleted = await api.delete("/account", headers=bearer(fresh))
    assert deleted.status_code == 204
    with server() as rest:
        rows = rest.get("/taste_profiles", params={"user_id": f"eq.{person.id}"})
    assert rows.json() == []


@supabase
async def test_for_you_uses_the_synced_taste_and_the_shared_place_or_the_alert_place(
    api: httpx.AsyncClient,
) -> None:
    person = stack.new_person()
    shelf = {"near": NEAR, "time_zone": "UTC"}

    none_yet = await api.post("/account/for-you", json=shelf, headers=bearer(person))
    assert (none_yet.status_code, none_yet.json()["code"]) == (404, "taste_not_found")

    await put_taste(api, person, "Contract Artist")
    here = await api.post("/account/for-you", json=shelf, headers=bearer(person))
    assert here.status_code == 200
    assert [r["concert"]["id"] for r in here.json()["concerts"]] == [
        "contract-one",
        "contract-three",
    ]

    no_place = await api.post("/account/for-you", json={"time_zone": "UTC"}, headers=bearer(person))
    assert (no_place.status_code, no_place.json()["code"]) == (422, "for_you_needs_place")

    await api.put("/account/alerts/place", json={"place": "San Francisco"}, headers=bearer(person))
    from_alerts = await api.post(
        "/account/for-you", json={"time_zone": "UTC"}, headers=bearer(person)
    )
    assert from_alerts.status_code == 200
    assert from_alerts.json()["place"] == PLACE.name
    assert len(from_alerts.json()["concerts"]) == 2


async def test_the_account_routes_need_a_sign_in(sources: None) -> None:
    app = create_app(
        settings_with(
            supabase_url="https://supabase.test",
            supabase_publishable_key="sb_publishable_test",
            supabase_secret_key=SecretStr("sb_secret_test"),
        ),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
        FunctionModel(forbid_model),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000"
    ) as client:
        body = {"near": NEAR, "time_zone": "UTC"}
        assert (await client.post("/account/for-you", json=body)).status_code == 401
        assert (await client.get("/account/taste")).status_code == 401
        assert (await client.delete("/account/taste")).status_code == 401
