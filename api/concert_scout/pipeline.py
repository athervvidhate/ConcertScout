import asyncio
import datetime as dt
import hashlib
import logging
from collections.abc import AsyncIterator, Coroutine, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import anyio
import httpx
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel, SecretStr
from pydantic_ai import Embedder
from pydantic_ai.models import Model
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import (
    assemble,
    cache,
    clock,
    cobilling,
    embeddings,
    interpreter,
    lab,
    limits,
    matching,
    pool,
    ranker,
    refinement,
    sculpt,
    share,
    similarity,
    telemetry,
)
from concert_scout.aliases import place_name
from concert_scout.interpreter import InterpreterError, interpret
from concert_scout.models import (
    ArtistProfile,
    Candidates,
    Concert,
    Elsewhere,
    Place,
    PoolTotal,
    Poster,
    Reading,
    Recommendation,
    RefinementApplied,
    SearchError,
    SeedArtist,
    Status,
    Unanswerable,
)
from concert_scout.names import collab_names
from concert_scout.ranker import RankerError
from concert_scout.refinement import RefinementError
from concert_scout.sources import (
    geocoder,
    jev,
    lastfm,
    listenbrainz,
    musicbrainz,
    spotify_catalog,
    ticketmaster,
)

logger = logging.getLogger(__name__)

ASK_FOR_A_SEARCH = "Tell us an Artist, a style or a place."
NEEDS_A_PLACE = "Add a place or an Artist, or press the location button."
# The home page shows the soonest of these, so a month of Concerts is plenty.
# With no place there is no pool, so this many similar Artists get looked up by name.
DIRECT_LOOKUPS = 15
# Imported Artists past this many join as names only, so a long list costs no extra API calls.
IMPORTED_SEEDS = 5


@dataclass(frozen=True)
class Services:
    ticketmaster: httpx.AsyncClient
    geocoder: httpx.AsyncClient
    musicbrainz: httpx.AsyncClient
    listenbrainz: httpx.AsyncClient
    lastfm: httpx.AsyncClient | None
    spotify_catalog: httpx.AsyncClient | None
    jev: httpx.AsyncClient
    redis: Redis
    model: Model
    turnstile: httpx.AsyncClient
    jambase: httpx.AsyncClient | None = None
    jambase_days: int = 90
    supabase: httpx.AsyncClient | None = None
    supabase_secret_key: SecretStr | None = None
    embedder: Embedder | None = None

    def embedding_sources(self) -> embeddings.Sources | None:
        """Where vectors are made and kept, or None while semantic retrieval is off."""
        if not (self.embedder and self.supabase and self.supabase_secret_key):
            return None
        return embeddings.Sources(
            self.embedder,
            self.supabase,
            self.supabase_secret_key,
            self.listenbrainz,
            self.lastfm,
            self.redis,
        )


async def find_artist_profile(name: str, services: Services) -> ArtistProfile:
    """Public Artist facts for the panel. This path never calls a model, and a dead source only
    leaves its part of the panel empty."""

    async def profile() -> ArtistProfile:
        if not services.lastfm:
            return ArtistProfile(name=name)
        try:
            return await lastfm.artist_profile(services.lastfm, services.redis, name)
        except lastfm.LastfmError as exc:
            logger.warning("Artist profile failed: %s", exc)
            return ArtistProfile(name=name)

    async def page() -> str | None:
        if not services.spotify_catalog:
            return None
        return await spotify_catalog.artist_page(services.spotify_catalog, services.redis, name)

    facts, spotify_url = await asyncio.gather(profile(), page())
    return facts.model_copy(update={"spotify_url": spotify_url})


async def find_artist_profiles(name: str, services: Services) -> list[ArtistProfile]:
    """A real duo keeps its own page. A tour billed as one name becomes each of its Artists."""
    whole = await find_artist_profile(name, services)
    parts = collab_names(name)
    if whole.spotify_url or whole.bio or not parts:
        return [whole]
    return list(await asyncio.gather(*(_billed_profile(part, services) for part in parts)))


async def _billed_profile(name: str, services: Services) -> ArtistProfile:
    """A billing can use a name the Artist is not filed under, so an alias gets a second look."""
    facts = await find_artist_profile(name, services)
    if facts.spotify_url:
        return facts
    try:
        filed = await musicbrainz.filed_name(services.musicbrainz, services.redis, name)
    except musicbrainz.MusicBrainzError as exc:
        logger.warning("MusicBrainz failed: %s", exc)
        return facts
    return await find_artist_profile(filed, services) if filed != name else facts


def _event(name: str, payload: BaseModel | None = None) -> ServerSentEvent:
    data = payload.model_dump(mode="json", exclude_none=True) if payload else {}
    return ServerSentEvent(event=name, data=data)


def _error(code: str, message: str) -> ServerSentEvent:
    return _event("error", SearchError(code=code, message=message))


async def _resolve_seed(name: str, services: Services) -> SeedArtist:
    try:
        return await musicbrainz.resolve(services.musicbrainz, services.redis, name)
    except musicbrainz.MusicBrainzError as exc:
        # The name alone can still join the pool, so a Search survives without MusicBrainz.
        logger.warning("MusicBrainz failed: %s", exc)
        return SeedArtist(name=name)


async def _find_taste(
    reading: Reading, names_only: Sequence[str], services: Services
) -> matching.Taste:
    seeds = await asyncio.gather(*(_resolve_seed(n, services) for n in reading.artists))
    neighbours = await similarity.find_neighbours(
        services.listenbrainz, services.lastfm, services.redis, seeds
    )
    extra = [SeedArtist(name=name) for name in names_only]
    return matching.Taste([*seeds, *extra], neighbours, reading.tags, reading.genres)


# A repeated Search within this window gets the same reading and grades, so the same Poster,
# and pays for no model call. It matches the Concert pool's own cache.
ANSWER_TTL = pool.CACHE_TTL


def _answer_key(kind: str, *parts: str) -> str:
    """Hashed, so a cache key never holds a visitor's Search text."""
    digest = hashlib.sha256("\x00".join(parts).encode()).hexdigest()
    return f"answer:{kind}:{digest}"


async def _interpreted(text: str, today: dt.date, services: Services) -> Reading:
    words = " ".join(text.split()).casefold()
    key = _answer_key("interpret", interpreter.INSTRUCTIONS, today.isoformat(), words)
    if cached := await cache.read(services.redis, key, Reading):
        telemetry.record_cache(True)
        return cached
    telemetry.record_cache(False)
    reading = await interpret(text, today, services.model)
    await cache.write(services.redis, key, reading, ANSWER_TTL)
    return reading


class Levels(BaseModel):
    levels: dict[str, int]


class Explained(BaseModel):
    reasons: list[str]


async def _graded(
    reading: Reading, rows: Mapping[str, ranker.Row], services: Services
) -> dict[str, int]:
    as_json = [f"{id_}={row.model_dump_json()}" for id_, row in rows.items()]
    taste = str(ranker.taste(reading))
    key = _answer_key("grade", jev.MODEL, jev.GUIDE, jev.QUESTION, *jev.LEVELS, taste, *as_json)
    if cached := await cache.read(services.redis, key, Levels):
        telemetry.record_cache(True)
        return cached.levels
    telemetry.record_cache(False)
    levels = await ranker.grade(services.jev, reading, rows)
    await cache.write(services.redis, key, Levels(levels=levels), ANSWER_TTL)
    return levels


async def _explained(
    reading: Reading, shown: Sequence[ranker.Row], services: Services
) -> list[str]:
    key = _answer_key("explain", ranker.REASONS, ranker.reasons_prompt(reading, shown))
    if cached := await cache.read(services.redis, key, Explained):
        telemetry.record_cache(True)
        return cached.reasons
    telemetry.record_cache(False)
    reasons = await ranker.explain(reading, shown, services.model)
    await cache.write(services.redis, key, Explained(reasons=reasons), ANSWER_TTL)
    return reasons


async def _recommend(
    reading: Reading,
    shortlist: Sequence[matching.Candidate],
    artist_tags: Mapping[str, Sequence[str]],
    services: Services,
) -> tuple[list[Recommendation], dict[str, int]]:
    rows = ranker.rows(shortlist, artist_tags)
    try:
        levels = await _graded(reading, rows, services)
    except RankerError as exc:
        logger.warning("Ranker failed: %s", exc)
        return assemble.from_matches(shortlist), {}
    if not levels:
        return assemble.from_matches(shortlist), {}
    poster = assemble.from_levels(levels, shortlist)
    candidates = {candidate.concert.id: candidate for candidate in shortlist}
    shown = [ranker.row(candidates[r.concert.id], artist_tags) for r in poster]
    # A Concert with no Lineup has no Artist to describe, so it keeps its neutral reason.
    named = [n for n, row in enumerate(shown) if row.artist]
    try:
        written = await _explained(reading, [shown[n] for n in named], services)
    except RankerError as exc:
        # The grades still stand. Each Concert keeps the neutral reason its match gave it.
        logger.warning("Reasons failed: %s", exc)
        return poster, levels
    reasons = dict(zip(named, written, strict=True))
    explained = [
        r.model_copy(update={"reason": reasons[n]}) if reasons.get(n) else r
        for n, r in enumerate(poster)
    ]
    return explained, levels


async def _find_elsewhere(
    reading: Reading, place: Place, services: Services, now: dt.datetime
) -> Elsewhere | None:
    """The Poster has already answered this Search, so a failure here only means no extra list."""
    words = [*reading.artists, *reading.tags, *reading.descriptors]
    if not words:
        return None
    try:
        with telemetry.step("elsewhere"):
            concerts = await pool.find_elsewhere(
                services.ticketmaster,
                services.redis,
                words[0],
                reading.start,
                reading.end,
                now,
            )
    except (ticketmaster.TicketmasterError, limits.DailyLimitReached) as exc:
        logger.warning("Elsewhere lookup failed: %s", type(exc).__name__)
        return None
    city = place.name.split(",")[0].casefold()
    others = [concert for concert in concerts if (concert.city or "").casefold() != city]
    return Elsewhere(keyword=words[0], concerts=others) if others else None


@dataclass(frozen=True)
class RefinementInput:
    """A typed Refinement against the Reading and Poster currently on screen."""

    reading: Reading
    text: str
    poster_artists: tuple[str, ...] = ()
    source_search_id: str | None = None


async def _read(asked: str | Reading, today: dt.date, services: Services) -> Reading:
    """A corrected Reading skips the interpreter. Its place still goes to the geocoder."""
    if isinstance(asked, Reading):
        return asked.model_copy(update={"place": place_name(asked.place) if asked.place else None})
    with telemetry.step("interpret"):
        return await _interpreted(asked, today, services)


async def _filter_only_from_session(
    session: sculpt.PoolSession,
    reading: Reading,
    exclude_artists: Sequence[str],
    services: Services,
    search_id: str | None,
) -> AsyncIterator[ServerSentEvent]:
    """Reuse the cached Concert pool and Jev grades with zero ranker or source calls."""
    yield _event("reading", reading)
    filtered = refinement.apply_reading_filters(
        session.pool, reading, exclude_artists=exclude_artists
    )
    yield _event("pool", PoolTotal(total=len(filtered)))

    if not filtered:
        shortlist: list[matching.Candidate] = []
    elif session.has_taste:
        taste = session.taste.to_taste()
        shortlist = matching.shortlist(
            matching.score_concerts(filtered, taste, session.artist_tags)
        )
    else:
        shortlist = matching.notable(filtered)

    yield _event(
        "candidates",
        Candidates(names=matching.candidate_names(shortlist), total=len(shortlist)),
    )

    shortlist_grades: dict[str, int] = {}
    if not shortlist:
        recommendations: list[Recommendation] = []
    elif not session.has_taste:
        recommendations = assemble.from_notable(shortlist)
    else:
        shortlist_grades = {
            c.concert.id: session.grades[c.concert.id]
            for c in shortlist
            if c.concert.id in session.grades
        }
        poster_recs = (
            assemble.from_levels(shortlist_grades, shortlist)
            if shortlist_grades
            else assemble.from_matches(shortlist)
        )
        recommendations = [
            rec.model_copy(update={"reason": session.reasons[rec.concert.id]})
            if rec.concert.id in session.reasons
            else rec
            for rec in poster_recs
        ]

    telemetry.record_funnel(
        pool_total=len(filtered),
        shortlist_total=len(shortlist),
        picks_total=len(recommendations),
    )

    sid = search_id or share.new_search_id()
    updated_session = session.model_copy(update={"reading": reading})
    try:
        await sculpt.save_session(services.redis, sid, updated_session)
    except RedisError as exc:
        logger.warning("Refined pool session not kept: %s", type(exc).__name__)

    yield _event(
        "inspect",
        lab.build_inspect(
            reading,
            len(filtered),
            shortlist,
            recommendations,
            shortlist_grades,
            telemetry.step_timings_ms(),
        ),
    )
    yield _event("poster", Poster(recommendations=recommendations))


async def _steps(
    asked: str | Reading | RefinementInput,
    imported: Sequence[str],
    near: Place | None,
    services: Services,
    now: dt.datetime,
    search_id: str | None = None,
) -> AsyncIterator[ServerSentEvent]:
    exclude_artists: Sequence[str] = ()
    if isinstance(asked, RefinementInput):
        yield _event("status", Status(step="refine", message="Refining your Search"))
        with telemetry.step("refine"):
            outcome = await refinement.refine(
                asked.reading, asked.poster_artists, asked.text, now.date(), services.model
            )
        session: sculpt.PoolSession | None = None
        if asked.source_search_id:
            try:
                session = await sculpt.load_session(services.redis, asked.source_search_id)
            except (sculpt.SessionExpired, RedisError):
                session = None

        if isinstance(outcome, refinement.UnanswerableRefinement):
            source_url, source_label = (
                refinement.source_link_for(session.pool, outcome.artist)
                if session
                else (None, None)
            )
            yield _event(
                "unanswerable",
                Unanswerable(
                    message=outcome.message,
                    artist=outcome.artist,
                    source_url=source_url,
                    source_label=source_label,
                ),
            )
            return

        yield _event("refinement", RefinementApplied(label=outcome.label))
        if session is not None and refinement.is_filter_only(
            session.reading,
            outcome.reading,
            boost_artists=outcome.boost_artists,
            today=now.date(),
        ):
            async for event in _filter_only_from_session(
                session, outcome.reading, outcome.exclude_artists, services, search_id
            ):
                yield event
            return

        reading = outcome.reading
        exclude_artists = outcome.exclude_artists
    else:
        if isinstance(asked, str):
            yield _event("status", Status(step="interpret", message="Reading your Search"))
        reading = await _read(asked, now.date(), services)
    names_only: Sequence[str] = ()
    # A Taste typed into this Search says what the person wants now, so it beats an import.
    if not (reading.artists or reading.tags or reading.descriptors):
        seeds, names_only = imported[:IMPORTED_SEEDS], imported[IMPORTED_SEEDS:]
        reading = reading.model_copy(update={"artists": list(seeds)})
    yield _event("reading", reading)

    if not (reading.place or near or reading.artists):
        if reading.descriptors or reading.tags:
            # Similar Artists start from a seed, so a style alone has nothing to look up.
            yield _error("needs_place", NEEDS_A_PLACE)
        else:
            yield _error("needs_taste_or_place", ASK_FOR_A_SEARCH)
        return

    async def find_place() -> Place | None:
        if not reading.place:
            return near
        with telemetry.step("resolve_place"):
            place = await geocoder.geocode(services.geocoder, services.redis, reading.place)
            radius = reading.radius_miles
            return place.model_copy(update={"radius_miles": radius}) if place else None

    async def find_taste() -> matching.Taste:
        with telemetry.step("resolve_artists"):
            return await _find_taste(reading, names_only, services)

    async def find_cobilling() -> dict[str, list[matching.CoBilledPeer]]:
        if not (services.supabase and services.supabase_secret_key and reading.artists):
            return {}
        with telemetry.step("cobilling"):
            return await cobilling.find_peers(
                services.supabase, services.supabase_secret_key, reading.artists
            )

    async def find_query_vector() -> embeddings.Vector | None:
        if not (sources := services.embedding_sources()):
            return None
        with telemetry.step("embed_query"):
            return await embeddings.query_vector(sources.embedder, services.redis, reading)

    async def find_semantic(
        query: embeddings.Vector | None, concerts: Sequence[Concert]
    ) -> dict[str, float]:
        if not (query and services.supabase and services.supabase_secret_key):
            return {}
        with telemetry.step("semantic"):
            return await embeddings.pool_scores(
                services.supabase,
                services.supabase_secret_key,
                query,
                [a.name for concert in concerts for a in concert.artists],
            )

    ingest_tasks: list[asyncio.Task[int]] = []

    def record_refreshed(concerts: list[Concert]) -> None:
        if services.supabase and services.supabase_secret_key:
            ingest_tasks.append(
                asyncio.create_task(
                    cobilling.ingest_concerts(
                        services.supabase, services.supabase_secret_key, concerts, now.date()
                    )
                )
            )

    async def find_pool(place: Place | None, lookups: Sequence[str]) -> list[Concert]:
        with telemetry.step("pool"):
            return await pool.find_concerts(
                services.ticketmaster,
                services.musicbrainz,
                services.redis,
                place,
                lookups,
                reading.start,
                reading.end,
                now,
                on_found=tag_fetch.add if wants_tags else None,
                on_refresh=record_refreshed
                if services.supabase and services.supabase_secret_key
                else None,
            )

    # Tags only score a Taste, so a place-only Search never asks for them.
    wants_tags = bool(reading.artists or names_only or reading.tags)
    tag_fetch = listenbrainz.TagFetch(services.listenbrainz, services.redis)
    # With a place, the pool needs nothing from the Taste, so the slowest steps overlap.
    tasks: list[asyncio.Task[Any]] = []

    def start[T](work: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        task = asyncio.create_task(work)
        tasks.append(task)
        return task

    try:
        try:
            place_lookup = start(find_place())
            taste_lookup = start(find_taste())
            cobilling_lookup = start(find_cobilling())
            query_lookup = start(find_query_vector())
            if reading.place:
                message = f"Finding {reading.region or reading.place}"
                yield _event("status", Status(step="resolve", message=message))
            if reading.artists:
                message = f"Finding Artists like {', '.join(reading.artists)}"
                yield _event("status", Status(step="resolve", message=message))

            place = await place_lookup
            if reading.place and place is None:
                where = reading.region or reading.place
                message = f"We could not find {where}. Check the spelling."
                yield _error("place_not_found", message)
                return

            if place:
                near_place = "you" if place is near else reading.region or place.name
                message = f"Looking for Concerts near {near_place}"
                yield _event("status", Status(step="pool", message=message))
                concert_lookup = start(find_pool(place, reading.artists))
                taste, cobilled = await asyncio.gather(taste_lookup, cobilling_lookup)
            else:
                taste, cobilled = await asyncio.gather(taste_lookup, cobilling_lookup)
                closest = similarity.closest(taste.neighbours, DIRECT_LOOKUPS)
                names = ", ".join(reading.artists)
                message = f"Looking for Concerts by {names} and similar Artists"
                yield _event("status", Status(step="pool", message=message))
                concert_lookup = start(find_pool(None, [*reading.artists, *closest]))
            if cobilled:
                taste = replace(taste, cobilling=cobilled)
            raw_concerts = await concert_lookup
            concerts = refinement.apply_reading_filters(
                raw_concerts, reading, exclude_artists=exclude_artists
            )
            yield _event("pool", PoolTotal(total=len(concerts)))
            query_embedding = await query_lookup
            if semantic := await find_semantic(query_embedding, concerts):
                taste = replace(taste, semantic=semantic)

            artist_tags: dict[str, list[str]] = {}
            if taste:
                yield _event(
                    "status", Status(step="match", message="Matching Concerts to your Taste")
                )
                with telemetry.step("match"):
                    # Most batches started while the pool was still arriving.
                    tag_fetch.add(concerts)
                    artist_tags = await tag_fetch.tags()
                    shortlist = matching.shortlist(
                        matching.score_concerts(concerts, taste, artist_tags)
                    )
            else:
                shortlist = matching.notable(concerts)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await tag_fetch.close()
        names = matching.candidate_names(shortlist)
        yield _event("candidates", Candidates(names=names, total=len(shortlist)))

        grades: dict[str, int] = {}
        if not taste:
            # Place-only Searches keep notable Ticketmaster listings, soonest first.
            recommendations = assemble.from_notable(shortlist)
        else:
            yield _event("status", Status(step="rank", message="Choosing the closest Concerts"))
            with telemetry.step("rank"):
                recommendations, grades = await _recommend(
                    reading, shortlist, artist_tags, services
                )

        if raw_concerts:
            sid = search_id or share.new_search_id()
            listeners, venue_tiers = await sculpt.load_cached_metadata(services.redis, raw_concerts)
            pool_session = sculpt.PoolSession(
                reading=reading,
                pool=raw_concerts[: sculpt.MAX_POOL_SIZE],
                artist_tags=artist_tags,
                query_embedding=query_embedding,
                taste=sculpt.StoredTaste.from_taste(taste),
                grades=grades,
                reasons={r.concert.id: r.reason for r in recommendations if r.reason},
                artist_listeners=listeners,
                venue_tiers=venue_tiers,
                has_taste=bool(taste),
            )
            try:
                await sculpt.save_session(services.redis, sid, pool_session)
            except RedisError as exc:
                logger.warning("Pool session not kept for sculpting: %s", type(exc).__name__)

        telemetry.record_funnel(
            pool_total=len(concerts),
            shortlist_total=len(shortlist),
            picks_total=len(recommendations),
        )
        yield _event(
            "inspect",
            lab.build_inspect(
                reading,
                len(concerts),
                shortlist,
                recommendations,
                grades,
                telemetry.step_timings_ms(),
            ),
        )
        yield _event("poster", Poster(recommendations=recommendations))
        if place and taste and not recommendations:
            elsewhere = await _find_elsewhere(reading, place, services, now)
            if elsewhere:
                yield _event("elsewhere", elsewhere)
        if ingest_tasks:
            await asyncio.gather(*ingest_tasks, return_exceptions=True)
    finally:
        for task in ingest_tasks:
            if not task.done():
                task.cancel()
        if ingest_tasks:
            await asyncio.gather(*ingest_tasks, return_exceptions=True)


async def run_search(
    asked: str | Reading | RefinementInput,
    imported: Sequence[str],
    near: Place | None,
    time_zone: str,
    services: Services,
    *,
    search_id: str | None = None,
) -> AsyncIterator[ServerSentEvent]:
    with telemetry.search() as usage:
        try:
            now = clock.now_in(time_zone)
            async for event in stream_search(
                asked, imported, near, services, now, search_id=search_id
            ):
                yield event
        finally:
            # A visitor who leaves early has still cost money, so a cancel must not skip this.
            if not usage.complete:
                logger.warning("Search cost is incomplete")
            with anyio.CancelScope(shield=True):
                await limits.record_spend(services.redis, usage.cost)
                await lab.record_search(services.redis, lab.from_usage(usage))


async def stream_search(
    asked: str | Reading | RefinementInput,
    imported: Sequence[str],
    near: Place | None,
    services: Services,
    now: dt.datetime,
    *,
    search_id: str | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """`asked` is the Search's words, a corrected Reading, or a typed Refinement."""
    try:
        async for event in _steps(asked, imported, near, services, now, search_id=search_id):
            yield event
    except InterpreterError as exc:
        logger.warning("Interpreter failed: %s", exc)
        message = "We could not read that Search. Try again in a minute."
        yield _error("interpreter_unavailable", message)
    except RefinementError as exc:
        logger.warning("Refinement failed: %s", exc)
        message = "We could not read that Refinement. Try again in a minute."
        yield _error("refinement_unavailable", message)
    except geocoder.GeocoderError as exc:
        logger.warning("Geocoder failed: %s", exc)
        message = "We could not look up that place. Try again in a minute."
        yield _error("geocoder_unavailable", message)
    except limits.DailyLimitReached as exc:
        logger.warning("Ticketmaster daily limit reached")
        message = "We have used today's Ticketmaster allowance. Try again tomorrow."
        yield _event(
            "error",
            SearchError(code="ticketmaster_limit", message=message, retry_after=exc.retry_after),
        )
    except ticketmaster.TicketmasterError as exc:
        logger.warning("Ticketmaster failed: %s", exc)
        message = "Ticketmaster is not responding. Try again in a minute."
        yield _error("ticketmaster_unavailable", message)
    yield _event("done")
