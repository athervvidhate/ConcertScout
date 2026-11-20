"""Live Co-Billing Graph contracts: bill weighting, pure scoring, dedupe, and pipeline wiring."""

import asyncio
import datetime as dt
import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import (
    assemble,
    cobilling,
    matching,
    pipeline,
    pool,
    ranker,
    similarity,
    sync,
    warm,
)
from concert_scout.app import create_app, make_services
from concert_scout.matching import CoBilledPeer, Neighbour, Taste
from concert_scout.models import Artist, Concert, SeedArtist
from concert_scout.sources import geocoder, jev, listenbrainz, musicbrainz, supabase, ticketmaster
from tests import supabase_stack as stack
from tests.conftest import interpretation, model_returning
from tests.contracts import (
    DAY,
    NOW,
    PLACE,
    contract_grades,
    forbidden_http,
    idle_musicbrainz,
    settings_with,
)
from tests.test_jambase import MOMENT, TODAY, captured, page_of

SUPABASE_URL = "https://supabase.test"
SECRET = SecretStr("sb_secret_test_key")


def concert(id: str, *names: str, date: dt.date | None = DAY, festival: bool = False) -> Concert:
    return Concert(
        id=id,
        name=f"Concert {id}",
        url=f"https://tickets.example/{id}",
        artists=[Artist(name=name) for name in names],
        date=date,
        festival=festival,
    )


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, 0.0),
        (1, 0.0),
        (2, 1.0),
        (5, 1.0),
        (6, 0.45),
        (15, 0.45),
        (16, 0.15),
        (40, 0.15),
        (41, 0.0),
        (120, 0.0),
    ],
)
def test_bill_weight_brackets_match_spec(count: int, expected: float) -> None:
    assert cobilling.bill_weight(count) == expected


def test_extract_bills_deduplicates_concerts_normalizes_artists_and_skips_mega_festivals() -> None:
    club = concert("c-club", "The Smile", "Four Tet", "smile")  # 2 unique normalized artists
    duplicate_club = concert("c-club", "Four Tet", "Different Opener")
    solo_after_norm = concert("c-solo", "The Smile", "Smile")
    showcase = concert("c-show", *(f"Artist {i}" for i in range(8)), date=None)
    mega = concert("c-mega", *(f"Act {i}" for i in range(41)))

    bills = cobilling.extract_bills([club, duplicate_club, solo_after_norm, showcase, mega], TODAY)

    assert [b.concert_id for b in bills] == ["c-club", "c-show"]
    assert bills[0].artists == ["four tet", "smile"]
    assert bills[0].weight == 1.0
    assert bills[0].concert_date == DAY
    assert bills[1].weight == 0.45
    assert bills[1].concert_date == TODAY
    assert len(bills[1].artists) == 8


def test_cobilled_peer_scores_deterministically_between_one_hop_and_two_hops() -> None:
    seed = SeedArtist(name="Four Tet", mbid="four-tet")
    taste = Taste(
        [seed],
        [
            Neighbour(name="Caribou", mbid="caribou", hops=1, closeness=1.0, seed=seed.name),
            Neighbour(name="Burial", mbid="burial", hops=2, closeness=1.0, seed=seed.name),
        ],
        [],
        cobilling={
            "four tet": [
                CoBilledPeer(artist_key="floating points", weight=2.0, shared_shows=2),
                CoBilledPeer(artist_key="kieran opener", weight=0.5, shared_shows=1),
                CoBilledPeer(artist_key="four tet", weight=5.0, shared_shows=5),  # self ignored
                CoBilledPeer(artist_key="zero weight", weight=0.0, shared_shows=1),
            ]
        },
    )
    pool_concerts = [
        concert("1", "Caribou"),
        concert("2", "Floating Points"),
        concert("3", "Kieran Opener"),
        concert("4", "Burial"),
        concert("5", "Zero Weight"),
    ]
    matches = {c.concert.id: c.match for c in matching.score_concerts(pool_concerts, taste, {})}

    fp = matches["2"]
    opener = matches["3"]
    assert fp is not None and opener is not None
    assert fp.signal == "co_billed"
    assert fp.score == pytest.approx(matching.CO_BILLED_WEIGHT)
    assert fp.artist == "Floating Points"
    assert fp.via == "Four Tet"
    assert matches["1"] is not None and matches["4"] is not None
    assert matches["1"].score > fp.score > matches["4"].score
    assert fp.score > opener.score > 0
    assert matches["5"] is None


def test_single_mid_festival_cobill_does_not_inflate_to_full_weight() -> None:
    seed = SeedArtist(name="Four Tet")
    taste = Taste(
        [seed],
        [],
        [],
        cobilling={"Four Tet": [CoBilledPeer(artist_key="mid fest peer", weight=0.15)]},
    )
    [candidate] = matching.score_concerts([concert("f", "Mid Fest Peer")], taste, {})

    assert candidate.match is not None
    assert candidate.match.signal == "co_billed"
    assert candidate.match.score < assemble.QUALIFYING_SCORE


def test_cobilling_adds_support_to_break_ties_and_names_festival_lineup_matches() -> None:
    seed = SeedArtist(name="Khruangbin")
    taste = Taste(
        [seed],
        [
            Neighbour(name="Hermanos Gutierrez", mbid=None, hops=1, closeness=1.0, seed=seed.name),
            Neighbour(name="Other Peer", mbid=None, hops=1, closeness=1.0, seed=seed.name),
        ],
        [],
        cobilling={
            "Khruangbin": [
                CoBilledPeer(artist_key="hermanos gutierrez", weight=1.0, shared_shows=1),
                CoBilledPeer(artist_key="arc de soleil", weight=1.0, shared_shows=1),
            ]
        },
    )
    concerts = [
        concert("other", "Other Peer"),
        concert("both", "Hermanos Gutierrez"),
        concert("fest", "Nobody", "Arc De Soleil", festival=True),
    ]
    scored = matching.score_concerts(concerts, taste, {})
    ranked = matching.shortlist(scored)

    assert [c.concert.id for c in ranked] == ["both", "other", "fest"]
    assert ranked[0].match is not None and ranked[1].match is not None
    assert ranked[0].match.support > ranked[1].match.support
    assert ranked[2].lineup_match == ["Arc De Soleil"]


def test_cobilled_neutral_fallback_reason_names_the_seed() -> None:
    seed = SeedArtist(name="Khruangbin")
    taste = Taste(
        [seed],
        [],
        [],
        cobilling={"Khruangbin": [CoBilledPeer(artist_key="arc de soleil", weight=1.0)]},
    )
    candidates = matching.score_concerts([concert("1", "Arc De Soleil")], taste, {})

    from_matches = assemble.from_matches(candidates)
    from_levels = assemble.from_levels({"1": 3}, candidates)

    assert len(from_matches) == 1
    assert from_matches[0].reason == "Shares bills with Khruangbin"
    assert from_levels[0].reason == "Shares bills with Khruangbin"


class InMemoryCoBillingRPC:
    """Simulates the Supabase co-billing RPCs with Postgres deduplication and accumulation."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.edges: dict[tuple[str, str], tuple[float, int, dt.date]] = {}
        self.calls: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["apikey"] == SECRET.get_secret_value()
        body = json.loads(request.content)
        if request.url.path == supabase.COBILLING_RECORD:
            recorded = 0
            for bill in body["p_bills"]:
                cid = bill["concert_id"]
                if cid in self.seen:
                    continue
                self.seen.add(cid)
                recorded += 1
                artists = sorted(set(bill["artists"]))
                day = dt.date.fromisoformat(bill["concert_date"])
                weight = float(bill["weight"])
                for i, a in enumerate(artists):
                    for b in artists[i + 1 :]:
                        prev_w, prev_n, prev_d = self.edges.get((a, b), (0.0, 0, day))
                        self.edges[(a, b)] = (prev_w + weight, prev_n + 1, max(prev_d, day))
            return httpx.Response(200, json=recorded)
        if request.url.path == supabase.COBILLING_NEIGHBORS:
            wanted = set(body["p_artists"])
            limit = int(body["p_limit"])
            by_seed: dict[str, list[dict[str, Any]]] = {}
            for (a, b), (weight, shows, last_seen) in self.edges.items():
                if a in wanted:
                    by_seed.setdefault(a, []).append(
                        {
                            "seed": a,
                            "peer": b,
                            "weight": weight,
                            "shared_shows": shows,
                            "last_seen": last_seen.isoformat(),
                        }
                    )
                if b in wanted:
                    by_seed.setdefault(b, []).append(
                        {
                            "seed": b,
                            "peer": a,
                            "weight": weight,
                            "shared_shows": shows,
                            "last_seen": last_seen.isoformat(),
                        }
                    )
            rows: list[dict[str, Any]] = []
            for seed_key in sorted(by_seed):
                ranked = sorted(
                    by_seed[seed_key],
                    key=lambda r: (-r["weight"], -r["shared_shows"], r["peer"]),
                )
                rows.extend(ranked[:limit])
            return httpx.Response(200, json=rows)
        return httpx.Response(404)


async def test_ingest_and_find_peers_round_trip_without_double_counting() -> None:
    rpc = InMemoryCoBillingRPC()
    bills = [
        concert("show-1", "Four Tet", "Floating Points", "Caribou"),
        concert("show-2", "Four Tet", "Floating Points"),
        concert("mega-1", *(f"Band {i}" for i in range(45))),
    ]
    async with supabase.make_client(SUPABASE_URL, httpx.MockTransport(rpc.handle)) as client:
        first = await cobilling.ingest_concerts(client, SECRET, bills, TODAY)
        second = await cobilling.ingest_concerts(client, SECRET, bills, TODAY)
        peers = await cobilling.find_peers(client, SECRET, ["Four Tet", "FOUR TET"])

    assert (first, second) == (2, 0)
    assert rpc.edges[("floating points", "four tet")][:2] == (2.0, 2)
    assert rpc.edges[("caribou", "four tet")][:2] == (1.0, 1)
    assert list(peers) == ["Four Tet"]
    assert [(p.artist_key, p.weight, p.shared_shows) for p in peers["Four Tet"]] == [
        ("floating points", 2.0, 2),
        ("caribou", 1.0, 1),
    ]


async def test_cobilling_gracefully_no_ops_when_unconfigured_or_unavailable() -> None:
    bill = [concert("show-1", "Four Tet", "Floating Points")]

    # Unconfigured: no client or no secret key makes zero requests.
    assert await cobilling.ingest_concerts(None, None, bill, TODAY) == 0
    assert await cobilling.find_peers(None, None, ["Four Tet"]) == {}

    async with supabase.make_client(
        SUPABASE_URL, httpx.MockTransport(lambda _: httpx.Response(503))
    ) as down:
        assert await cobilling.ingest_concerts(down, SECRET, bill, TODAY) == 0
        assert await cobilling.find_peers(down, SECRET, ["Four Tet"]) == {}


async def test_sync_populates_cobilling_and_survives_supabase_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync, "REQUEST_GAP", 0)
    monkeypatch.setattr(warm, "PLACES", ())
    records = captured("jambase-lodge.json")["events"]
    rpc = InMemoryCoBillingRPC()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "supabase.test":
            return rpc.handle(request)
        if request.url.host == "musicbrainz.org":
            body = captured("musicbrainz-batch.json")
            return httpx.Response(200, json={"count": body["count"], "artists": body["artists"]})
        if request.url.path == "/v3/quota":
            return httpx.Response(200, json=captured("jambase-quota.json"))
        key = request.url.params.get("geoStateIso")
        return httpx.Response(200, json=page_of(records if key == "US-CA" else []))

    redis = FakeAsyncRedis()
    settings = settings_with(
        jbd_api_key="unused", supabase_url=SUPABASE_URL, supabase_secret_key=SECRET
    )
    services = make_services(settings, httpx.MockTransport(handle), redis)
    steps = await sync.run(services, MOMENT)
    assert all(s.error is None for s in steps)
    # The captured Lodge Room show has Hit the Lights, Forever Came Calling, Fox Royale.
    assert ("forever came calling", "hit the lights") in rpc.edges
    assert ("fox royale", "hit the lights") in rpc.edges
    edge_before = rpc.edges[("forever came calling", "hit the lights")]

    # Re-syncing the exact same Concert never double-counts its edges.
    await cobilling.ingest_concerts(
        services.supabase,
        services.supabase_secret_key,
        [concert(records[0]["identifier"], "Hit the Lights", "Forever Came Calling", "Fox Royale")],
        TODAY,
    )
    assert rpc.edges[("forever came calling", "hit the lights")] == edge_before

    # When Supabase is down, /sync still succeeds cleanly.
    def handle_down(request: httpx.Request) -> httpx.Response:
        if request.url.host == "supabase.test":
            return httpx.Response(503)
        return handle(request)

    down_services = make_services(settings, httpx.MockTransport(handle_down), FakeAsyncRedis())
    down_steps = await sync.run(down_services, MOMENT)
    assert all(s.error is None for s in down_steps)


async def test_pool_refresh_callback_fires_only_on_cache_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bill = concert("tm-bill", "Four Tet", "Floating Points")
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[bill]))
    refreshed: list[list[str]] = []
    redis = FakeAsyncRedis()

    async with ticketmaster.make_client("unused", httpx.MockTransport(forbidden_http)) as tm:
        await pool.find_concerts(
            tm,
            idle_musicbrainz(),
            redis,
            PLACE,
            [],
            DAY,
            DAY,
            NOW,
            on_refresh=lambda cs: refreshed.append([c.id for c in cs]),
        )
        await pool.find_concerts(
            tm,
            idle_musicbrainz(),
            redis,
            PLACE,
            [],
            DAY,
            DAY,
            NOW,
            on_refresh=lambda cs: refreshed.append([c.id for c in cs]),
        )

    assert refreshed == [["tm-bill"]]


async def test_pipeline_queries_cobilling_in_parallel_with_find_taste_and_ingests_refreshes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = InMemoryCoBillingRPC()
    # Pre-seed the co-billing graph with a live bill connecting Four Tet and Underground Peer.
    async with supabase.make_client(SUPABASE_URL, httpx.MockTransport(rpc.handle)) as client:
        await cobilling.ingest_concerts(
            client, SECRET, [concert("past-bill", "Four Tet", "Underground Peer")], TODAY
        )

    taste_started = asyncio.Event()
    cobilling_started = asyncio.Event()
    real_find_peers = cobilling.find_peers

    async def synchronized_resolve(client: httpx.AsyncClient, redis: Any, name: str) -> SeedArtist:
        taste_started.set()
        await asyncio.wait_for(cobilling_started.wait(), timeout=2.0)
        return SeedArtist(name=name)

    async def synchronized_peers(
        client: httpx.AsyncClient | None,
        secret_key: SecretStr | None,
        seeds: Any,
        limit: int = cobilling.NEIGHBOR_LIMIT,
    ) -> dict[str, list[CoBilledPeer]]:
        cobilling_started.set()
        await asyncio.wait_for(taste_started.wait(), timeout=2.0)
        return await real_find_peers(client, secret_key, seeds, limit)

    upcoming = concert("upcoming-peer", "Underground Peer", "Local Opener")
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    monkeypatch.setattr(musicbrainz, "resolve", synchronized_resolve)
    monkeypatch.setattr(cobilling, "find_peers", synchronized_peers)
    monkeypatch.setattr(similarity, "find_neighbours", AsyncMock(return_value=[]))
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[upcoming]))
    monkeypatch.setattr(ticketmaster, "find_artist_concerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(listenbrainz.TagFetch, "tags", AsyncMock(return_value={}))
    monkeypatch.setattr(jev, "grade", contract_grades)
    monkeypatch.setattr(ranker, "explain", AsyncMock(side_effect=ranker.RankerError("fallback")))

    model = model_returning(interpretation(artists=["Four Tet"], place="San Francisco"))
    settings = settings_with(supabase_url=SUPABASE_URL, supabase_secret_key=SECRET)
    services = make_services(settings, httpx.MockTransport(rpc.handle), FakeAsyncRedis(), model)

    events = [
        (event.event, event.data)
        async for event in pipeline.stream_search("Four Tet in SF", [], None, services, NOW)
    ]

    assert taste_started.is_set() and cobilling_started.is_set()
    poster = dict(events)["poster"]
    assert poster is not None
    recs = poster["recommendations"]
    assert [r["concert"]["id"] for r in recs] == ["upcoming-peer"]
    assert recs[0]["reason"] == "Shares bills with Four Tet"
    # The freshly fetched Ticketmaster bill was also ingested asynchronously into the graph.
    assert ("local opener", "underground peer") in rpc.edges


async def test_pipeline_succeeds_when_supabase_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upcoming = concert("seed-show", "Four Tet")
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    monkeypatch.setattr(musicbrainz, "resolve", AsyncMock(return_value=SeedArtist(name="Four Tet")))
    monkeypatch.setattr(similarity, "find_neighbours", AsyncMock(return_value=[]))
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[upcoming]))
    monkeypatch.setattr(ticketmaster, "find_artist_concerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(listenbrainz.TagFetch, "tags", AsyncMock(return_value={}))
    monkeypatch.setattr(jev, "grade", contract_grades)
    monkeypatch.setattr(ranker, "explain", AsyncMock(side_effect=ranker.RankerError("fallback")))

    model = model_returning(interpretation(artists=["Four Tet"], place="San Francisco"))
    settings = settings_with(supabase_url=SUPABASE_URL, supabase_secret_key=SECRET)
    services = make_services(
        settings, httpx.MockTransport(lambda _: httpx.Response(503)), FakeAsyncRedis(), model
    )

    events = [
        (event.event, event.data)
        async for event in pipeline.stream_search("Four Tet in SF", [], None, services, NOW)
    ]

    assert events[-1] == ("done", {})
    assert "error" not in dict(events)
    poster = dict(events)["poster"]
    assert poster is not None
    assert [r["concert"]["id"] for r in poster["recommendations"]] == ["seed-show"]


async def test_warm_ingests_refreshed_ticketmaster_bills(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = InMemoryCoBillingRPC()
    monkeypatch.setattr(warm, "PLACES", ("San Francisco, California, United States",))
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    bill = concert("warm-bill", "Four Tet", "Caribou")
    monkeypatch.setattr(ticketmaster, "find_concerts", AsyncMock(return_value=[bill]))
    monkeypatch.setattr(listenbrainz.TagFetch, "tags", AsyncMock(return_value={}))

    settings = settings_with(supabase_url=SUPABASE_URL, supabase_secret_key=SECRET)
    services = make_services(settings, httpx.MockTransport(rpc.handle), FakeAsyncRedis())
    [warmed] = await warm.warm(services, NOW)

    assert warmed.error is None
    assert ("caribou", "four tet") in rpc.edges


async def test_app_creates_and_closes_supabase_client_for_cobilling() -> None:
    app = create_app(
        settings_with(supabase_url=SUPABASE_URL, supabase_secret_key=SECRET),
        httpx.MockTransport(forbidden_http),
        FakeAsyncRedis(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.supabase
async def test_supabase_migration_accumulates_deduplicates_and_enforces_rls() -> None:
    person = stack.new_person()
    secret = SecretStr(stack.secret_key())
    tag = f"cobill-{person.id[:8]}"
    a_name, b_name, c_name = f"{tag} alpha", f"{tag} beta", f"{tag} gamma"
    bills = [
        concert(f"{tag}-1", b_name, a_name, date=dt.date(2026, 11, 10)),
        concert(f"{tag}-2", c_name, b_name, a_name, date=dt.date(2026, 11, 15)),
        concert(f"{tag}-mega", *(f"{tag} act {i}" for i in range(41)), date=dt.date(2026, 11, 16)),
    ]

    async with supabase.make_client(stack.URL) as client:
        first = await cobilling.ingest_concerts(client, secret, bills, TODAY)
        second = await cobilling.ingest_concerts(client, secret, bills, TODAY)
        peers = await cobilling.find_peers(client, secret, [b_name])

    assert (first, second) == (2, 0)
    assert [(p.artist_key, p.weight, p.shared_shows) for p in peers[b_name]] == [
        (a_name, 2.0, 2),
        (c_name, 1.0, 1),
    ]

    # Browser roles cannot read, write, or invoke co-billing RPCs.
    with stack.rest(person.token) as rest:
        assert rest.get("/artist_cobilling").status_code in (401, 403)
        assert rest.get("/cobilling_seen_concerts").status_code in (401, 403)
        assert rest.post("/rpc/cobilling_neighbors", json={"p_artists": [b_name]}).status_code in (
            401,
            403,
        )
        assert rest.post("/rpc/record_cobilling_bills", json={"p_bills": []}).status_code in (
            401,
            403,
        )
