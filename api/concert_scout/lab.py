"""Anonymized Engineering Lab telemetry, eval suite metadata, and Search ranking inspection.

Privacy invariant: SearchMetrics never accepts or stores Search text, Artist names, Reading fields,
coordinates, IP addresses, usernames, or Spotify data.
"""

import datetime as dt
import functools
import logging
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import matching, telemetry
from concert_scout.models import Grade, Reading, Recommendation

logger = logging.getLogger(__name__)

METRICS_KEY = "lab:search_metrics"
MAX_SAMPLES = 200
RETENTION_DAYS = 7
METRICS_TTL = RETENTION_DAYS * 24 * 60 * 60

STEP_LABELS: dict[str, str] = {
    "interpret": "Interpret Search",
    "refine": "Interpret Refinement",
    "resolve_place": "Geocode place",
    "resolve_artists": "Artist similarity graph",
    "pool": "Concert pool",
    "cobilling": "Live co-billing lookup",
    "embed_query": "Embed Taste query",
    "semantic": "pgvector cosine lookup",
    "match": "Match & shortlist",
    "rank": "Jev grading & reasons",
    "elsewhere": "Elsewhere lookup",
}
STEP_ORDER: tuple[str, ...] = tuple(STEP_LABELS.keys())
ALLOWED_STEPS: frozenset[str] = frozenset(STEP_LABELS.keys())

EVAL_SEARCHES_PATH = Path(__file__).resolve().parent.parent / "evals" / "searches.yaml"


def hour_bucket(now: dt.datetime | None = None) -> str:
    """UTC hour bucket (`YYYY-MM-DDTHH:00Z`) so telemetry timestamps cannot fingerprint a visit."""
    current = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    return current.strftime("%Y-%m-%dT%H:00Z")


class SearchMetrics(BaseModel):
    """Strictly numeric telemetry for one Search. Extra fields are forbidden."""

    model_config = ConfigDict(extra="forbid")

    total_ms: float = Field(ge=0)
    steps_ms: dict[str, float] = Field(default_factory=dict)
    cost_usd: float = Field(ge=0)
    cost_complete: bool = True
    cache_hits: int = Field(default=0, ge=0)
    cache_misses: int = Field(default=0, ge=0)
    pool_total: int = Field(default=0, ge=0)
    shortlist_total: int = Field(default=0, ge=0)
    picks_total: int = Field(default=0, ge=0)
    recorded_at: str

    @field_validator("steps_ms")
    @classmethod
    def only_known_steps(cls, value: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for name, ms in value.items():
            if name not in ALLOWED_STEPS:
                raise ValueError(f"unknown step name: {name}")
            if ms < 0 or not math.isfinite(ms):
                raise ValueError(f"invalid step timing for {name}")
            cleaned[name] = round(float(ms), 1)
        return cleaned

    @field_validator("recorded_at")
    @classmethod
    def valid_hour_bucket(cls, value: str) -> str:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:00Z")
        return value


class StepLatency(BaseModel):
    step: str
    label: str
    samples: int
    p50_ms: float
    p95_ms: float


class EvalTier(BaseModel):
    id: Literal["tags_only", "cobilling", "hybrid_pgvector_jev"]
    name: str
    signals: list[str]
    ranker: str
    status: Literal["baseline", "shipped_offline_ready", "pending_live_eval"]
    status_label: str
    summary: str
    notes: str


class EvalSuiteSummary(BaseModel):
    source_file: str
    total_cases: int
    judged_cases: int
    unjudged_cases: int
    snapshot_cases: int
    must_labels: int
    good_labels: int
    bad_labels: int
    categories: dict[str, int]
    targets: dict[str, str]
    tiers: list[EvalTier]
    measurement_note: str


class ArchitectureGuarantee(BaseModel):
    id: str
    adr: str
    title: str
    summary: str
    enforced_by: str


class LabSummary(BaseModel):
    sample_count: int
    window_size: int = MAX_SAMPLES
    retention_days: int = RETENTION_DAYS
    p50_total_ms: float | None = None
    p95_total_ms: float | None = None
    avg_cost_usd: float | None = None
    cost_complete_samples: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float | None = None
    avg_pool_total: float | None = None
    avg_shortlist_total: float | None = None
    avg_picks_total: float | None = None
    latest_bucket: str | None = None
    steps: list[StepLatency] = []
    eval_benchmarks: EvalSuiteSummary
    guarantees: list[ArchitectureGuarantee]
    telemetry_available: bool = True


class InspectPick(BaseModel):
    """Under-the-hood ranking breakdown for one Recommendation on a Poster."""

    concert_id: str
    artist: str
    concert_name: str
    signal: matching.Signal | None = None
    via: str | None = None
    styles: list[str] = []
    match_score: float | None = None
    support: float | None = None
    grade: Grade | None = None
    jev_level: int | None = None
    lineup_match_count: int = 0
    source: Literal["ticketmaster", "jambase", "venue_calendar", "eventbrite"] = "ticketmaster"


class SearchInspect(BaseModel):
    """Additive SSE payload emitted right before `poster` for the optional Ranking Inspector."""

    reading: Reading
    pool_total: int
    shortlist_total: int
    steps_ms: dict[str, float] = {}
    picks: list[InspectPick] = []


def from_usage(usage: telemetry.SearchUsage, now: dt.datetime | None = None) -> SearchMetrics:
    """Convert numeric SearchUsage into a privacy-safe SearchMetrics payload."""
    steps_ms = {
        name: round(max(0.0, seconds * 1000.0), 1)
        for name, seconds in usage.steps.items()
        if name in ALLOWED_STEPS and math.isfinite(seconds)
    }
    return SearchMetrics(
        total_ms=usage.total_ms(),
        steps_ms=steps_ms,
        cost_usd=round(max(0.0, float(usage.cost)), 6),
        cost_complete=usage.complete,
        cache_hits=max(0, usage.cache_hits),
        cache_misses=max(0, usage.cache_misses),
        pool_total=max(0, usage.pool_total),
        shortlist_total=max(0, usage.shortlist_total),
        picks_total=max(0, usage.picks_total),
        recorded_at=hour_bucket(now),
    )


def build_inspect(
    reading: Reading,
    pool_total: int,
    shortlist: Sequence[matching.Candidate],
    recommendations: Sequence[Recommendation],
    levels: Mapping[str, int],
    steps_ms: Mapping[str, float],
) -> SearchInspect:
    """Build per-pick match signals, Jev levels, and step timings for the Poster inspector."""
    by_id = {candidate.concert.id: candidate for candidate in shortlist}
    picks: list[InspectPick] = []
    for rec in recommendations:
        candidate = by_id.get(rec.concert.id)
        match = candidate.match if candidate else None
        artist = (
            match.artist
            if match
            else (rec.concert.artists[0].name if rec.concert.artists else rec.concert.name)
        )
        jev_level = levels.get(rec.concert.id, rec.score)
        picks.append(
            InspectPick(
                concert_id=rec.concert.id,
                artist=artist,
                concert_name=rec.concert.name,
                signal=match.signal if match else None,
                via=match.via if match else None,
                styles=list(match.styles) if match else [],
                match_score=round(match.score, 4) if match else None,
                support=round(match.support, 4) if match else None,
                grade=rec.grade,
                jev_level=jev_level,
                lineup_match_count=len(rec.lineup_match),
                source=rec.concert.source,
            )
        )
    safe_steps = {
        name: round(max(0.0, float(ms)), 1)
        for name, ms in steps_ms.items()
        if name in ALLOWED_STEPS and math.isfinite(ms)
    }
    return SearchInspect(
        reading=reading,
        pool_total=pool_total,
        shortlist_total=len(shortlist),
        steps_ms=safe_steps,
        picks=picks,
    )


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile, rounded to 1 decimal place."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(float(ordered[0]), 1)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(float(ordered[low]), 1)
    weight = rank - low
    return round(float(ordered[low] * (1.0 - weight) + ordered[high] * weight), 1)


async def record_search(redis: Redis, metrics: SearchMetrics) -> None:
    """Append one numeric Search sample to the bounded Redis ring buffer. Never raises."""
    payload = metrics.model_dump_json()
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.lpush(METRICS_KEY, payload)
            pipe.ltrim(METRICS_KEY, 0, MAX_SAMPLES - 1)
            pipe.expire(METRICS_KEY, METRICS_TTL)
            await pipe.execute()
    except RedisError as exc:
        logger.warning("Lab telemetry not recorded: %s", type(exc).__name__)


def _classify_case(case_id: str, text: str) -> str:
    lower_id = case_id.casefold()
    lower_text = text.casefold()
    if lower_id.startswith("no-place-"):
        return "No place (seed-led)"
    if any(
        token in lower_id
        for token in (
            "garage",
            "techno",
            "dubstep",
            "drum-and-bass",
            "ambient",
            "house",
            "fred-again",
            "four-tet",
            "kaytranada",
        )
    ):
        return "Electronic & sparse tags"
    if " like " in lower_text:
        return "Seed Artist + city"
    return "Plain description & edge cases"


def _eval_tiers() -> list[EvalTier]:
    return [
        EvalTier(
            id="tags_only",
            name="Tags + ListenBrainz graph",
            signals=["seed", "one_hop", "two_hops", "tags", "genre"],
            ranker="Deterministic shortlist + Jev",
            status="baseline",
            status_label="Baseline",
            summary=(
                "MusicBrainz/ListenBrainz 1-hop & 2-hop similarity with IDF-weighted "
                "tags and Ticketmaster subgenres."
            ),
            notes=(
                "Strong for mainstream rock/country/pop seeds; struggles with "
                "underground electronic and sparse local tags."
            ),
        ),
        EvalTier(
            id="cobilling",
            name="+ Live Co-Billing Graph",
            signals=["seed", "one_hop", "two_hops", "co_billed", "tags", "genre"],
            ranker="Shortlist (CO_BILLED_WEIGHT=0.72) + Jev",
            status="shipped_offline_ready",
            status_label="Shipped · Offline ready",
            summary=(
                "Mines real club/theater bill co-appearances (2–40 Artists, "
                "mega-festivals excluded) during Catalog sync."
            ),
            notes=(
                "Captures live booking scenes that streaming popularity misses; "
                "unit-tested offline in test_cobilling.py."
            ),
        ),
        EvalTier(
            id="hybrid_pgvector_jev",
            name="Hybrid pgvector + Jev",
            signals=[
                "seed",
                "one_hop",
                "two_hops",
                "co_billed",
                "semantic",
                "tags",
                "genre",
            ],
            ranker="Pool-scoped pgvector cosine (512d) + Jev 1.14 + Haiku reasons",
            status="pending_live_eval",
            status_label="Pending live eval",
            summary=(
                "Source-grounded Sonic Cards & graph-propagated centroids scored "
                "in parallel with zero extra critical-path latency."
            ),
            notes=(
                "Code, migration, and fallback contracts are shipped; full before/after "
                "eval run awaits paid-tier Gemini embedding backfill."
            ),
        ),
    ]


@functools.lru_cache(maxsize=4)
def load_eval_benchmarks(path: Path = EVAL_SEARCHES_PATH) -> EvalSuiteSummary:
    """Compute real deterministic suite coverage from `api/evals/searches.yaml`."""
    entries: list[dict[str, Any]] = []
    if path.exists():
        loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            for item in cast(list[object], loaded):
                if isinstance(item, dict):
                    entries.append(cast(dict[str, Any], item))

    total_cases = len(entries)
    judged_cases = sum(1 for item in entries if bool(item.get("judged")))
    snapshot_cases = sum(1 for item in entries if bool(item.get("snapshot")))
    must_labels = sum(len(item.get("must") or []) for item in entries)
    good_labels = sum(len(item.get("good") or []) for item in entries)
    bad_labels = sum(len(item.get("bad") or []) for item in entries)

    categories: dict[str, int] = {
        "Electronic & sparse tags": 0,
        "Seed Artist + city": 0,
        "Plain description & edge cases": 0,
        "No place (seed-led)": 0,
    }
    for item in entries:
        bucket = _classify_case(str(item.get("id", "")), str(item.get("text", "")))
        categories[bucket] = categories.get(bucket, 0) + 1

    return EvalSuiteSummary(
        source_file="api/evals/searches.yaml",
        total_cases=total_cases,
        judged_cases=judged_cases,
        unjudged_cases=total_cases - judged_cases,
        snapshot_cases=snapshot_cases,
        must_labels=must_labels,
        good_labels=good_labels,
        bad_labels=bad_labels,
        categories=categories,
        targets={
            "bad_artists": "0 bad Artists on a Poster",
            "must_recall": ">= 90% of must Artists found",
            "good_or_must_share": ">= 60% judged good or must",
            "invented_facts": "0 invented facts or unknown IDs",
            "p95_poster_latency": "< 15s time to poster (p95)",
        },
        tiers=_eval_tiers(),
        measurement_note=(
            "Suite counts are computed live from api/evals/searches.yaml. Offline snapshot "
            "replays run with zero API keys; comparative before/after live scores for Hybrid "
            "pgvector + Jev are explicitly marked pending until the paid-tier embedding "
            "backfill completes."
        ),
    )


def architectural_guarantees() -> list[ArchitectureGuarantee]:
    return [
        ArchitectureGuarantee(
            id="source-facts",
            adr="ADR 0002",
            title="Facts never pass through the LLM",
            summary=(
                "Concert names, dates, venues, prices, URLs, and images come strictly from "
                "Ticketmaster and JamBase records. Jev grades shortlisted IDs; code drops unknown "
                "IDs and attaches verified source facts."
            ),
            enforced_by="concert_scout/assemble.py · tests/test_app.py",
        ),
        ArchitectureGuarantee(
            id="spotify-isolation",
            adr="ADR 0003",
            title="Official Spotify OAuth & strict LLM isolation",
            summary=(
                "Connected Spotify accounts use official OAuth only and power a separate "
                "exact-name shelf. Spotify data never enters LLM prompts, Search telemetry, "
                "or shared Posters."
            ),
            enforced_by="concert_scout/spotify.py · tests/test_spotify.py",
        ),
        ArchitectureGuarantee(
            id="privacy-spend-gates",
            adr="Spec 05 & 13",
            title="Zero-PII telemetry & bounded spend gates",
            summary=(
                "Engineering Lab stores only numeric timings, costs, cache counts, and funnel "
                "sizes in a 200-entry Redis ring buffer (7-day TTL). Searches are guarded by "
                "Turnstile, hashed IP hourly limits, and daily/monthly spend caps."
            ),
            enforced_by="concert_scout/lab.py · concert_scout/limits.py · tests/test_lab.py",
        ),
    ]


async def summarize(redis: Redis, *, eval_path: Path = EVAL_SEARCHES_PATH) -> LabSummary:
    """Summarize anonymized Search metrics from Redis alongside eval suite metadata."""
    telemetry_available = True
    raw_items: list[bytes | str] = []
    try:
        raw_items = await redis.lrange(METRICS_KEY, 0, MAX_SAMPLES - 1)  # type: ignore[misc]
    except RedisError as exc:
        logger.warning("Lab telemetry unavailable: %s", type(exc).__name__)
        telemetry_available = False

    samples: list[SearchMetrics] = []
    for raw in raw_items:
        try:
            samples.append(SearchMetrics.model_validate_json(raw))
        except ValidationError:
            continue

    totals = [s.total_ms for s in samples]
    complete_costs = [s.cost_usd for s in samples if s.cost_complete]
    cache_hits = sum(s.cache_hits for s in samples)
    cache_misses = sum(s.cache_misses for s in samples)
    cache_total = cache_hits + cache_misses

    steps: list[StepLatency] = []
    for step_name in STEP_ORDER:
        values = [s.steps_ms[step_name] for s in samples if step_name in s.steps_ms]
        if not values:
            continue
        p50 = percentile(values, 50)
        p95 = percentile(values, 95)
        if p50 is not None and p95 is not None:
            steps.append(
                StepLatency(
                    step=step_name,
                    label=STEP_LABELS[step_name],
                    samples=len(values),
                    p50_ms=p50,
                    p95_ms=p95,
                )
            )

    count = len(samples)
    return LabSummary(
        sample_count=count,
        window_size=MAX_SAMPLES,
        retention_days=RETENTION_DAYS,
        p50_total_ms=percentile(totals, 50),
        p95_total_ms=percentile(totals, 95),
        avg_cost_usd=round(sum(complete_costs) / len(complete_costs), 6)
        if complete_costs
        else None,
        cost_complete_samples=len(complete_costs),
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        cache_hit_rate=round(cache_hits / cache_total, 4) if cache_total > 0 else None,
        avg_pool_total=round(sum(s.pool_total for s in samples) / count, 1) if count else None,
        avg_shortlist_total=round(sum(s.shortlist_total for s in samples) / count, 1)
        if count
        else None,
        avg_picks_total=round(sum(s.picks_total for s in samples) / count, 1) if count else None,
        latest_bucket=max((s.recorded_at for s in samples), default=None),
        steps=steps,
        eval_benchmarks=load_eval_benchmarks(eval_path),
        guarantees=architectural_guarantees(),
        telemetry_available=telemetry_available,
    )
