"""Runs one Search through the real pipeline, against live sources or a Snapshot."""

import datetime as dt
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr
from pydantic_ai.models import Model
from redis.asyncio import Redis

from concert_scout import cache, interpreter, limits, telemetry
from concert_scout.app import make_services
from concert_scout.config import Settings
from concert_scout.models import Poster, Recommendation
from concert_scout.pipeline import stream_search
from evals.snapshots import (
    Live,
    RecordingModel,
    RecordingTransport,
    ReplayModel,
    ReplayTransport,
    Snapshot,
)

# Spans log a warning each, which would bury the report.
logging.getLogger(telemetry.__name__).setLevel(logging.ERROR)


@dataclass
class SearchRun:
    recommendations: list[Recommendation] = field(default_factory=list[Recommendation])
    names: list[str] = field(default_factory=list[str])
    error: str | None = None
    seconds_to_poster: float | None = None
    cost: Decimal = Decimal(0)
    cost_complete: bool = True
    steps: dict[str, float] = field(default_factory=dict[str, float])


async def run(
    text: str,
    today: dt.date,
    settings: Settings,
    transport: httpx.AsyncBaseTransport,
    model: Model,
    spend_redis: Redis | None = None,
) -> SearchRun:
    """A fresh fake Redis means a cold cache, and so the same requests on every run."""
    services = make_services(settings, transport, FakeAsyncRedis(), model)
    result = SearchRun()
    # A Snapshot keeps only its date. Noon UTC is that same date in almost every zone.
    noon = dt.datetime.combine(today, dt.time(12), dt.UTC)
    started = time.perf_counter()
    async with AsyncExitStack() as resources:
        for client in (
            services.ticketmaster,
            services.geocoder,
            services.musicbrainz,
            services.listenbrainz,
            services.jev,
            services.lastfm,
            services.spotify_catalog,
            services.turnstile,
        ):
            if client is not None:
                resources.push_async_callback(client.aclose)
        resources.push_async_callback(services.redis.aclose)
        with telemetry.search() as usage:
            try:
                async for event in stream_search(text, [], None, services, noon):
                    data: dict[str, Any] = event.data or {}
                    if event.event == "candidates":
                        result.names = data["names"]
                    elif event.event == "error":
                        result.error = data["code"]
                    elif event.event == "poster":
                        result.seconds_to_poster = time.perf_counter() - started
                        result.recommendations = Poster.model_validate(data).recommendations
            finally:
                result.cost = usage.cost
                result.cost_complete = usage.complete
                result.steps = usage.steps
                if spend_redis is not None:
                    await limits.record_spend(spend_redis, usage.cost)
    return result


def real_model(settings: Settings) -> Model:
    return interpreter.make_model(settings.anthropic_api_key.get_secret_value())


async def capture(case_id: str, text: str, settings: Settings) -> tuple[Snapshot, SearchRun]:
    """A real, paid Search whose every outbound call lands in a new Snapshot."""
    today = dt.date.today()
    secrets = [
        settings.tm_key,
        settings.anthropic_api_key,
        settings.geoapify_key,
        settings.typesafe_api_key,
        settings.lastfm_key,
    ]
    transport = RecordingTransport(secrets=[s.get_secret_value() for s in secrets if s])
    model = RecordingModel(real_model(settings))
    async with cache.make_client(settings.redis_url) as ledger:
        await limits.check_spend(ledger, limits.EVAL_DAILY_SPEND)
        result = await run(text, today, settings, transport, model, ledger)
    snapshot = Snapshot(
        id=f"{case_id}-{today.isoformat()}-{uuid4().hex[:8]}",
        text=text,
        today=today,
        seconds_to_poster=result.seconds_to_poster,
        lastfm_enabled=bool(settings.lastfm_key),
        records=transport.records,
        answers={key: transport.redact(value) for key, value in model.answers.items()},
    )
    return snapshot, result


async def replay(
    snapshot: Snapshot, settings: Settings | None, live: Live = "none"
) -> tuple[SearchRun, list[str]]:
    """Replays a Snapshot. Only a `live` model needs real settings, and only it spends money."""
    # The pacing protects live services, and a replay calls none.
    settings = settings or Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        tm_key=SecretStr("replay"),
        anthropic_api_key=SecretStr("replay"),
        geoapify_key=SecretStr("replay"),
        typesafe_api_key=SecretStr("replay"),
    )
    settings = settings.model_copy(
        update={"lastfm_key": SecretStr("replay") if snapshot.lastfm_enabled else None}
    )
    transport = ReplayTransport(snapshot, live_grades=live != "none")
    model = ReplayModel(real_model(settings), snapshot, live)
    with (
        patch.object(limits, "SLOT_SECONDS", 0.001),
        patch.object(limits, "MUSICBRAINZ_GAP", dt.timedelta(milliseconds=1)),
    ):
        result = await run(snapshot.text, snapshot.today, settings, transport, model)
    return result, [*transport.misses, *model.misses]
