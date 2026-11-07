"""Runs one Search through the real pipeline, against live sources or a Snapshot."""

import datetime as dt
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr
from pydantic_ai.models import Model

from concert_scout import interpreter, limits, telemetry
from concert_scout.app import make_services
from concert_scout.config import Settings
from concert_scout.models import Poster, Recommendation
from concert_scout.pipeline import stream_search
from evals.snapshots import (
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


async def run(
    text: str,
    today: dt.date,
    settings: Settings,
    transport: httpx.AsyncBaseTransport,
    model: Model,
) -> SearchRun:
    """A fresh fake Redis means a cold cache, and so the same requests on every run."""
    services = make_services(settings, transport, FakeAsyncRedis(), model)
    result = SearchRun()
    started = time.perf_counter()
    with telemetry.search() as usage:
        async for event in stream_search(text, [], services, today):
            data: dict[str, Any] = event.data or {}
            if event.event == "candidates":
                result.names = data["names"]
            elif event.event == "error":
                result.error = data["code"]
            elif event.event == "poster":
                result.seconds_to_poster = time.perf_counter() - started
                result.recommendations = Poster.model_validate(data).recommendations
    result.cost = usage.cost
    result.cost_complete = usage.complete
    return result


def _real_model(settings: Settings) -> Model:
    return interpreter.make_model(settings.anthropic_api_key.get_secret_value())


async def capture(case_id: str, text: str, settings: Settings) -> tuple[Snapshot, SearchRun]:
    """A real, paid Search whose every outbound call lands in a new Snapshot."""
    today = dt.date.today()
    transport = RecordingTransport()
    model = RecordingModel(_real_model(settings))
    result = await run(text, today, settings, transport, model)
    snapshot = Snapshot(
        id=f"{case_id}-{today.isoformat()}",
        text=text,
        today=today,
        seconds_to_poster=result.seconds_to_poster,
        records=transport.records,
        answers=model.answers,
    )
    return snapshot, result


async def replay(
    snapshot: Snapshot, settings: Settings | None, live_model: bool = False
) -> tuple[SearchRun, list[str]]:
    """Replays a Snapshot. Only `live_model` needs real settings, and only it spends money."""
    # The pacing protects live services, and a replay calls none.
    limits.SLOT_SECONDS = 0.001
    limits.MUSICBRAINZ_GAP = dt.timedelta(milliseconds=1)
    settings = settings or Settings(
        tm_key=SecretStr("replay"),
        anthropic_api_key=SecretStr("replay"),
        geoapify_key=SecretStr("replay"),
    )
    transport = ReplayTransport(snapshot)
    model = ReplayModel(_real_model(settings), snapshot, live_model)
    result = await run(snapshot.text, snapshot.today, settings, transport, model)
    return result, [*transport.misses, *model.misses]
