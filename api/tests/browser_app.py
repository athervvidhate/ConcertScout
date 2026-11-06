"""E2E-only composition: production API/pipeline, real isolated Redis, domain adapter fixtures.

No production flag enables this. Never import this module from the application package.
"""

import socket
import subprocess
import tempfile
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

from concert_scout.app import create_app
from tests.contracts import contract_model, forbidden_http, install_sources, settings_with

patch = pytest.MonkeyPatch()
install_sources(patch)

with socket.socket() as address:
    address.bind(("127.0.0.1", 0))
    redis_port = address.getsockname()[1]

storage = tempfile.TemporaryDirectory(prefix="concert-scout-e2e-")
redis = subprocess.Popen(
    [
        "redis-server",
        "--bind",
        "127.0.0.1",
        "--port",
        str(redis_port),
        "--save",
        "",
        "--appendonly",
        "no",
        "--dir",
        storage.name,
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
for attempt in range(100):
    try:
        with socket.create_connection(("127.0.0.1", redis_port), timeout=0.1):
            break
    except OSError:
        if redis.poll() is not None or attempt == 99:
            redis.terminate()
            raise RuntimeError("Isolated E2E Redis failed to start") from None
        time.sleep(0.05)

app = create_app(
    settings_with(redis_url=f"redis://127.0.0.1:{redis_port}/0", searches_per_hour=1000),
    httpx.MockTransport(forbidden_http),
    model=contract_model(),
)
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    try:
        async with original_lifespan(application):
            yield
    finally:
        redis.terminate()
        redis.wait(timeout=5)
        storage.cleanup()
        patch.undo()


app.router.lifespan_context = lifespan
