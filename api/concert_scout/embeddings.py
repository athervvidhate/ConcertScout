"""Hybrid semantic retrieval: grounded Sonic Cards, graph-propagated vectors, pool-scoped lookup.

An Artist's vector comes from public source facts only, never from a model's imagination
([ADR 0002](../../docs/adr/0002-facts-never-pass-through-the-llm.md)). Tier 1 embeds a Sonic Card
assembled from MusicBrainz, tags, Last.fm's summary, similar Artists and Co-Billed peers. Tier 2
gives a thin Artist the weighted centroid of their peers' Tier 1 vectors, with no model call.
A Search embeds its Taste words once, then scores only the Artists in its Concert pool.

Every network call here fails soft: a missing key, a dead provider or an Artist with no vector
leaves a Search exactly as it was without this signal.
"""

import asyncio
import hashlib
import html
import logging
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx
from pydantic import SecretStr
from pydantic_ai import Embedder
from redis.asyncio import Redis

from concert_scout import cobilling, matching
from concert_scout.matching import CoBilledPeer
from concert_scout.models import Artist, Reading
from concert_scout.names import normalize
from concert_scout.sources import embedder as embedding_api
from concert_scout.sources import lastfm, listenbrainz, supabase
from concert_scout.sources.embedder import Vector

logger = logging.getLogger(__name__)

TIER_CARD = 1
TIER_GRAPH = 2
# An Artist with fewer tags than this and no summary has too little to describe.
THIN_TAGS = 2
MAX_TAGS = 8
TOP_SIMILAR = 10
TOP_PEERS = 10
BIO_LIMIT = 300
MAX_KEY_LENGTH = cobilling.MAX_KEY_LENGTH
# Artists whose facts are gathered and embedded together.
BATCH_SIZE = 100
# Source lookups running at once across a batch.
FACT_LOOKUPS = 8
# A Search waits no longer than this for its Taste vector, which is embedded beside the pool fetch.
QUERY_SECONDS = 5.0
# A Search waits no longer than this for the pool's scores before going on without them.
LOOKUP_SECONDS = 2.0
# The most pool Artists one lookup scores.
MAX_POOL_KEYS = 5000

# Sentences in a Last.fm summary that say nothing about the sound.
BOILERPLATE = re.compile(
    r"\b(tour dates?|tickets?|on sale|pre-?orders?|out now|available now|new album out|"
    r"follow (us|him|her|them)|last\.?fm|wikipedia|read more|click|subscribe|"
    r"there (are|is) (at least )?\d+ (artists?|bands?))\b|https?://|www\.",
    re.IGNORECASE,
)
MARKUP = re.compile(r"<[^>]+>")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ArtistFacts:
    """Everything a Sonic Card is made from. A fact no source reported stays empty."""

    name: str
    mbid: str | None = None
    kind: str | None = None
    area: str | None = None
    genres: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    bio: str | None = None
    similar: tuple[str, ...] = ()
    peers: tuple[CoBilledPeer, ...] = ()

    @property
    def thin(self) -> bool:
        """Too little is known to describe them, so their peers will."""
        return len(self.tags) < THIN_TAGS and not self.bio


@dataclass
class Report:
    """What one run did, for the CLI and the sync log."""

    looked_up: int = 0
    card: int = 0
    graph: int = 0
    unchanged: int = 0
    # Thin Artists whose peers have no vectors yet, so there is nothing to average.
    unplaced: int = 0
    failed: bool = False


def clean_bio(summary: str | None) -> str | None:
    """A short plain summary, or None. Markup, links, tour notices and boilerplate go."""
    if not summary:
        return None
    text = " ".join(html.unescape(MARKUP.sub(" ", summary)).split())
    sentences = [s for s in SENTENCE_END.split(text) if s and not BOILERPLATE.search(s)]
    kept: list[str] = []
    length = 0
    for sentence in sentences:
        if length + len(sentence) > BIO_LIMIT:
            break
        kept.append(sentence)
        length += len(sentence) + 1
    if kept:
        return " ".join(kept)
    # One long first sentence still describes them, so cut it at a word.
    return sentences[0][:BIO_LIMIT].rsplit(" ", 1)[0] if sentences else None


def clean_tags(tags: Sequence[str]) -> list[str]:
    """Tags that describe a sound, strongest first, each once."""
    cleaned: dict[str, None] = {}
    for tag in tags:
        for usable in sorted(matching.usable_tags([tag])):
            cleaned.setdefault(usable)
    return list(cleaned)[:MAX_TAGS]


def sonic_card(facts: ArtistFacts) -> str:
    """The text that stands for an Artist. Same facts, same text, so the hash can skip repeats."""
    identity = " ".join(
        part
        for part in (
            f"Type: {facts.kind}." if facts.kind else "",
            f"Country: {facts.area}." if facts.area else "",
        )
        if part
    )
    peers = [p.artist_key for p in facts.peers[:TOP_PEERS]]
    sections = [
        f"{facts.name}.",
        identity,
        f"Genre: {', '.join(facts.genres)}." if facts.genres else "",
        f"Tags: {', '.join(facts.tags)}." if facts.tags else "",
        f"About: {facts.bio}" if facts.bio else "",
        f"Similar artists: {', '.join(facts.similar[:TOP_SIMILAR])}." if facts.similar else "",
        f"Often shares bills with: {', '.join(peers)}." if peers else "",
    ]
    return " ".join(section for section in sections if section)


def card_hash(card: str) -> str:
    return hashlib.sha256(card.encode()).hexdigest()


def graph_hash(peers: Sequence[tuple[CoBilledPeer, str]]) -> str:
    """What a centroid came from: each peer, their weight and the card behind their vector."""
    parts = sorted(f"{p.artist_key}@{p.weight:.3f}@{source}" for p, source in peers)
    return hashlib.sha256(b"graph\n" + "\n".join(parts).encode()).hexdigest()


def centroid(weighted: Sequence[tuple[float, Sequence[float]]]) -> Vector | None:
    """The weighted mean direction of unit vectors, or None when there is nothing to average."""
    if not weighted:
        return None
    total = [0.0] * len(weighted[0][1])
    for weight, vector in weighted:
        for i, x in enumerate(vector):
            total[i] += weight * x
    try:
        return embedding_api.unit(total)
    except embedding_api.EmbedderError:
        return None


def taste_text(reading: Reading) -> str | None:
    """The Search's Taste as the words to embed, or None for a Search with no Taste."""
    sections = [
        f"Music like {', '.join(reading.artists)}." if reading.artists else "",
        f"Sound: {', '.join(reading.descriptors)}." if reading.descriptors else "",
        f"Tags: {', '.join(reading.tags)}." if reading.tags else "",
        f"Genre: {', '.join(reading.genres)}." if reading.genres else "",
    ]
    text = " ".join(section for section in sections if section)
    return text or None


async def query_vector(embedder: Embedder, redis: Redis, reading: Reading) -> Vector | None:
    """The Taste's vector, or None with no Taste or no answer. Runs beside the pool fetch."""
    if not (text := taste_text(reading)):
        return None
    try:
        async with asyncio.timeout(QUERY_SECONDS):
            return await embedding_api.embed_query(embedder, redis, text)
    except (embedding_api.EmbedderError, TimeoutError) as exc:
        logger.warning("Query embedding failed: %s", type(exc).__name__)
        return None


async def pool_scores(
    client: httpx.AsyncClient,
    secret_key: SecretStr,
    query: Vector,
    names: Sequence[str],
) -> dict[str, float]:
    """Cosine similarity to the query for the pool's Artists that reach the floor, by normalized
    name. An Artist with no vector is absent, and any failure gives an empty answer."""
    keys = list(
        dict.fromkeys(
            key for name in names if (key := normalize(name)) and len(key) <= MAX_KEY_LENGTH
        )
    )[:MAX_POOL_KEYS]
    try:
        async with asyncio.timeout(LOOKUP_SECONDS):
            rows = await supabase.semantic_scores(
                client, secret_key, query, keys, matching.SEMANTIC_FLOOR
            )
    except (supabase.SupabaseError, TimeoutError) as exc:
        logger.warning("Semantic lookup failed: %s", type(exc).__name__)
        return {}
    return {row.artist_key: row.cosine for row in rows}


@dataclass(frozen=True)
class Sources:
    """Where Sonic Card facts come from, and where vectors are made and kept."""

    embedder: Embedder
    supabase: httpx.AsyncClient
    secret_key: SecretStr
    listenbrainz: httpx.AsyncClient
    lastfm: httpx.AsyncClient | None
    redis: Redis


async def embed_artists(
    artists: Sequence[Artist],
    sources: Sources,
    *,
    only_new: bool = False,
    limit: int | None = None,
    deadline: float | None = None,
) -> Report:
    """Store a vector for each Artist whose facts changed, or with `only_new`, who has none yet.

    `limit` stops the run once that many Artists have been looked up.

    Tier 1 vectors go first, so a thin Artist in the same run can take theirs as peers. A failure
    stops the run with what was stored kept, and the next run picks up from there.
    """
    report = Report()
    unique = {key: a for a in artists if (key := normalize(a.name)) and len(key) <= MAX_KEY_LENGTH}
    keys = list(unique)
    for start in range(0, len(keys), BATCH_SIZE):
        if deadline is not None and time.monotonic() > deadline:
            break
        if limit is not None and report.looked_up >= limit:
            break
        batch = {key: unique[key] for key in keys[start : start + BATCH_SIZE]}
        room = None if limit is None else limit - report.looked_up
        try:
            await _embed_batch(batch, sources, only_new, room, report)
        except (supabase.SupabaseError, embedding_api.EmbedderError) as exc:
            logger.warning("Embedding run stopped: %s", exc)
            report.failed = True
            break
    return report


async def _embed_batch(
    batch: Mapping[str, Artist],
    sources: Sources,
    only_new: bool,
    room: int | None,
    report: Report,
) -> None:
    client, secret = sources.supabase, sources.secret_key
    states = {s.artist_key: s for s in await supabase.embedding_states(client, secret, list(batch))}
    wanted = {k: a for k, a in batch.items() if not (only_new and k in states)}
    if room is not None:
        wanted = dict(list(wanted.items())[:room])
    if not wanted:
        return
    report.looked_up += len(wanted)
    facts = await _gather(wanted, sources)

    cards: dict[str, str] = {}
    for key, fact in facts.items():
        if fact.thin:
            continue
        card = sonic_card(fact)
        state = states.get(key)
        if state and state.tier == TIER_CARD and state.card_hash == card_hash(card):
            report.unchanged += 1
        else:
            cards[key] = card
    if cards:
        vectors = await embedding_api.embed_documents(sources.embedder, list(cards.values()))
        rows = [
            supabase.EmbeddingRow(
                artist_key=key,
                mbid=facts[key].mbid,
                tier=TIER_CARD,
                card_hash=card_hash(card),
                embedding=vector,
            )
            for (key, card), vector in zip(cards.items(), vectors, strict=True)
        ]
        await supabase.upsert_embeddings(client, secret, rows)
        report.card += len(rows)

    thin = {key: fact for key, fact in facts.items() if fact.thin}
    if thin:
        await _propagate(thin, states, sources, report)


async def _propagate(
    thin: Mapping[str, ArtistFacts],
    states: Mapping[str, supabase.EmbeddingState],
    sources: Sources,
    report: Report,
) -> None:
    """Tier 2: each thin Artist takes the weighted centroid of their peers' Tier 1 vectors."""
    client, secret = sources.supabase, sources.secret_key
    peer_keys = list(dict.fromkeys(p.artist_key for fact in thin.values() for p in fact.peers))
    stored = {
        e.artist_key: e
        for e in await supabase.stored_embeddings(client, secret, peer_keys)
        if e.tier == TIER_CARD
    }
    rows: list[supabase.EmbeddingRow] = []
    for key, fact in thin.items():
        used = [(p, stored[p.artist_key]) for p in fact.peers if p.artist_key in stored]
        if not used:
            report.unplaced += 1
            continue
        digest = graph_hash([(p, e.card_hash) for p, e in used])
        if (state := states.get(key)) and state.tier == TIER_GRAPH and state.card_hash == digest:
            report.unchanged += 1
            continue
        vector = centroid([(p.weight, e.embedding) for p, e in used])
        if vector is None:
            report.unplaced += 1
            continue
        rows.append(
            supabase.EmbeddingRow(
                artist_key=key, mbid=fact.mbid, tier=TIER_GRAPH, card_hash=digest, embedding=vector
            )
        )
    if rows:
        await supabase.upsert_embeddings(client, secret, rows)
        report.graph += len(rows)


async def _gather(wanted: Mapping[str, Artist], sources: Sources) -> dict[str, ArtistFacts]:
    """Facts for each Artist from every source, in a few batched calls and one per Artist."""
    names = [a.name for a in wanted.values()]
    mbids = [a.mbid for a in wanted.values() if a.mbid]
    metadata, peers = await asyncio.gather(
        listenbrainz.artist_metadata(sources.listenbrainz, sources.redis, mbids),
        cobilling.find_peers(sources.supabase, sources.secret_key, names),
    )
    slots = asyncio.Semaphore(FACT_LOOKUPS)

    async def one(key: str, artist: Artist) -> tuple[str, ArtistFacts]:
        async with slots:
            profile_tags, bio, similar = await _from_profiles(artist, sources)
        meta = metadata.get(artist.mbid or "", listenbrainz.ArtistMetadata())
        return key, ArtistFacts(
            name=artist.name,
            mbid=artist.mbid,
            kind=meta.kind,
            area=meta.area,
            genres=tuple(dict.fromkeys(g for g in (artist.genre, artist.subgenre) if g)),
            tags=tuple(clean_tags([*meta.tags, *profile_tags])),
            bio=bio,
            similar=tuple(similar[:TOP_SIMILAR]),
            peers=tuple(peers.get(artist.name, [])),
        )

    return dict(await asyncio.gather(*(one(k, a) for k, a in wanted.items())))


async def _from_profiles(
    artist: Artist, sources: Sources
) -> tuple[list[str], str | None, list[str]]:
    """Last.fm's tags and summary, and the closest similar Artists from ListenBrainz when the
    Artist has an ID, else Last.fm's own. A failed source leaves its part empty."""
    tags: list[str] = []
    bio: str | None = None
    similar: list[str] = []
    if sources.lastfm:
        try:
            profile = await lastfm.artist_profile(sources.lastfm, sources.redis, artist.name)
            tags, bio, similar = profile.tags, clean_bio(profile.bio), profile.similar
        except lastfm.LastfmError as exc:
            logger.warning("Last.fm profile failed: %s", exc)
    if artist.mbid:
        try:
            found = await listenbrainz.similar_artists(
                sources.listenbrainz, sources.redis, artist.mbid
            )
            similar = [a.name for a in found[:TOP_SIMILAR]] or similar
        except listenbrainz.ListenBrainzError as exc:
            logger.warning("ListenBrainz similar failed: %s", exc)
    return tags, bio, similar
