"""Bounded source coverage capture and offline replay; never part of a visitor's Search."""

import argparse
import asyncio
import datetime as dt
import html
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Self, cast
from urllib.parse import quote, quote_plus, urlsplit

import httpx
from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis

from concert_scout import limits
from concert_scout.models import Concert
from concert_scout.names import normalize
from concert_scout.sources import http, ticketmaster

Provider = Literal["ticketmaster", "ticketfairy"]
DEFAULT_REFERENCES = Path(__file__).with_name("coverage-references.json")
CAPTURES = Path(__file__).parent / "snapshots" / "coverage"


class Reference(BaseModel):
    """A hand-reviewed venue date, not a claim about distinct sets that night."""

    id: str
    name: str
    names: list[str]
    date: dt.date
    venue: str
    venue_aliases: list[str]
    city: str
    city_aliases: list[str]
    source_url: str
    evidence_page: str
    keywords: list[str]


class References(BaseModel):
    start: dt.date
    end: dt.date
    country: str
    state: str
    references: list[Reference]
    evidence: dict[str, str] = {}
    excluded: list[dict[str, str]] = []

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.start > self.end:
            raise ValueError("start must precede end")
        if len({r.id for r in self.references}) != len(self.references):
            raise ValueError("reference IDs must be unique")
        return self


class Candidate(BaseModel):
    concert: Concert
    status: str = "unknown"


class Lookup(BaseModel):
    provider: Provider
    keyword: str
    complete: bool = False
    requests: int = 0
    seconds: float = 0
    total: int | None = None
    error: str | None = None
    candidates: list[Candidate] = []
    # Response bodies are third-party records and stay in the ignored capture.
    payloads: list[dict[str, Any]] = []


class Capture(BaseModel):
    captured_at: dt.datetime
    references: References
    lookups: list[Lookup]
    seconds: float


class Finding(BaseModel):
    reference_id: str
    provider: Provider
    state: Literal["present", "missing", "unresolved", "out_of_scope"]
    ids: list[str] = []
    other_dates: list[dt.date] = []
    multiple_listings: bool = False
    external_sellers: list[str] = []
    reason: str


def _normal(value: str) -> str:
    return normalize(html.unescape(value).replace("\u200b", ""))


def _same_name(reference: Reference, concert: Concert) -> bool:
    names = {_normal(v) for v in reference.names}
    candidate_names = {_normal(concert.name), *(_normal(a.name) for a in concert.artists)}
    return bool(names & candidate_names)


def _same_identity(reference: Reference, concert: Concert) -> bool:
    venues = {_normal(v) for v in reference.venue_aliases}
    cities = {_normal(v) for v in reference.city_aliases}
    return (
        _normal(concert.venue or "") in venues
        and _normal(concert.city or "") in cities
        and _same_name(reference, concert)
    )


def compare(capture: Capture, provider: Provider) -> list[Finding]:
    """Exact aliases only. Failed/incomplete required lookups cannot prove absence."""
    lookups = {lookup.keyword: lookup for lookup in capture.lookups if lookup.provider == provider}
    candidates = {
        c.concert.id: c for lookup in lookups.values() for c in lookup.candidates
    }.values()
    findings: list[Finding] = []
    for reference in capture.references.references:
        if not capture.references.start <= reference.date <= capture.references.end:
            findings.append(
                Finding(
                    reference_id=reference.id,
                    provider=provider,
                    state="out_of_scope",
                    reason="outside date window",
                )
            )
            continue
        related = [c for c in candidates if _same_identity(reference, c.concert)]
        exact = [c for c in related if c.concert.date == reference.date]
        active = [c for c in exact if c.status not in {"cancelled", "postponed"}]
        other_dates = sorted({c.concert.date for c in related if c.concert.date} - {reference.date})
        if active:
            hosts = {urlsplit(c.concert.url).hostname or "" for c in active}
            findings.append(
                Finding(
                    reference_id=reference.id,
                    provider=provider,
                    state="present",
                    ids=sorted(c.concert.id for c in active),
                    multiple_listings=len(active) > 1,
                    external_sellers=sorted(h for h in hosts if h != "www.ticketmaster.com"),
                    other_dates=other_dates,
                    reason="same published name/Artist, venue, city and date",
                )
            )
            continue
        keys = (
            ["California"] if provider == "ticketfairy" else [reference.venue, *reference.keywords]
        )
        complete = all(key in lookups and lookups[key].complete for key in keys)
        # Same venue/date but different title may be an unrecognized alias; review it.
        uncertain = any(
            c.concert.date == reference.date
            and (
                (
                    _normal(c.concert.venue or "") in {_normal(v) for v in reference.venue_aliases}
                    and _normal(c.concert.city or "")
                    in {_normal(v) for v in reference.city_aliases}
                )
                or (
                    _same_name(reference, c.concert)
                    and (c.concert.venue is None or c.concert.city is None)
                )
            )
            for c in candidates
        )
        state: Literal["missing", "unresolved"] = (
            "missing" if complete and not uncertain else "unresolved"
        )
        reason = "not found by completed bounded lookups"
        if exact:
            state, reason = "unresolved", "source reports cancelled/postponed"
        elif not complete:
            reason = "required lookup absent, failed or truncated"
        elif uncertain:
            reason = "name/location fields cannot resolve identity on this date"
        elif other_dates:
            state, reason = (
                "unresolved",
                "same identity on another date; review possible reschedule",
            )
        elif any(c.concert.date is None for c in related):
            state, reason = "unresolved", "matching identity has no published date"
        findings.append(
            Finding(
                reference_id=reference.id,
                provider=provider,
                state=state,
                other_dates=other_dates,
                reason=reason,
            )
        )
    return findings


def parse_candidates(provider: Provider, body: dict[str, Any]) -> tuple[list[Candidate], int]:
    """Normalize captured vendor records without asking a model to extract any fact."""
    rows: list[Candidate]
    if provider == "ticketmaster":
        total = int(body["page"]["totalElements"])
        rows = [
            Candidate(
                concert=ticketmaster.parse_concert(row),
                status=row["dates"].get("status", {}).get("code", "unknown"),
            )
            for row in body.get("_embedded", {}).get("events", [])
        ]
    else:
        if body.get("success") is not True:
            raise ValueError("unsuccessful response")
        total = int(body["data"]["pagination"]["totalCount"])
        rows = []
        for row in body["data"]["events"]:
            venue: dict[str, Any] = row.get("venue") or {}
            start = dt.datetime.fromisoformat(row["startDate"]) if row.get("startDate") else None
            rows.append(
                Candidate(
                    concert=Concert(
                        id=row["url"],
                        name=row["displayName"],
                        url=row["url"],
                        artists=[],
                        date=start.date() if start and not row.get("hideDate") else None,
                        venue=venue.get("name"),
                        city=venue.get("city"),
                        region=venue.get("state"),
                    )
                )
            )
    for candidate in rows:
        candidate.concert.id = f"{provider}:{candidate.concert.id}"
    return rows, total


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    tm_key: SecretStr
    redis_url: str = "redis://127.0.0.1:6379/0"


async def capture_sources(
    references: References,
    settings: AuditSettings,
    max_requests: int,
    providers: list[Provider],
    transport: httpx.AsyncBaseTransport | None = None,
) -> Capture:
    started = time.perf_counter()
    now = dt.datetime.now(dt.UTC)
    lookups: list[Lookup] = []
    used = 0
    redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        settings.redis_url, socket_connect_timeout=1, socket_timeout=1
    )
    secrets = [settings.tm_key.get_secret_value()]
    async with httpx.AsyncClient(
        headers={"User-Agent": http.USER_AGENT},
        timeout=15,
        transport=transport,
    ) as client:
        try:
            for provider in providers:
                keywords = (
                    ["California"]
                    if provider == "ticketfairy"
                    else sorted(
                        {
                            keyword
                            for r in references.references
                            for keyword in [r.venue, *r.keywords]
                        }
                    )
                )
                for keyword in keywords:
                    lookup = Lookup(provider=provider, keyword=keyword)
                    lookups.append(lookup)
                    if provider == "ticketfairy" and (
                        references.country != "US" or references.state != "CA"
                    ):
                        lookup.error = "Ticket Fairy probe supports California only"
                        continue
                    began = time.perf_counter()
                    page = 0
                    while True:
                        if used >= max_requests:
                            lookup.error = "request budget exhausted"
                            break
                        if provider == "ticketmaster":
                            try:
                                await limits.ticketmaster_call(redis)
                            except limits.DailyLimitReached:
                                lookup.error = "Ticketmaster daily quota exhausted"
                                used = max_requests
                                break
                            url = f"{ticketmaster.BASE_URL}/events.json"
                            params: dict[str, str | int] = {
                                "apikey": secrets[0],
                                "keyword": keyword,
                                "size": 200,
                                "page": page,
                                "countryCode": references.country,
                                "stateCode": references.state,
                                "sort": "date,asc",
                                "localStartDateTime": (
                                    f"{references.start}T00:00:00,{references.end}T23:59:59"
                                ),
                            }
                        else:
                            url = "https://www.ticketfairy.com/api/v1/events/listing"
                            params = {
                                "country": references.country.lower(),
                                "state": keyword,
                                "from": str(references.start),
                                "to": str(references.end),
                                "timezone": "America/Los_Angeles",
                                "size": 200,
                                "page": page + 1,
                                "section_type": "upcoming",
                                "sort": "start_date",
                                "order": "asc",
                            }
                        used += 1
                        lookup.requests += 1
                        try:
                            response = await client.get(url, params=params)
                            response.raise_for_status()
                            # Never persist a response echoing a credential.
                            body = response.text
                            for secret in secrets:
                                for encoded in {secret, quote(secret, safe=""), quote_plus(secret)}:
                                    body = body.replace(encoded, "[redacted]")
                            decoded: Any = json.loads(body)
                            if not isinstance(decoded, dict):
                                raise ValueError("expected JSON object")
                            payload = cast(dict[str, Any], decoded)
                            lookup.payloads.append(payload)
                            rows, total = parse_candidates(provider, payload)
                            lookup.total = total
                            lookup.candidates.extend(rows)
                            page += 1
                            if provider == "ticketmaster":
                                done = page * 200 >= total
                            else:
                                done = page >= payload["data"]["pagination"]["totalPages"]
                            if done:
                                lookup.complete = len(lookup.candidates) == total
                                if not lookup.complete:
                                    lookup.error = "response count differs from published total"
                                break
                            if not rows or page * 200 >= 1000:
                                lookup.error = "paging truncated; absence is not established"
                                break
                        except httpx.HTTPStatusError as exc:
                            lookup.error = f"HTTP {exc.response.status_code}"
                            break
                        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                            lookup.error = type(exc).__name__
                            break
                    lookup.seconds = round(time.perf_counter() - began, 3)
        finally:
            await redis.aclose()
    return Capture(
        captured_at=now,
        references=references,
        lookups=lookups,
        seconds=round(time.perf_counter() - started, 3),
    )


def report(capture: Capture) -> dict[str, Any]:
    providers: list[Provider] = list(dict.fromkeys(lookup.provider for lookup in capture.lookups))
    findings = [f for p in providers for f in compare(capture, p)]
    return {
        "captured_at": capture.captured_at.isoformat(),
        "unit": "hand-reviewed venue dates, not distinct sets or nationwide recall",
        "references": len(capture.references.references),
        "capture_seconds": capture.seconds,
        "providers": {
            p: {
                "states": dict(Counter(f.state for f in findings if f.provider == p)),
                "requests": sum(
                    lookup.requests for lookup in capture.lookups if lookup.provider == p
                ),
                "complete_lookups": sum(
                    lookup.complete for lookup in capture.lookups if lookup.provider == p
                ),
                "lookup_seconds": round(
                    sum(lookup.seconds for lookup in capture.lookups if lookup.provider == p), 3
                ),
                "errors": [
                    lookup.error
                    for lookup in capture.lookups
                    if lookup.provider == p and lookup.error
                ],
            }
            for p in providers
        },
        "findings": [f.model_dump(mode="json") for f in findings],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    live = commands.add_parser("capture", help="explicit bounded, read-only network run")
    live.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    live.add_argument("--output", type=Path, default=CAPTURES / "capture.json")
    live.add_argument("--env-file", type=Path, default=Path(".env"))
    live.add_argument("--max-requests", type=int, default=50)
    live.add_argument(
        "--providers",
        nargs="+",
        choices=["ticketmaster", "ticketfairy"],
        default=["ticketmaster", "ticketfairy"],
    )
    offline = commands.add_parser("replay", help="local captured records only; no keys or network")
    offline.add_argument("capture", type=Path)
    args = parser.parse_args()
    if args.command == "capture":
        if not 1 <= args.max_requests <= 100:
            parser.error("max-requests must be between 1 and 100")
        if args.output.exists():
            parser.error("output already exists; choose a new path to preserve evidence")
        references = References.model_validate_json(args.references.read_text())
        settings = AuditSettings(_env_file=args.env_file)  # pyright: ignore[reportCallIssue]
        capture = asyncio.run(
            capture_sources(
                references,
                settings,
                args.max_requests,
                args.providers,
            )
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(capture.model_dump_json(indent=2) + "\n")
    else:
        capture = Capture.model_validate_json(args.capture.read_text())
    print(json.dumps(report(capture), indent=2))


if __name__ == "__main__":
    main()
