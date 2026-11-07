"""Search reports for the owner. Only what the visitor saw on the page goes out."""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints
from redis.asyncio import Redis
from redis.exceptions import RedisError

from concert_scout import limits
from concert_scout.config import Settings
from concert_scout.security import Refused, client_ip
from concert_scout.sources import resend

logger = logging.getLogger(__name__)

SUBJECT_LENGTH = 60

Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class Report(BaseModel):
    search: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    reading: Annotated[str, StringConstraints(max_length=2000)] = ""
    results: Annotated[list[Line], Field(max_length=30)] = []
    error: Line = ""


def email_body(report: Report) -> str:
    return "\n\n".join(
        [
            f"Search: {report.search}",
            f"Their note: {report.note or '(none)'}",
            f"How we read it: {report.reading or '(not read)'}",
            f"Error: {report.error or '(none)'}",
            "Results:\n" + ("\n".join(f"- {r}" for r in report.results) or "(none)"),
        ]
    )


def router(
    settings: Settings, redis: Redis, transport: httpx.AsyncBaseTransport | None = None
) -> APIRouter:
    routes = APIRouter()
    key, to = settings.resend_api_key, settings.feedback_email

    async def limit(request: Request) -> None:
        ip = client_ip(request, settings.client_ip_header)
        try:
            await limits.visitor_call(redis, "feedback", ip, limits.FEEDBACK_PER_HOUR)
            await limits.visitor_call(
                redis, "feedback", "everyone", limits.FEEDBACK_EVERYONE_PER_HOUR
            )
        except limits.VisitorLimitReached as exc:
            message = "We have plenty of reports for now. Try again later."
            raise Refused(429, "visitor_limit", message, exc.retry_after) from None
        except RedisError as exc:
            logger.warning("Feedback limit failed: %s", type(exc).__name__)
            raise Refused(503, "limits_unavailable", "Try again in a minute.") from None

    @routes.post("/feedback", status_code=204)
    async def feedback(report: Report, request: Request) -> Response:
        if request.headers.get("origin") not in settings.cors_origins:
            raise Refused(403, "origin_refused", "This site cannot send reports.")
        if key is None or not to:
            raise Refused(503, "feedback_off", "Reports are not switched on yet.")
        await limit(request)
        subject = " ".join(report.search.split())[:SUBJECT_LENGTH]
        try:
            async with resend.make_client(key.get_secret_value(), transport) as client:
                await resend.send(
                    client, to, f"Concert Scout report: {subject}", email_body(report)
                )
        except resend.ResendError as exc:
            logger.warning("Report failed: %s", exc)
            raise Refused(503, "feedback_failed", "That did not send. Try again soon.") from None
        return Response(status_code=204)

    return routes
