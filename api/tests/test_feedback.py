"""A report reaches the owner once, carries what the page showed, and cannot be abused."""

import json
from typing import Any

import httpx
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout.app import create_app
from concert_scout.limits import FEEDBACK_PER_HOUR
from tests.contracts import contract_model, settings_with

ORIGIN = "http://localhost:3000"
REPORT = {
    "search": "calvin harris in southern california\nin the next year",
    "note": "These are in Oakland",
    "reading": '{"region":"Southern California"}',
    "results": ["Calvin Harris, May 7, Oakland"],
}


def api_for(handler: Any, **settings: Any) -> httpx.AsyncClient:
    fields: dict[str, Any] = {
        "resend_api_key": SecretStr("private-resend"),
        "feedback_email": "owner@example.com",
    } | settings
    app = create_app(
        settings_with(**fields),
        httpx.MockTransport(handler),
        FakeAsyncRedis(),
        contract_model(),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000")


async def test_a_report_emails_the_search_and_its_results_to_the_owner() -> None:
    sent: list[httpx.Request] = []

    def resend(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"id": "email"})

    async with api_for(resend) as api:
        response = await api.post("/feedback", json=REPORT, headers={"Origin": ORIGIN})
    assert response.status_code == 204
    assert sent[0].url.path == "/emails"
    assert sent[0].headers["authorization"] == "Bearer private-resend"
    body = json.loads(sent[0].content)
    assert body["to"] == ["owner@example.com"]
    assert "\n" not in body["subject"]
    assert "southern california" in body["subject"]
    assert "These are in Oakland" in body["text"]
    assert "Calvin Harris, May 7, Oakland" in body["text"]


async def test_reports_refuse_other_sites_and_stay_off_without_configuration() -> None:
    def forbidden(_: httpx.Request) -> httpx.Response:
        raise AssertionError("nothing may be sent")

    async with api_for(forbidden) as api:
        refused = await api.post(
            "/feedback", json=REPORT, headers={"Origin": "https://evil.example"}
        )
    assert refused.status_code == 403
    async with api_for(forbidden, resend_api_key=None) as api:
        off = await api.post("/feedback", json=REPORT, headers={"Origin": ORIGIN})
    assert off.status_code == 503
    assert off.json()["code"] == "feedback_off"


async def test_a_visitor_cannot_flood_the_inbox() -> None:
    sent: list[httpx.Request] = []

    def resend(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"id": "email"})

    async with api_for(resend) as api:
        for _ in range(FEEDBACK_PER_HOUR):
            ok = await api.post("/feedback", json=REPORT, headers={"Origin": ORIGIN})
            assert ok.status_code == 204
        limited = await api.post("/feedback", json=REPORT, headers={"Origin": ORIGIN})
    assert limited.status_code == 429
    assert len(sent) == FEEDBACK_PER_HOUR


async def test_a_failed_email_says_so_without_leaking_the_key() -> None:
    def down(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with api_for(down) as api:
        response = await api.post("/feedback", json=REPORT, headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert response.json()["code"] == "feedback_failed"
    assert "private-resend" not in response.text
