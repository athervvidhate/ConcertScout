"""Contracts for Engineering Lab telemetry, privacy invariants, and Search ranking inspection."""

import datetime as dt
import json
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis import FakeAsyncRedis
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from concert_scout import lab, matching, pool, ranker, similarity
from concert_scout.models import Artist, Concert, Reading, SeedArtist
from concert_scout.sources import musicbrainz
from tests.contracts import DAY, install_sources
from tests.test_app import TOKEN, api_for, parse_sse


@pytest.fixture(autouse=True)
def domain_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


async def test_telemetry_privacy_excludes_search_text_artists_coords_and_spotify() -> None:
    redis = FakeAsyncRedis()
    secret_query = "SecretArtistXYZ near 37.7749,-122.4194 spotify_token_abc123"
    secret_artist = "PrivateImportedBand999"
    async with api_for(redis) as api:
        response = await api.post(
            "/search",
            json={
                "text": secret_query,
                "taste": [secret_artist],
                "near": {"lat": 37.7749, "lon": -122.4194},
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )
    assert response.status_code == 200
    raw_items = cast(list[bytes], await redis.lrange(lab.METRICS_KEY, 0, -1))  # pyright: ignore[reportUnknownMemberType]
    assert len(raw_items) == 1
    serialized = raw_items[0].decode("utf-8")

    for forbidden in (
        secret_query,
        "SecretArtistXYZ",
        secret_artist,
        "Contract Artist",
        "San Francisco",
        "37.7749",
        "-122.4194",
        "spotify_token_abc123",
    ):
        assert forbidden not in serialized

    parsed = json.loads(serialized)
    assert set(parsed.keys()) == {
        "total_ms",
        "steps_ms",
        "cost_usd",
        "cost_complete",
        "cache_hits",
        "cache_misses",
        "pool_total",
        "shortlist_total",
        "picks_total",
        "recorded_at",
    }
    assert set(parsed["steps_ms"].keys()) <= lab.ALLOWED_STEPS
    assert parsed["pool_total"] == 3
    assert parsed["picks_total"] == 2
    assert parsed["cache_misses"] >= 1


def test_search_metrics_forbids_extra_fields_and_unknown_steps() -> None:
    with pytest.raises(ValidationError):
        lab.SearchMetrics.model_validate(
            {
                "total_ms": 120.0,
                "steps_ms": {},
                "cost_usd": 0.001,
                "recorded_at": "2026-11-22T12:00Z",
                "search_text": "must be rejected",
            }
        )
    with pytest.raises(ValidationError):
        lab.SearchMetrics(
            total_ms=120.0,
            steps_ms={"user_query_step": 10.0},
            cost_usd=0.001,
            recorded_at="2026-11-22T12:00Z",
        )


def test_percentile_math() -> None:
    assert lab.percentile([], 50) is None
    assert lab.percentile([42.0], 95) == 42.0
    assert lab.percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50) == 30.0
    assert lab.percentile([10.0, 20.0, 30.0, 40.0, 50.0], 95) == 48.0
    values = [float(i) for i in range(1, 101)]
    assert lab.percentile(values, 50) == 50.5
    assert lab.percentile(values, 95) == 95.0


async def test_ring_buffer_is_bounded_to_200_with_7_day_ttl() -> None:
    redis = FakeAsyncRedis()
    bucket = lab.hour_bucket(dt.datetime(2026, 11, 22, 14, 35, tzinfo=dt.UTC))
    assert bucket == "2026-11-22T14:00Z"

    for idx in range(lab.MAX_SAMPLES + 25):
        await lab.record_search(
            redis,
            lab.SearchMetrics(
                total_ms=float(idx + 1),
                steps_ms={"interpret": 50.0, "pool": 200.0},
                cost_usd=0.002,
                cost_complete=True,
                cache_hits=1 if idx % 2 == 0 else 0,
                cache_misses=1,
                pool_total=40,
                shortlist_total=15,
                picks_total=6,
                recorded_at=bucket,
            ),
        )

    length = await redis.llen(lab.METRICS_KEY)  # pyright: ignore[reportUnknownMemberType]
    ttl = await redis.ttl(lab.METRICS_KEY)
    assert length == lab.MAX_SAMPLES
    assert 0 < ttl <= lab.METRICS_TTL

    summary = await lab.summarize(redis)
    assert summary.sample_count == lab.MAX_SAMPLES
    # Latest 200 entries have total_ms 26..225
    assert summary.p50_total_ms == lab.percentile([float(i) for i in range(26, 226)], 50)
    assert summary.p95_total_ms == lab.percentile([float(i) for i in range(26, 226)], 95)
    assert summary.avg_cost_usd == 0.002
    assert summary.cache_hits == 100
    assert summary.cache_misses == 200
    assert summary.cache_hit_rate == pytest.approx(100 / 300, abs=1e-4)
    assert [step.step for step in summary.steps] == ["interpret", "pool"]


async def test_get_lab_returns_200_when_redis_is_empty_or_fails() -> None:
    async with api_for(FakeAsyncRedis()) as api:
        empty_resp = await api.get("/lab")
    assert empty_resp.status_code == 200
    assert empty_resp.headers["cache-control"] == "public, max-age=30"
    body = empty_resp.json()
    assert body["sample_count"] == 0
    assert body["p50_total_ms"] is None
    assert body["p95_total_ms"] is None
    assert body["avg_cost_usd"] is None
    assert body["cache_hit_rate"] is None
    assert body["telemetry_available"] is True
    assert body["eval_benchmarks"]["total_cases"] >= 20
    assert body["eval_benchmarks"]["judged_cases"] > 0
    assert [tier["id"] for tier in body["eval_benchmarks"]["tiers"]] == [
        "tags_only",
        "cobilling",
        "hybrid_pgvector_jev",
    ]
    assert "guarantees" not in body
    assert body["baseline"]["sample_count"] == 158
    assert body["baseline"]["p50_total_ms"] > 0

    broken = FakeAsyncRedis()
    broken.lrange = AsyncMock(side_effect=RedisConnectionError("down"))  # type: ignore[method-assign]
    async with api_for(broken) as api:
        degraded_resp = await api.get("/lab")
    assert degraded_resp.status_code == 200
    degraded = degraded_resp.json()
    assert degraded["sample_count"] == 0
    assert degraded["telemetry_available"] is False


async def test_record_search_swallows_redis_failure() -> None:
    broken = FakeAsyncRedis()
    broken.pipeline = MagicMock(side_effect=RedisConnectionError("down"))  # type: ignore[method-assign]
    await lab.record_search(
        broken,
        lab.SearchMetrics(
            total_ms=100.0,
            steps_ms={"interpret": 50.0},
            cost_usd=0.001,
            recorded_at="2026-11-22T12:00Z",
        ),
    )


async def test_repeated_search_increments_cache_hit_rate() -> None:
    redis = FakeAsyncRedis()
    body = {"text": "UKG in SF", "token": TOKEN, "time_zone": "UTC"}
    async with api_for(redis) as api:
        first = await api.post("/search", json=body)
        second = await api.post("/search", json=body)
        lab_resp = await api.get("/lab")
    assert first.status_code == 200 and second.status_code == 200
    summary = lab_resp.json()
    assert summary["sample_count"] == 2
    assert summary["cache_hits"] >= 1
    assert summary["cache_misses"] >= 1
    assert summary["cache_hit_rate"] is not None
    assert 0 < summary["cache_hit_rate"] < 1


async def test_sse_emits_inspect_event_with_signals_grades_and_no_spotify_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concerts = [
        Concert(
            id="c-seed",
            name="Khruangbin Live",
            artists=[Artist(name="Khruangbin", mbid="mb-k")],
            date=DAY,
            venue="Salt Shed",
            city="Chicago",
            url="https://tickets.example/seed",
            source="ticketmaster",
        ),
        Concert(
            id="c-hop",
            name="Hermanos Gutiérrez",
            artists=[Artist(name="Hermanos Gutiérrez", mbid="mb-hg")],
            date=DAY + dt.timedelta(days=1),
            venue="Thalia Hall",
            city="Chicago",
            url="https://tickets.example/hop",
            source="jambase",
        ),
        Concert(
            id="c-genre",
            name="Local Groove Night",
            artists=[
                Artist(
                    name="Local Groove",
                    mbid="mb-lg",
                    genre="Rock",
                    subgenre="Psychedelic",
                )
            ],
            date=DAY + dt.timedelta(days=2),
            venue="Empty Bottle",
            city="Chicago",
            url="https://tickets.example/genre",
            source="ticketmaster",
        ),
    ]
    monkeypatch.setattr(pool, "find_concerts", AsyncMock(return_value=concerts))
    monkeypatch.setattr(
        musicbrainz,
        "resolve",
        AsyncMock(return_value=SeedArtist(name="Khruangbin", mbid="mb-k")),
    )
    monkeypatch.setattr(
        similarity,
        "find_neighbours",
        AsyncMock(
            return_value=[
                matching.Neighbour(
                    name="Hermanos Gutiérrez",
                    mbid="mb-hg",
                    hops=1,
                    closeness=0.9,
                    seed="Khruangbin",
                )
            ]
        ),
    )
    monkeypatch.setattr(
        ranker,
        "grade",
        AsyncMock(return_value={"c-seed": 3, "c-hop": 3, "c-genre": 2}),
    )

    reading = Reading(
        artists=["Khruangbin"],
        tags=["psychedelic"],
        place="Chicago, Illinois",
    )
    async with api_for() as api:
        response = await api.post(
            "/search",
            json={
                "reading": reading.model_dump(mode="json", exclude_none=True),
                "token": TOKEN,
                "time_zone": "UTC",
            },
        )

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert "inspect" in names
    assert names.index("inspect") < names.index("poster")
    assert events[-1] == ("done", {})

    by_event: dict[str, Any] = dict(events)
    inspect = by_event["inspect"]
    assert inspect["pool_total"] == 3
    assert inspect["shortlist_total"] == 3
    assert "spotify" not in json.dumps(inspect).casefold()

    picks_by_id = {pick["concert_id"]: pick for pick in inspect["picks"]}
    assert picks_by_id["c-seed"]["signal"] == "seed"
    assert picks_by_id["c-seed"]["grade"] == "seed"
    assert picks_by_id["c-seed"]["jev_level"] == 3
    assert picks_by_id["c-seed"]["source"] == "ticketmaster"

    assert picks_by_id["c-hop"]["signal"] == "one_hop"
    assert picks_by_id["c-hop"]["via"] == "Khruangbin"
    assert picks_by_id["c-hop"]["grade"] == "strong"
    assert picks_by_id["c-hop"]["jev_level"] == 3
    assert picks_by_id["c-hop"]["source"] == "jambase"

    assert picks_by_id["c-genre"]["signal"] == "genre"
    assert picks_by_id["c-genre"]["grade"] == "fair"
    assert picks_by_id["c-genre"]["jev_level"] == 2
    assert picks_by_id["c-genre"]["match_score"] > 0
    assert picks_by_id["c-genre"]["support"] >= picks_by_id["c-genre"]["match_score"]


def test_build_inspect_preserves_cobilled_semantic_and_tags_signals() -> None:
    c1 = Concert(
        id="co-1",
        name="Club Bill",
        artists=[Artist(name="Opener Act")],
        url="https://tickets.example/co-1",
    )
    c2 = Concert(
        id="sem-1",
        name="Late Night Club",
        artists=[Artist(name="Semantic Act")],
        url="https://tickets.example/sem-1",
    )
    c3 = Concert(
        id="tag-1",
        name="Tagged Night",
        artists=[Artist(name="Tag Act")],
        url="https://tickets.example/tag-1",
    )
    shortlist = [
        matching.Candidate(
            concert=c1,
            match=matching.Match(
                artist="Opener Act", signal="co_billed", score=0.72, support=0.72, via="Four Tet"
            ),
        ),
        matching.Candidate(
            concert=c2,
            match=matching.Match(
                artist="Semantic Act", signal="semantic", score=0.45, support=0.60
            ),
        ),
        matching.Candidate(
            concert=c3,
            match=matching.Match(
                artist="Tag Act",
                signal="tags",
                score=0.38,
                support=0.38,
                styles=["uk garage", "2-step"],
            ),
        ),
    ]
    levels = {"co-1": 3, "sem-1": 2, "tag-1": 2}
    from concert_scout import assemble

    recs = assemble.from_levels(levels, shortlist)
    inspected = lab.build_inspect(
        Reading(artists=["Four Tet"], tags=["uk garage"], place="London"),
        pool_total=120,
        shortlist=shortlist,
        recommendations=recs,
        levels=levels,
        steps_ms={"pool": 320.4, "semantic": 24.8, "rank": 540.1},
    )
    assert inspected.pool_total == 120
    assert inspected.shortlist_total == 3
    assert [p.signal for p in inspected.picks] == ["co_billed", "semantic", "tags"]
    assert inspected.picks[0].via == "Four Tet"
    assert inspected.picks[1].support == 0.6
    assert inspected.picks[2].styles == ["uk garage", "2-step"]


async def test_postgres_telemetry_persists_all_time_count_and_caches_summary() -> None:
    import httpx
    from pydantic import SecretStr

    stored_rows: list[dict[str, Any]] = []
    get_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_calls
        if request.method == "POST" and request.url.path == lab.TELEMETRY_TABLE:
            batch = json.loads(request.content.decode("utf-8"))
            stored_rows.extend(batch)
            return httpx.Response(201)
        if request.method == "GET" and request.url.path == lab.TELEMETRY_TABLE:
            get_calls += 1
            total = len(stored_rows)
            selected = [
                {k: v for k, v in row.items() if k != "source"} for row in reversed(stored_rows)
            ]
            return httpx.Response(
                200,
                json=selected,
                headers={"content-range": f"0-{max(0, total - 1)}/{total}"},
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    redis = FakeAsyncRedis()
    secret = SecretStr("test-secret")
    async with httpx.AsyncClient(
        base_url="https://supabase.test", transport=httpx.MockTransport(handler)
    ) as sb:
        await lab.record_search(
            redis,
            lab.SearchMetrics(
                total_ms=820.0,
                steps_ms={"interpret": 110.0, "pool": 400.0},
                cost_usd=0.0025,
                cost_complete=True,
                cache_hits=1,
                cache_misses=2,
                pool_total=50,
                shortlist_total=20,
                picks_total=6,
                recorded_at="2026-11-22T15:00Z",
            ),
            supabase_client=sb,
            supabase_secret_key=secret,
        )
        first = await lab.summarize(redis, supabase_client=sb, supabase_secret_key=secret)
        second = await lab.summarize(redis, supabase_client=sb, supabase_secret_key=secret)

    assert first.storage_backend == "postgres"
    assert first.sample_count == 1
    assert first.all_time_count == 1
    assert first.p50_total_ms == 820.0
    assert second.sample_count == 1
    # Second call within 30s hits Redis summary cache instead of re-querying Postgres.
    assert get_calls == 1


def test_backfill_script_parses_span_logs_without_pii() -> None:
    from scripts.backfill_lab_telemetry import parse_log_lines

    trace_a = "a" * 32
    lines = [
        (
            f"2026-11-20T18:12:01Z search span=interpret trace={trace_a} "
            "duration_ms=145.20 attributes={'input_tokens': 100}"
        ),
        (
            f"2026-11-20T18:12:02Z search span=pool trace={trace_a} "
            "duration_ms=910.50 attributes={}"
        ),
        (
            f"2026-11-20T18:12:03Z search span=search trace={trace_a} "
            "duration_ms=1420.75 attributes={'cost_complete': True, 'cost_usd': 0.0031}"
        ),
        "unrelated log line with secret query text that must be ignored",
    ]
    rows = parse_log_lines(lines)
    assert len(rows) == 1
    row = rows[0]
    assert row.total_ms == 1420.8
    assert row.steps_ms == {"interpret": 145.2, "pool": 910.5}
    assert row.cost_usd == 0.0031
    assert row.cost_complete is True
    assert row.recorded_at == "2026-11-20T18:00Z"
