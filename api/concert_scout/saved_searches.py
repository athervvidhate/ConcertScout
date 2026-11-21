"""Saved Searches that rerun weekly and fold unseen Recommendations into the daily Alert email.

A Saved Search stores only the Search text and the Reading shown to the person — never visitor
coordinates, imported Taste or Spotify data (ADR 0003). Each Account may keep at most 5.

Weekly reruns run through the normal Search pipeline starting from the stored Reading (skipping
the interpreter), count against daily and monthly spend caps, and stop before live visitor caps
so background reruns never exhaust the app's Search budget.
"""

import datetime as dt
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Self
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, model_validator
from redis.exceptions import RedisError

from concert_scout import limits, pipeline
from concert_scout.config import Settings
from concert_scout.models import Poster, Reading, Recommendation
from concert_scout.pipeline import Services
from concert_scout.security import Refused
from concert_scout.sources import supabase
from concert_scout.sources.supabase import Account, DueSavedSearch, SavedSearch

logger = logging.getLogger(__name__)

MAX_SAVED_SEARCHES = 5
RERUN_INTERVAL = dt.timedelta(days=7)
FURTHEST_AHEAD = dt.timedelta(days=400)


class SavedReading(Reading):
    """A Reading stored in a Saved Search. Extra fields (coordinates, Taste) are refused."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def actionable_without_location(self) -> Self:
        if self.place and self.place.casefold() == "near you":
            raise ValueError("A Saved Search needs a named place, not your device location.")
        if not (self.place or self.artists):
            raise ValueError("A Saved Search needs an Artist or a named place.")
        furthest = dt.datetime.now(dt.UTC).date() + FURTHEST_AHEAD
        if any(day and day > furthest for day in (self.start, self.end)):
            raise ValueError("Dates are too far ahead.")
        return self


class SaveSearchRequest(BaseModel):
    """Only the Search text and Reading shown to the person. Extra fields are refused."""

    model_config = ConfigDict(extra="forbid")

    query_text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    reading: SavedReading


@dataclass(frozen=True)
class SavedSearchPicks:
    """Unseen Recommendations from one due Saved Search, ready to fold into the Account's Alert."""

    saved_search: DueSavedSearch
    recommendations: list[Recommendation]


def _canonical_reading(reading: Reading) -> dict[str, object]:
    return reading.model_dump(mode="json", exclude_none=True)


def _same_saved_search(existing: SavedSearch, query_text: str, reading: Reading) -> bool:
    return existing.query_text.casefold() == query_text.casefold() and _canonical_reading(
        existing.reading
    ) == _canonical_reading(reading)


def is_due(saved_search: SavedSearch, now: dt.datetime) -> bool:
    """True when a Saved Search has never run or its last run was at least 7 days ago."""
    if saved_search.last_run_at is None:
        return True
    now_utc = now.astimezone(dt.UTC) if now.tzinfo else now.replace(tzinfo=dt.UTC)
    last_utc = (
        saved_search.last_run_at.astimezone(dt.UTC)
        if saved_search.last_run_at.tzinfo
        else saved_search.last_run_at.replace(tzinfo=dt.UTC)
    )
    return (now_utc - last_utc) >= RERUN_INTERVAL


async def run_one(saved: DueSavedSearch, services: Services) -> list[Recommendation] | None:
    """Rerun one Saved Search through the normal Search pipeline from its stored Reading.

    Returns the list of Recommendations on success, or None if the pipeline emitted an error.
    """
    recommendations: list[Recommendation] = []
    errored = False
    async for event in pipeline.run_search(saved.reading, (), None, "UTC", services):
        if event.event == "poster":
            poster = Poster.model_validate(event.data)
            recommendations = poster.recommendations
        elif event.event == "error":
            errored = True
    return None if errored else recommendations


async def collect_due(
    services: Services,
    accounts_client: httpx.AsyncClient,
    secret_key: SecretStr,
    now: dt.datetime,
    deadline: float,
) -> dict[str, list[SavedSearchPicks]]:
    """Rerun due Saved Searches while budget and time remain, returning unseen picks per Account.

    Spend-cap priority: checks `limits.check_saved_search_spend` before EVERY rerun and stops
    immediately when spend approaches the daily or monthly cap, leaving skipped Saved Searches'
    `last_run_at` untouched so they wait cleanly for the next eligible run.
    """
    cutoff = now - RERUN_INTERVAL
    due = await supabase.due_saved_searches(accounts_client, secret_key, cutoff)
    due = [item for item in due if is_due(item, now)]
    if not due:
        return {}

    user_ids = list({item.user_id: None for item in due})
    paused = await supabase.paused_saved_search_users(accounts_client, secret_key, user_ids)
    active = [item for item in due if item.user_id not in paused]
    if not active:
        return {}

    sent_by_search = await supabase.saved_search_sent_for(
        accounts_client, secret_key, [item.id for item in active]
    )

    picks_by_user: dict[str, list[SavedSearchPicks]] = {}
    empty_ran: list[str] = []
    today = now.date()

    for saved in active:
        if time.monotonic() > deadline:
            break
        # Fixed past date window cannot return upcoming Concerts; advance last_run_at without spend.
        if saved.reading.end is not None and saved.reading.end < today:
            empty_ran.append(saved.id)
            continue
        try:
            await limits.check_saved_search_spend(services.redis)
        except (limits.SpendCapReached, RedisError) as exc:
            logger.info("Saved Search reruns stopped for spend cap: %s", type(exc).__name__)
            break

        recommendations = await run_one(saved, services)
        if recommendations is None:
            continue

        already_sent = sent_by_search.get(saved.id, set())
        unseen = [rec for rec in recommendations if rec.concert.id not in already_sent]
        if not unseen:
            empty_ran.append(saved.id)
            continue
        picks_by_user.setdefault(saved.user_id, []).append(
            SavedSearchPicks(saved_search=saved, recommendations=unseen)
        )

    if empty_ran:
        try:
            await supabase.mark_saved_search_ran(accounts_client, secret_key, empty_ran, now)
        except supabase.SupabaseError as exc:
            logger.warning("Saved Search last_run_at update failed: %s", exc)

    return picks_by_user


def account_routes(
    settings: Settings,
    client: httpx.AsyncClient,
    current_account: Callable[..., Awaitable[Account]],
) -> APIRouter:
    """Account routes for Saved Searches, mounted under `/account`."""
    assert settings.supabase_publishable_key and settings.supabase_secret_key
    publishable, secret = settings.supabase_publishable_key, settings.supabase_secret_key
    routes = APIRouter()
    unavailable = Refused(503, "accounts_unavailable", "Accounts are unavailable. Try again soon.")

    @routes.get("/saved-searches", response_model_exclude_none=True)
    async def list_saved_searches(
        account: Annotated[Account, Depends(current_account)],
    ) -> list[SavedSearch]:
        try:
            return await supabase.list_saved_searches(client, publishable, account)
        except supabase.SupabaseError as exc:
            logger.warning("Saved Searches read failed: %s", exc)
            raise unavailable from None

    @routes.post("/saved-searches", response_model_exclude_none=True)
    async def save_search(
        body: SaveSearchRequest,
        account: Annotated[Account, Depends(current_account)],
    ) -> SavedSearch:
        clean_reading = Reading.model_validate(body.reading.model_dump())
        try:
            existing = await supabase.list_saved_searches(client, publishable, account)
        except supabase.SupabaseError as exc:
            logger.warning("Saved Searches read failed: %s", exc)
            raise unavailable from None

        for item in existing:
            if _same_saved_search(item, body.query_text, clean_reading):
                return item

        if len(existing) >= MAX_SAVED_SEARCHES:
            raise Refused(
                409,
                "saved_search_limit",
                f"You can keep at most {MAX_SAVED_SEARCHES} Saved Searches. "
                "Remove one on your Account page first.",
            )

        try:
            return await supabase.create_saved_search(
                client, secret, account, body.query_text, clean_reading
            )
        except supabase.SupabaseError as exc:
            logger.warning("Saved Search write failed: %s", exc)
            raise unavailable from None

    @routes.delete("/saved-searches/{saved_search_id}", status_code=204)
    async def remove_saved_search(
        saved_search_id: Annotated[UUID, Path()],
        account: Annotated[Account, Depends(current_account)],
    ) -> Response:
        try:
            await supabase.delete_saved_search(client, publishable, account, str(saved_search_id))
        except supabase.SupabaseError as exc:
            logger.warning("Saved Search removal failed: %s", exc)
            raise unavailable from None
        return Response(status_code=204)

    return routes
