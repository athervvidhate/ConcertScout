"""Run real Searches one at a time, then all at once, and show where each one's time went.

The API runs in this process against the real providers in `.env`, so each Search costs about a
tenth of a cent in model calls and uses the shared Ticketmaster allowance. Each visitor gets its own
address, so the hourly Search limit stays out of the way. The run owns one Redis database and
empties it before each run that starts cold. Run it from `api/`:

    uv run python scripts/check_concurrency.py --searches 4
    uv run python scripts/check_concurrency.py --searches 4 --same --runs together

For each Search it prints the total time, when the pool and the Poster arrived, the time spent
waiting for a turn at the Ticketmaster and MusicBrainz gates, and the time spent with each source.
Model calls are not counted per source; they are the rest of the total.
"""

import argparse
import asyncio
import contextvars
import json
import logging
import os
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn
from redis.asyncio import Redis

from concert_scout import cache, limits
from concert_scout.app import create_app
from concert_scout.config import Settings

SEARCHES = [
    "anything in Los Angeles in the next six months",
    "anything in New York in the next six months",
    "indie rock in Chicago next month",
    "techno in Brooklyn this month",
    "jazz in New Orleans in December",
    "hip hop in Atlanta next month",
    "punk in Seattle in December",
    "country in Nashville next month",
]
# Cloudflare's always-pass test secret accepts any token.
TOKEN = "concurrency-check"
IP_HEADER = "x-concurrency-check-ip"
LABEL_HEADER = "x-concurrency-check-search"
# The event loop should wake within this of when it was asked to. More means something blocked it.
STALL = 0.05

type Scope = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
type Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


@dataclass
class Measure:
    gate_wait: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    gate_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    source_time: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    source_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    refusals: dict[str, int] = field(default_factory=lambda: defaultdict(int))


measures: dict[str, Measure] = defaultdict(Measure)
current = contextvars.ContextVar("search", default="")
stalls: list[float] = []


def timed_gate(name: str, gate: Callable[[Redis], Awaitable[None]]) -> Callable[..., Any]:
    async def wait_for_turn(redis: Redis) -> None:
        started = time.perf_counter()
        await gate(redis)
        measure = measures[current.get()]
        measure.gate_wait[name] += time.perf_counter() - started
        measure.gate_calls[name] += 1

    return wait_for_turn


class TimedTransport(httpx.AsyncBaseTransport):
    """Sits under each client's retries, so every attempt and its status is counted."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        started = time.perf_counter()
        response = await self._inner.handle_async_request(request)
        await response.aread()
        source = request.url.host.split(".")[-2]
        measure = measures[current.get()]
        measure.source_time[source] += time.perf_counter() - started
        measure.source_calls[source] += 1
        if response.status_code >= 400:
            measure.refusals[f"{source} {response.status_code}"] += 1
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


def labelled(app: ASGIApp) -> ASGIApp:
    """Each request's work is counted against the Search named in its header."""

    async def asgi(scope: Scope, receive: Receive, send: Send) -> None:
        for key, value in scope.get("headers", []):
            if key == LABEL_HEADER.encode():
                current.set(value.decode())
        await app(scope, receive, send)

    return asgi


async def watch_loop() -> None:
    while True:
        started = time.perf_counter()
        await asyncio.sleep(0.01)
        if (late := time.perf_counter() - started - 0.01) > STALL:
            stalls.append(late)


@dataclass
class Result:
    label: str
    text: str
    total: float = 0
    arrived: dict[str, float] = field(default_factory=dict[str, float])
    failure: str | None = None


async def search(client: httpx.AsyncClient, label: str, text: str, visitor: int) -> Result:
    result = Result(label, text)
    body = {"text": text, "token": TOKEN, "time_zone": "America/Chicago"}
    headers = {LABEL_HEADER: label, IP_HEADER: f"198.51.100.{visitor}"}
    started = time.perf_counter()
    event = ""
    async with client.stream("POST", "/search", json=body, headers=headers) as response:
        if response.status_code != 200:
            result.failure = f"HTTP {response.status_code}"
            return result
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
                result.arrived.setdefault(event, time.perf_counter() - started)
            elif line.startswith("data:") and event == "error":
                result.failure = json.loads(line.removeprefix("data:"))["code"]
    result.total = time.perf_counter() - started
    return result


def print_run(title: str, results: list[Result], wall: float) -> None:
    worst = max(stalls, default=0)
    print(f"\n{title}: {wall:.1f}s in all, {len(stalls)} event loop stalls (worst {worst:.2f}s)")
    for result in results:
        if result.failure and not result.arrived:
            print(f"  {result.label:<9} {result.failure}")
            continue
        m = measures[result.label]
        gates = "  ".join(
            f"{name} {m.gate_calls[name]} calls, waited {m.gate_wait[name]:.1f}s"
            for name in ("ticketmaster", "musicbrainz")
        )
        sources = "  ".join(
            f"{source} {m.source_time[source]:.1f}s/{m.source_calls[source]}"
            for source in sorted(m.source_time)
        )
        refused = "  ".join(f"{k} x{v}" for k, v in m.refusals.items())
        arrived = "  ".join(
            f"{e} {result.arrived[e]:.1f}s" for e in ("pool", "poster") if e in result.arrived
        )
        print(f"  {result.label:<9} {result.total:5.1f}s  {arrived}  {result.failure or ''}")
        print(f"            gates: {gates}")
        print(f"            sources: {sources}  {refused}")


async def run(
    client: httpx.AsyncClient,
    redis: Redis,
    name: str,
    texts: list[str],
    *,
    together: bool,
    cold: bool,
) -> list[Result]:
    stalls.clear()
    started = time.perf_counter()
    labels = [f"{name}{n}" for n in range(len(texts))]
    if together:
        if cold:
            await redis.flushdb()  # pyright: ignore[reportUnknownMemberType]
        jobs = (
            search(client, label, t, n)
            for n, (label, t) in enumerate(zip(labels, texts, strict=True))
        )
        results = list(await asyncio.gather(*jobs))
    else:
        results: list[Result] = []
        for n, (label, text) in enumerate(zip(labels, texts, strict=True)):
            if cold:
                await redis.flushdb()  # pyright: ignore[reportUnknownMemberType]
            results.append(await search(client, label, text, n))
    title = f"{'Together' if together else 'One at a time'}, {'cold' if cold else 'warm'} cache"
    print_run(title, results, time.perf_counter() - started)
    return results


def print_slowdown(alone: list[Result], together: list[Result]) -> None:
    print("\nTogether against alone, both cold:")
    for one, other in zip(alone, together, strict=True):
        if one.total and other.total:
            print(f"  {one.text:<50} {one.total:5.1f}s -> {other.total:5.1f}s")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--searches", type=int, default=4, choices=range(1, len(SEARCHES) + 1))
    parser.add_argument("--same", action="store_true", help="every visitor sends the first Search")
    parser.add_argument(
        "--runs",
        choices=["alone", "together", "warm"],
        action="append",
        help="which runs to make (default: all three). warm reuses the cache from the run before",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://127.0.0.1:6379/15",
        help="a Redis database this run may empty (default: database 15)",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    texts = [SEARCHES[0]] * args.searches if args.same else SEARCHES[: args.searches]
    runs = args.runs or ["alone", "together", "warm"]

    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    logging.getLogger("concert_scout.telemetry").setLevel(logging.ERROR)
    limits.ticketmaster_call = timed_gate("ticketmaster", limits.ticketmaster_call)
    limits.musicbrainz_call = timed_gate("musicbrainz", limits.musicbrainz_call)

    settings = Settings(  # pyright: ignore[reportCallIssue]
        redis_url=args.redis_url, client_ip_header=IP_HEADER, searches_per_hour=1000
    )
    app = labelled(create_app(settings, transport=TimedTransport()))
    server = uvicorn.Server(uvicorn.Config(app, port=args.port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    # Uvicorn reports startup only through this flag.
    while not server.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    watcher = asyncio.create_task(watch_loop())
    redis = cache.make_client(args.redis_url)
    base_url = f"http://127.0.0.1:{args.port}"
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
            alone = together = None
            if "alone" in runs:
                alone = await run(client, redis, "alone", texts, together=False, cold=True)
            if "together" in runs:
                together = await run(client, redis, "together", texts, together=True, cold=True)
            if "warm" in runs:
                await run(client, redis, "warm", texts, together=True, cold=False)
            if alone and together:
                print_slowdown(alone, together)
    finally:
        watcher.cancel()
        await redis.aclose()
        server.should_exit = True
        await serving


if __name__ == "__main__":
    asyncio.run(main())
