"""Hybrid semantic retrieval: Sonic Cards, graph propagation, pool scoring and fallback."""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from google.genai import types as genai_types
from pydantic import SecretStr
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingModel, EmbeddingResult
from pydantic_ai.embeddings.google import GoogleEmbeddingModel
from pydantic_ai.embeddings.result import EmbedInputType
from pydantic_ai.embeddings.settings import EmbeddingSettings
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.usage import RequestUsage

from concert_scout import (
    assemble,
    catalog,
    embeddings,
    limits,
    matching,
    pipeline,
    ranker,
    similarity,
    sync,
    telemetry,
    warm,
)
from concert_scout.app import make_services
from concert_scout.matching import CoBilledPeer, Taste
from concert_scout.models import Artist, ArtistProfile, Concert, Reading, SeedArtist
from concert_scout.names import normalize
from concert_scout.sources import (
    embedder as embedding_api,
)
from concert_scout.sources import (
    geocoder,
    jambase,
    jev,
    lastfm,
    listenbrainz,
    musicbrainz,
    supabase,
    ticketmaster,
)
from tests import supabase_stack as stack
from tests.conftest import interpretation, model_returning
from tests.contracts import NOW, PLACE, contract_grades, forbidden_http, settings_with
from tests.test_cobilling import SECRET, SUPABASE_URL, InMemoryCoBillingRPC, concert
from tests.test_jambase import MOMENT, TODAY, captured, page_of

DIMENSIONS = embedding_api.DIMENSIONS


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def hashed(text: str) -> list[float]:
    """A bag of words in 512 buckets, so texts that share words share direction."""
    vector = [0.0] * DIMENSIONS
    for word in words(text):
        vector[int.from_bytes(hashlib.sha256(word.encode()).digest()[:4]) % DIMENSIONS] += 1.0
    return vector


class HashingModel(EmbeddingModel):
    """A typed fake at the embedder boundary. It never touches the network."""

    def __init__(self) -> None:
        super().__init__(settings={"dimensions": DIMENSIONS})
        self.calls: list[tuple[EmbedInputType, list[str]]] = []
        self.fail = False
        self.on_embed: Any = None

    @property
    def model_name(self) -> str:
        return "hashing"

    @property
    def system(self) -> str:
        return "test"

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        texts, _ = self.prepare_embed(inputs, settings)
        self.calls.append((input_type, texts))
        if self.on_embed:
            await self.on_embed()
        if self.fail:
            raise UnexpectedModelBehavior("embedding unavailable")
        return EmbeddingResult(
            embeddings=[hashed(t) for t in texts],
            inputs=texts,
            input_type=input_type,
            usage=RequestUsage(),
            model_name="hashing",
            provider_name="test",
        )

    @property
    def embedded_documents(self) -> list[str]:
        return [t for kind, texts in self.calls if kind == "document" for t in texts]


class FakeVectors(InMemoryCoBillingRPC):
    """The Supabase vector functions, with exact cosine over what was stored."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: dict[str, dict[str, Any]] = {}
        self.score_keys: list[list[str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path != supabase.COBILLING_RECORD and path != supabase.COBILLING_NEIGHBORS:
            self.calls.append(request)
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        keys: set[str] = set(body.get("p_artists", []))
        if path == supabase.EMBEDDINGS_UPSERT:
            assert request.headers["apikey"] == SECRET.get_secret_value()
            rows: list[dict[str, Any]] = body["p_rows"]
            for row in rows:
                self.rows[row["artist_key"]] = row
            return httpx.Response(200, json=len(rows))
        if path == supabase.EMBEDDING_STATE:
            states = [
                {"artist_key": k, "tier": r["tier"], "card_hash": r["card_hash"]}
                for k, r in self.rows.items()
                if k in keys
            ]
            return httpx.Response(200, json=states)
        if path == supabase.EMBEDDINGS_FOR:
            vectors = [
                {
                    "artist_key": k,
                    "tier": r["tier"],
                    "card_hash": r["card_hash"],
                    "embedding": json.dumps(r["embedding"]),
                }
                for k, r in self.rows.items()
                if k in keys
            ]
            return httpx.Response(200, json=vectors)
        if path == supabase.SEMANTIC_SCORES:
            query: list[float] = json.loads(body["p_query"])
            self.score_keys.append(body["p_artists"])
            scores = [(k, cosine(query, r["embedding"])) for k, r in self.rows.items() if k in keys]
            kept = sorted((s for s in scores if s[1] >= body["p_floor"]), key=lambda s: -s[1])
            return httpx.Response(200, json=[{"artist_key": k, "cosine": c} for k, c in kept])
        return super().handle(request)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norms if norms else 0.0


def norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in vector))


def stored(rpc: FakeVectors, name: str, text: str, tier: int = 1) -> None:
    key = normalize(name)
    vector = embedding_api.unit(hashed(text))
    rpc.rows[key] = {
        "artist_key": key,
        "mbid": None,
        "tier": tier,
        "card_hash": embeddings.card_hash(text),
        "embedding": vector,
    }


# ---- Sonic Cards ------------------------------------------------------------------------------


def test_clean_bio_strips_markup_notices_and_caps_at_a_sentence() -> None:
    summary = (
        "<b>Moody</b> ambient producer from Leeds &amp; London. Their new album is out now. "
        "Tickets on sale Friday. There are at least 3 artists with this name. "
        + "A long closing sentence about drones and tape loops. " * 10
        + '<a href="https://www.last.fm/music/x">Read more on Last.fm</a>'
    )
    bio = embeddings.clean_bio(summary)
    assert bio is not None
    assert bio.startswith("Moody ambient producer from Leeds & London. A long closing sentence")
    assert "out now" not in bio and "Tickets" not in bio and "at least" not in bio
    assert "<" not in bio and len(bio) <= embeddings.BIO_LIMIT


def test_clean_bio_returns_none_for_nothing_useful_and_cuts_one_long_sentence() -> None:
    assert embeddings.clean_bio(None) is None
    assert embeddings.clean_bio("   ") is None
    assert embeddings.clean_bio("Tickets on sale now. Follow us on Last.fm.") is None
    long = embeddings.clean_bio("word " * 200)
    assert long is not None and len(long) <= embeddings.BIO_LIMIT


def test_clean_tags_drop_demographic_and_era_tags_and_keep_strength_order() -> None:
    tags = embeddings.clean_tags(
        ["UKG", "british", "seen live", "2-step", "1990s", "uk garage", "bass"]
    )
    assert tags == ["uk garage", "2 step garage", "bass"]


def test_sonic_card_is_deterministic_grounded_and_leaves_gaps_out() -> None:
    facts = embeddings.ArtistFacts(
        name="DJ Example",
        kind="Person",
        area="United Kingdom",
        genres=("Dance/Electronic", "House"),
        tags=("uk garage", "bass"),
        bio="Producer and DJ.",
        similar=tuple(f"Similar {i}" for i in range(15)),
        peers=tuple(CoBilledPeer(f"peer {i}", 1.0) for i in range(15)),
    )
    card = embeddings.sonic_card(facts)
    assert card == (
        "DJ Example. Type: Person. Country: United Kingdom. Genre: Dance/Electronic, House. "
        "Tags: uk garage, bass. About: Producer and DJ. "
        f"Similar artists: {', '.join(f'Similar {i}' for i in range(10))}. "
        f"Often shares bills with: {', '.join(f'peer {i}' for i in range(10))}."
    )
    assert embeddings.sonic_card(facts) == card
    assert embeddings.sonic_card(embeddings.ArtistFacts(name="Bare")) == "Bare."
    assert embeddings.card_hash(card) == hashlib.sha256(card.encode()).hexdigest()


def test_thin_means_under_two_tags_and_no_bio() -> None:
    assert embeddings.ArtistFacts(name="a", tags=("x",)).thin
    assert not embeddings.ArtistFacts(name="a", tags=("x", "y")).thin
    assert not embeddings.ArtistFacts(name="a", bio="Something.").thin


def test_centroid_is_a_weighted_unit_vector_and_none_for_nothing() -> None:
    result = embeddings.centroid([(3.0, [1.0, 0.0]), (1.0, [0.0, 1.0])])
    assert result is not None
    assert norm(result) == pytest.approx(1.0)
    assert result[0] == pytest.approx(3 / math.sqrt(10))
    assert embeddings.centroid([]) is None
    assert embeddings.centroid([(1.0, [1.0, 0.0]), (1.0, [-1.0, 0.0])]) is None


def test_taste_text_uses_only_the_readings_words() -> None:
    reading = Reading(
        artists=["Burial"],
        descriptors=["late night"],
        tags=["uk garage"],
        genres=["Dance/Electronic"],
        place="Portland",
    )
    text = embeddings.taste_text(reading)
    assert text == (
        "Music like Burial. Sound: late night. Tags: uk garage. Genre: Dance/Electronic."
    )
    assert "Portland" not in (text or "")
    assert embeddings.taste_text(Reading(place="Portland")) is None


# ---- The Gemini adapter -----------------------------------------------------------------------


async def test_gemini_adapter_asks_for_512_dimensions_and_the_right_task_on_the_api_key_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    embedder = embedding_api.make_embedder(SecretStr("not-a-real-key"))
    model = embedder.model
    assert isinstance(model, GoogleEmbeddingModel)
    assert model.model_name == "gemini-embedding-001"
    assert model.system == "google"
    assert "generativelanguage.googleapis.com" in model.base_url
    assert model._client.vertexai is False  # pyright: ignore[reportPrivateUsage]

    def response(count: int) -> genai_types.EmbedContentResponse:
        values = [float(i + 1) for i in range(DIMENSIONS)]
        return genai_types.EmbedContentResponse(
            embeddings=[genai_types.ContentEmbedding(values=values)] * count
        )

    async def answer(**kwargs: Any) -> genai_types.EmbedContentResponse:
        return response(len(kwargs["contents"]))

    call = AsyncMock(side_effect=answer)
    monkeypatch.setattr(
        model._client.aio.models,  # pyright: ignore[reportPrivateUsage]
        "embed_content",
        call,
    )
    # The SDK call is replaced above, so nothing leaves the machine.
    with override_allow_model_requests(True):
        query = await embedding_api.embed_query(embedder, FakeAsyncRedis(), "uk garage")
        documents = await embedding_api.embed_documents(embedder, ["a card", "another"])

    assert [c.kwargs["config"].task_type for c in call.call_args_list] == [
        "RETRIEVAL_QUERY",
        "RETRIEVAL_DOCUMENT",
    ]
    assert {c.kwargs["config"].output_dimensionality for c in call.call_args_list} == {512}
    assert norm(query) == pytest.approx(1.0)
    assert [norm(d) for d in documents] == [pytest.approx(1.0)] * 2


async def test_embedder_rejects_a_wrong_shape_and_hides_the_text_in_errors() -> None:
    model = HashingModel()
    embedder = Embedder(model)
    redis = FakeAsyncRedis()
    secret_text = "private Search words"
    model.fail = True
    with pytest.raises(embedding_api.EmbedderError) as failed:
        await embedding_api.embed_query(embedder, redis, secret_text)
    assert secret_text not in str(failed.value)

    short = Embedder(
        AsyncMock(spec=EmbeddingModel, embed=AsyncMock(return_value=_short_result()))  # pyright: ignore[reportArgumentType]
    )
    with pytest.raises(embedding_api.EmbedderError, match="shape"):
        await embedding_api.embed_documents(short, ["x"])


def _short_result() -> EmbeddingResult:
    return EmbeddingResult(
        embeddings=[[1.0, 2.0]],
        inputs=["x"],
        input_type="document",
        usage=RequestUsage(),
        model_name="short",
        provider_name="test",
    )


async def test_query_vectors_are_cached_for_six_hours_under_a_hashed_key() -> None:
    model = HashingModel()
    embedder = Embedder(model)
    redis = FakeAsyncRedis()
    first = await embedding_api.embed_query(embedder, redis, "ambient electronic")
    second = await embedding_api.embed_query(embedder, redis, "ambient electronic")

    assert first == second and len(model.calls) == 1
    [key] = cast(list[bytes], await redis.keys("embed:query:*"))  # pyright: ignore[reportUnknownMemberType]
    assert b"ambient" not in key
    assert 0 < await redis.ttl(key) <= 6 * 3600


async def test_embedding_cost_counts_toward_a_searchs_spend() -> None:
    model = HashingModel()
    with telemetry.search() as usage:
        await embedding_api.embed_documents(Embedder(model), ["x" * 400, "y" * 400])
    assert usage.input_tokens == 200
    assert usage.cost == 200 * limits.EMBEDDING_USD_PER_MILLION_TOKENS / limits.MICRODOLLARS
    assert usage.complete


# ---- Backfill and incremental updates ---------------------------------------------------------

PROFILES = {
    "Bio Act": ArtistProfile(name="Bio Act", bio="Moody ambient producer. Tickets on sale now."),
}


def sources_for(rpc: FakeVectors, model: HashingModel, redis: FakeAsyncRedis) -> embeddings.Sources:
    return embeddings.Sources(
        embedder=Embedder(model),
        supabase=supabase.make_client(SUPABASE_URL, httpx.MockTransport(rpc.handle)),
        secret_key=SECRET,
        listenbrainz=listenbrainz.make_client(httpx.MockTransport(forbidden_http)),
        lastfm=lastfm.make_client("unused", httpx.MockTransport(forbidden_http)),
        redis=redis,
    )


def stub_sources(monkeypatch: pytest.MonkeyPatch, tags: list[str] | None = None) -> None:
    meta = {
        "m1": listenbrainz.ArtistMetadata(
            tags=tags or ["uk garage", "2 step garage"], kind="Person", area="United Kingdom"
        )
    }
    monkeypatch.setattr(listenbrainz, "artist_metadata", AsyncMock(return_value=meta))
    monkeypatch.setattr(listenbrainz, "similar_artists", AsyncMock(return_value=[]))

    async def profile(_: httpx.AsyncClient, __: object, name: str) -> ArtistProfile:
        return PROFILES.get(name, ArtistProfile(name=name))

    monkeypatch.setattr(lastfm, "artist_profile", profile)


ARTISTS = [
    Artist(name="Tagged Act", mbid="m1", genre="Dance/Electronic"),
    Artist(name="Bio Act"),
    Artist(name="Thin Opener"),
    Artist(name="Lonely Act"),
]


def seed_bills(rpc: FakeVectors) -> None:
    rpc.edges[("tagged act", "thin opener")] = (3.0, 3, TODAY)
    rpc.edges[("bio act", "thin opener")] = (1.0, 1, TODAY)


async def test_backfill_embeds_tier_one_cards_then_graph_centroids_and_skips_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    rpc, model = FakeVectors(), HashingModel()
    seed_bills(rpc)
    sources = sources_for(rpc, model, FakeAsyncRedis())

    first = await embeddings.embed_artists(ARTISTS, sources)

    assert (first.card, first.graph, first.unplaced, first.unchanged) == (2, 1, 1, 0)
    assert first.looked_up == 4 and not first.failed
    assert set(rpc.rows) == {"tagged act", "bio act", "thin opener"}
    assert [rpc.rows[k]["tier"] for k in ("tagged act", "bio act", "thin opener")] == [1, 1, 2]
    assert all(norm(r["embedding"]) == pytest.approx(1.0) for r in rpc.rows.values())
    assert all(len(r["embedding"]) == DIMENSIONS for r in rpc.rows.values())

    # The card is source facts only, in the fixed order.
    [tagged_card] = [t for t in model.embedded_documents if t.startswith("Tagged Act")]
    assert tagged_card.startswith(
        "Tagged Act. Type: Person. Country: United Kingdom. Genre: Dance/Electronic. "
        "Tags: uk garage, 2 step garage."
    )
    assert "Tickets" not in " ".join(model.embedded_documents)
    # Tier 2 costs no embedding call: it is the weighted centroid of its peers' vectors.
    assert len(model.embedded_documents) == 2
    expected = embeddings.centroid(
        [(3.0, rpc.rows["tagged act"]["embedding"]), (1.0, rpc.rows["bio act"]["embedding"])]
    )
    assert expected is not None
    assert rpc.rows["thin opener"]["embedding"] == pytest.approx(expected)

    # Nothing changed, so a second run makes no embedding call and rewrites nothing.
    calls = len(model.calls)
    rewritten = dict(rpc.rows)
    second = await embeddings.embed_artists(ARTISTS, sources)
    assert (second.card, second.graph, second.unchanged) == (0, 0, 3)
    assert len(model.calls) == calls and rpc.rows == rewritten


async def test_a_changed_card_is_re_embedded_and_a_changed_peer_moves_the_centroid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    rpc, model = FakeVectors(), HashingModel()
    seed_bills(rpc)
    sources = sources_for(rpc, model, FakeAsyncRedis())
    await embeddings.embed_artists(ARTISTS, sources)
    before = dict(rpc.rows)

    stub_sources(monkeypatch, tags=["jungle", "drum and bass"])
    report = await embeddings.embed_artists(ARTISTS, sources)

    assert (report.card, report.graph, report.unchanged) == (1, 1, 1)
    assert rpc.rows["tagged act"]["card_hash"] != before["tagged act"]["card_hash"]
    assert rpc.rows["thin opener"]["card_hash"] != before["thin opener"]["card_hash"]
    assert rpc.rows["bio act"] == before["bio act"]


async def test_only_new_leaves_stored_artists_alone_and_limit_bounds_the_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    rpc, model = FakeVectors(), HashingModel()
    sources = sources_for(rpc, model, FakeAsyncRedis())
    stored(rpc, "Tagged Act", "Tagged Act. Tags: old.")

    report = await embeddings.embed_artists(ARTISTS, sources, only_new=True, limit=1)

    assert report.looked_up == 1
    assert "Tagged Act" not in " ".join(model.embedded_documents)
    assert set(rpc.rows) == {"tagged act", "bio act"}


async def test_a_thin_artist_waits_for_peers_with_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    rpc, model = FakeVectors(), HashingModel()
    rpc.edges[("lonely act", "unembedded peer")] = (1.0, 1, TODAY)
    sources = sources_for(rpc, model, FakeAsyncRedis())

    report = await embeddings.embed_artists([Artist(name="Lonely Act")], sources)

    assert (report.unplaced, report.card, report.graph) == (1, 0, 0)
    assert rpc.rows == {} and model.calls == []


async def test_graph_vectors_never_average_other_graph_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    rpc, model = FakeVectors(), HashingModel()
    stored(rpc, "Tier Two Peer", "Tier Two Peer. Tags: x.", tier=2)
    rpc.edges[("thin one", "tier two peer")] = (1.0, 1, TODAY)
    sources = sources_for(rpc, model, FakeAsyncRedis())

    report = await embeddings.embed_artists([Artist(name="Thin One")], sources)

    assert report.unplaced == 1 and "thin one" not in rpc.rows


async def test_embedding_provider_failure_stops_the_run_and_keeps_what_was_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    rpc, model = FakeVectors(), HashingModel()
    model.fail = True
    sources = sources_for(rpc, model, FakeAsyncRedis())

    report = await embeddings.embed_artists(ARTISTS, sources)

    assert report.failed and rpc.rows == {}


async def test_supabase_outage_stops_the_run_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)
    model = HashingModel()
    sources = embeddings.Sources(
        embedder=Embedder(model),
        supabase=supabase.make_client(
            SUPABASE_URL, httpx.MockTransport(lambda _: httpx.Response(503))
        ),
        secret_key=SECRET,
        listenbrainz=listenbrainz.make_client(httpx.MockTransport(forbidden_http)),
        lastfm=None,
        redis=FakeAsyncRedis(),
    )
    report = await embeddings.embed_artists(ARTISTS, sources)
    assert report.failed and model.calls == []


async def test_artist_metadata_reads_type_area_and_strongest_tags_first_and_caches() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "artist_mbid": "m1",
                    "type": "Group",
                    "area": "United Kingdom",
                    "tag": {"artist": [{"tag": "weak", "count": 1}, {"tag": "strong", "count": 9}]},
                }
            ],
        )

    redis = FakeAsyncRedis()
    client = listenbrainz.make_client(httpx.MockTransport(handle))
    first = await listenbrainz.artist_metadata(client, redis, ["m1", "m2"])
    again = await listenbrainz.artist_metadata(client, redis, ["m1", "m2"])

    assert first["m1"].tags == ["strong", "weak"]
    assert (first["m1"].kind, first["m1"].area) == ("Group", "United Kingdom")
    assert first["m2"] == listenbrainz.ArtistMetadata()
    assert again == first and len(seen) == 1

    down = listenbrainz.make_client(httpx.MockTransport(lambda _: httpx.Response(503)))
    assert await listenbrainz.artist_metadata(down, FakeAsyncRedis(), ["m1"]) == {}


async def test_catalog_lists_every_artist_once_with_settled_ids() -> None:
    redis = FakeAsyncRedis()
    listing = jambase.Listing(
        concert=concert("jambase:1", "Hit the Lights", "Fox Royale", date=TODAY),
        latitude=34.0,
        longitude=-118.0,
    )
    await catalog.store(redis, [listing], [], TODAY)
    await catalog.settle(redis, {"Fox Royale": "fox-mbid"}, TODAY)

    artists = await catalog.all_artists(redis, TODAY)

    assert {(a.name, a.mbid) for a in artists} == {
        ("Hit the Lights", None),
        ("Fox Royale", "fox-mbid"),
    }


# ---- Matching stays pure ----------------------------------------------------------------------


def test_semantic_score_stretches_from_the_floor_and_ignores_the_unrelated() -> None:
    taste = Taste(
        [],
        [],
        [],
        semantic={
            "twin": 1.0,
            "close": 0.8,
            "borderline": matching.SEMANTIC_FLOOR,
            "far": 0.1,
        },
    )
    candidates = matching.score_concerts(
        [concert(n, n.title()) for n in ("twin", "close", "borderline", "far", "unknown")],
        taste,
        {},
    )
    matches = {c.concert.id: c.match for c in candidates}

    twin, close = matches["twin"], matches["close"]
    assert twin is not None and close is not None
    assert twin.signal == "semantic" and twin.score == pytest.approx(matching.SEMANTIC_WEIGHT)
    expected = (
        matching.SEMANTIC_WEIGHT * (0.8 - matching.SEMANTIC_FLOOR) / (1 - matching.SEMANTIC_FLOOR)
    )
    assert close.score == pytest.approx(expected)
    assert twin.score > close.score > 0
    assert twin.via is None
    assert matches["borderline"] is None and matches["far"] is None and matches["unknown"] is None


def test_semantic_scores_make_a_taste_and_add_to_support() -> None:
    assert Taste([], [], [], semantic={"x": 0.9})
    assert not Taste([], [], [])
    seed = SeedArtist(name="Four Tet")
    taste = Taste(
        [seed],
        [],
        [],
        cobilling={"Four Tet": [CoBilledPeer(artist_key="both", weight=1.0)]},
        semantic={"both": 0.9, "only semantic": 0.9},
    )
    both, only = matching.score_concerts(
        [concert("1", "Both"), concert("2", "Only Semantic")], taste, {}
    )
    assert both.match is not None and only.match is not None
    assert both.match.signal == "co_billed"
    semantic_alone = only.match.score
    assert both.match.support == pytest.approx(both.match.score + semantic_alone)
    assert both.match.support > only.match.support


def test_semantic_matches_name_a_festival_lineup_and_read_neutrally() -> None:
    taste = Taste([], [], [], semantic={"close act": 0.85, "barely": 0.43})
    fest = concert("fest", "Nobody", "Close Act", "Barely", festival=True)
    [candidate] = matching.score_concerts([fest], taste, {})

    assert candidate.lineup_match == ["Close Act"]
    assert candidate.match is not None
    assert assemble.from_matches([candidate])[0].reason == "Close Act sounds close to your Search"


# ---- The pipeline -----------------------------------------------------------------------------

# The shortlist keeps 40, so an Artist 45 places down only gets in by scoring.
FILLER = [concert(f"filler-{i}", f"Filler {i}") for i in range(45)]
GARAGE = "Garage Act. Tags: uk garage, 2 step garage."
METAL = "Metal Act. Tags: thrash metal, heavy metal."


def patch_pipeline(monkeypatch: pytest.MonkeyPatch, pool_concerts: list[Concert]) -> AsyncMock:
    find = AsyncMock(return_value=pool_concerts)
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    monkeypatch.setattr(musicbrainz, "resolve", AsyncMock(return_value=SeedArtist(name="x")))
    monkeypatch.setattr(similarity, "find_neighbours", AsyncMock(return_value=[]))
    monkeypatch.setattr(ticketmaster, "find_concerts", find)
    monkeypatch.setattr(ticketmaster, "find_artist_concerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(listenbrainz.TagFetch, "tags", AsyncMock(return_value={}))
    monkeypatch.setattr(jev, "grade", contract_grades)
    monkeypatch.setattr(ranker, "explain", AsyncMock(side_effect=ranker.RankerError("neutral")))
    return find


UKG = interpretation(descriptors=["uk garage"], tags=["uk garage"], place="San Francisco")


async def poster_ids(
    rpc: FakeVectors,
    model: HashingModel | None,
    *,
    transport: httpx.MockTransport | None = None,
    reading: dict[str, Any] = UKG,
) -> tuple[list[str], list[tuple[str | None, Any]]]:
    settings = settings_with(supabase_url=SUPABASE_URL, supabase_secret_key=SECRET)
    services = make_services(
        settings,
        transport or httpx.MockTransport(rpc.handle),
        FakeAsyncRedis(),
        model_returning(reading),
    )
    if model:
        services = replace(services, embedder=Embedder(model))
    events = [
        (e.event, e.data)
        async for e in pipeline.stream_search("uk garage", [], None, services, NOW)
    ]
    poster = dict(events).get("poster")
    ids = [r["concert"]["id"] for r in poster["recommendations"]] if poster else []
    return ids, events


async def test_semantic_retrieval_surfaces_an_artist_no_tag_or_peer_reaches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_pipeline(
        monkeypatch, [*FILLER, concert("metal", "Metal Act"), concert("garage", "Garage Act")]
    )
    rpc = FakeVectors()
    stored(rpc, "Garage Act", GARAGE)
    stored(rpc, "Metal Act", METAL)

    without, _ = await poster_ids(rpc, None)
    with_it, events = await poster_ids(rpc, HashingModel())

    # No tags, seeds or peers: today's matching leaves the 46th Concert off the shortlist.
    assert "garage" not in without
    assert with_it[0] == "garage" and "metal" not in with_it[:1]
    [scored] = [c for c in rpc.calls if c.url.path == supabase.SEMANTIC_SCORES]
    body = json.loads(scored.content)
    # Only the pool's Artists are asked about, and only above the floor.
    assert sorted(body["p_artists"]) == sorted(
        [normalize(a.name) for c in [*FILLER, concert("m", "Metal Act")] for a in c.artists]
        + ["garage act"]
    )
    assert body["p_floor"] == matching.SEMANTIC_FLOOR
    assert "error" not in dict(events)


async def test_query_embedding_runs_beside_the_pool_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool_started, embed_started = asyncio.Event(), asyncio.Event()
    pool_concerts = [*FILLER, concert("garage", "Garage Act")]
    find = patch_pipeline(monkeypatch, pool_concerts)

    async def pool_waits_for_the_embedding(*_: Any, **__: Any) -> list[Concert]:
        pool_started.set()
        await asyncio.wait_for(embed_started.wait(), timeout=2.0)
        return pool_concerts

    find.side_effect = pool_waits_for_the_embedding
    model = HashingModel()

    async def embed_waits_for_the_pool() -> None:
        embed_started.set()
        await asyncio.wait_for(pool_started.wait(), timeout=2.0)

    model.on_embed = embed_waits_for_the_pool
    rpc = FakeVectors()
    stored(rpc, "Garage Act", GARAGE)

    ids, _ = await poster_ids(rpc, model)

    assert pool_started.is_set() and embed_started.is_set()
    assert ids[0] == "garage"


async def test_search_with_no_embeddings_configured_is_exactly_todays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_pipeline(monkeypatch, [*FILLER, concert("garage", "Garage Act")])
    rpc = FakeVectors()
    stored(rpc, "Garage Act", GARAGE)

    settings = settings_with(supabase_url=SUPABASE_URL, supabase_secret_key=SECRET)
    assert make_services(settings).embedder is None
    ids, _ = await poster_ids(rpc, None)

    assert "garage" not in ids
    assert not [c for c in rpc.calls if "semantic" in c.url.path]


async def test_embedding_needs_both_a_google_key_and_supabase() -> None:
    key = SecretStr("not-a-real-key")
    both = settings_with(google_api_key=key, supabase_url=SUPABASE_URL, supabase_secret_key=SECRET)
    no_supabase = settings_with(google_api_key=key)
    assert make_services(both).embedding_sources() is not None
    assert make_services(no_supabase).embedder is None
    assert make_services(no_supabase).embedding_sources() is None


@pytest.mark.parametrize("failure", ["embedder", "supabase", "no vectors"])
async def test_semantic_failures_leave_the_search_as_it_was(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    pool_concerts = [concert("seed-show", "Four Tet"), *FILLER, concert("garage", "Garage Act")]
    patch_pipeline(monkeypatch, pool_concerts)
    monkeypatch.setattr(musicbrainz, "resolve", AsyncMock(return_value=SeedArtist(name="Four Tet")))
    reading = interpretation(artists=["Four Tet"], tags=["uk garage"], place="San Francisco")
    rpc = FakeVectors()
    model = HashingModel()
    transport = httpx.MockTransport(rpc.handle)
    if failure == "embedder":
        stored(rpc, "Garage Act", GARAGE)
        model.fail = True
    elif failure == "supabase":
        transport = httpx.MockTransport(lambda _: httpx.Response(503))

    baseline, _ = await poster_ids(FakeVectors(), None, reading=reading)
    ids, events = await poster_ids(rpc, model, transport=transport, reading=reading)

    assert ids == baseline and ids[0] == "seed-show" and "garage" not in ids
    assert events[-1] == ("done", {})
    assert "error" not in dict(events)


async def test_semantic_lookup_that_hangs_gives_way_to_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(embeddings, "LOOKUP_SECONDS", 0.05)

    async def hang(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=[])

    client = supabase.make_client(SUPABASE_URL, httpx.MockTransport(hang))
    assert await embeddings.pool_scores(client, SECRET, [1.0] * DIMENSIONS, ["a"]) == {}


async def test_query_embedding_that_hangs_gives_way_to_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(embeddings, "QUERY_SECONDS", 0.05)
    model = HashingModel()

    async def hang() -> None:
        await asyncio.sleep(5)

    model.on_embed = hang
    reading = Reading(tags=["uk garage"])
    assert await embeddings.query_vector(Embedder(model), FakeAsyncRedis(), reading) is None
    assert await embeddings.query_vector(Embedder(model), FakeAsyncRedis(), Reading()) is None


async def test_pool_scores_only_ask_about_normalized_pool_names() -> None:
    rpc = FakeVectors()
    stored(rpc, "Garage Act", GARAGE)
    client = supabase.make_client(SUPABASE_URL, httpx.MockTransport(rpc.handle))
    query = embedding_api.unit(hashed("uk garage"))

    scores = await embeddings.pool_scores(client, SECRET, query, ["The Garage Act", "Garage Act"])

    assert rpc.score_keys == [["garage act"]]
    assert set(scores) == {"garage act"} and scores["garage act"] > matching.SEMANTIC_FLOOR
    assert await embeddings.pool_scores(client, SECRET, query, []) == {}
    assert len(rpc.score_keys) == 1


# ---- /sync ------------------------------------------------------------------------------------


async def run_sync(
    monkeypatch: pytest.MonkeyPatch, rpc: FakeVectors, model: HashingModel | None
) -> list[sync.Step]:
    monkeypatch.setattr(sync, "REQUEST_GAP", 0)
    monkeypatch.setattr(warm, "PLACES", ("San Francisco, California, United States",))
    monkeypatch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    records = captured("jambase-lodge.json")["events"]

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

    settings = settings_with(
        jbd_api_key="unused",
        lastfm_key="unused",
        supabase_url=SUPABASE_URL,
        supabase_secret_key=SECRET,
    )
    services = make_services(settings, httpx.MockTransport(handle), FakeAsyncRedis())
    if model:
        services = replace(services, embedder=Embedder(model))
    return await sync.run(services, MOMENT)


async def test_sync_embeds_new_catalog_artists_and_never_blocks_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sources(monkeypatch)

    async def described(_: httpx.AsyncClient, __: object, name: str) -> ArtistProfile:
        return ArtistProfile(name=name, bio="A live act.")

    monkeypatch.setattr(lastfm, "artist_profile", described)
    rpc, model = FakeVectors(), HashingModel()
    steps = await run_sync(monkeypatch, rpc, model)

    step = next(s for s in steps if s.name == "embeddings")
    assert step.error is None and step.stored > 0
    # The captured Lodge Room bill: Hit the Lights, Forever Came Calling and Fox Royale.
    assert {"hit the lights", "forever came calling", "fox royale"} <= set(rpc.rows)
    assert all(s.error is None for s in steps)

    broken = HashingModel()
    broken.fail = True
    steps = await run_sync(monkeypatch, FakeVectors(), broken)
    assert next(s for s in steps if s.name == "embeddings").error == "stopped early"
    assert all(s.error is None for s in steps if s.name != "embeddings")


async def test_sync_without_a_google_key_has_no_embedding_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = await run_sync(monkeypatch, FakeVectors(), None)
    assert "embeddings" not in {s.name for s in steps}


# ---- The real Supabase stack ------------------------------------------------------------------


@pytest.mark.supabase
async def test_supabase_stores_scores_exactly_by_pool_and_keeps_vectors_server_only() -> None:
    person = stack.new_person()
    secret = SecretStr(stack.secret_key())
    tag = f"emb-{person.id[:8]}"
    near, far, outside = f"{tag} near", f"{tag} far", f"{tag} outside"
    query = embedding_api.unit(hashed("uk garage 2 step"))
    rows = [
        supabase.EmbeddingRow(
            artist_key=near,
            mbid="mbid-near",
            tier=1,
            card_hash=embeddings.card_hash("near"),
            embedding=embedding_api.unit(hashed("uk garage 2 step bass")),
        ),
        supabase.EmbeddingRow(
            artist_key=far,
            tier=2,
            card_hash=embeddings.card_hash("far"),
            embedding=embedding_api.unit(hashed("thrash metal")),
        ),
        supabase.EmbeddingRow(
            artist_key=outside,
            tier=1,
            card_hash=embeddings.card_hash("outside"),
            embedding=query,
        ),
    ]

    async with supabase.make_client(stack.URL) as client:
        assert await supabase.upsert_embeddings(client, secret, rows) == 3
        # A repeat replaces rather than duplicates.
        assert await supabase.upsert_embeddings(client, secret, rows[:1]) == 1
        states = await supabase.embedding_states(client, secret, [near, far, "nobody"])
        vectors = await supabase.stored_embeddings(client, secret, [near])
        everything = await supabase.semantic_scores(client, secret, query, [near, far], 0.0)
        floored = await supabase.semantic_scores(client, secret, query, [near, far], 0.3)

    assert {(s.artist_key, s.tier, s.card_hash) for s in states} == {
        (near, 1, embeddings.card_hash("near")),
        (far, 2, embeddings.card_hash("far")),
    }
    assert vectors[0].embedding == pytest.approx(rows[0].embedding, abs=1e-5)
    # Only the pool's keys are scored: `outside` is a perfect match but was not asked about.
    assert [s.artist_key for s in everything] == [near, far]
    expected = cosine(query, rows[0].embedding)
    assert everything[0].cosine == pytest.approx(expected, abs=1e-5)
    assert [s.artist_key for s in floored] == [near]

    # Browser roles cannot read, write or call any of it.
    with stack.rest(person.token) as rest:
        assert rest.get("/artist_embeddings").status_code in (401, 403)
        bodies: list[tuple[str, dict[str, Any]]] = [
            ("semantic_scores", {"p_query": json.dumps(query), "p_artists": [near]}),
            ("artist_embedding_state", {"p_artists": [near]}),
            ("artist_embeddings_for", {"p_artists": [near]}),
            ("upsert_artist_embeddings", {"p_rows": []}),
        ]
        for name, body in bodies:
            assert rest.post(f"/rpc/{name}", json=body).status_code in (401, 403)
