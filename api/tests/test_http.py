import logging

import httpx
import pytest

from concert_scout.sources import http


async def test_a_request_logs_no_api_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    async with http.make_client("https://example.test", {"key": "secret-key"}, transport) as c:
        await c.get("/videos")
    assert "secret-key" not in caplog.text
