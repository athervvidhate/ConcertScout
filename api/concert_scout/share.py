"""Shared Posters: a Poster the server produced, kept at its own link.

The browser never sends a Poster. `keep` stores what a Search produced under a Search ID that only
that Search's stream carries, and `promote` turns it into a Shared Poster. Only Recommendations
and the Search's reading are stored, so a Shared Poster never holds the person's coordinates.
"""

import base64
import datetime as dt
import hashlib
import secrets

from pydantic import BaseModel
from redis.asyncio import Redis

from concert_scout import assemble
from concert_scout.models import Interpreted, Recommendation

# A Search ID is only good for sharing soon after its Search.
SEARCH_TTL = dt.timedelta(hours=6)
SHARE_TTL = dt.timedelta(days=90)
# 16 random bytes make a 22-character Search ID; 9 bytes of its hash make a 12-character link.
SEARCH_ID = r"^[A-Za-z0-9_-]{22}$"
SHARE_ID = r"^[A-Za-z0-9_-]{12}$"


class Made(BaseModel):
    """What one Search produced. This is all a Shared Poster ever holds."""

    made: dt.date
    interpreted: Interpreted | None
    recommendations: list[Recommendation]


class NotFound(Exception):
    """The Search ID or link is unknown, or its record has expired."""


def _search_key(search_id: str) -> str:
    return f"share:search:{search_id}"


def _poster_key(share_id: str) -> str:
    return f"share:poster:{share_id}"


def share_id(search_id: str) -> str:
    """The link follows from the secret Search ID, so sharing a Search again gives the same link."""
    digest = hashlib.sha256(f"share\x00{search_id}".encode()).digest()
    return base64.urlsafe_b64encode(digest[:9]).decode()


async def keep(redis: Redis, made: Made) -> str:
    """Store a finished Search's Poster and return its Search ID."""
    search_id = secrets.token_urlsafe(16)
    await redis.set(_search_key(search_id), made.model_dump_json(), ex=SEARCH_TTL)
    return search_id


async def promote(redis: Redis, search_id: str) -> str:
    """Make a kept Search's Poster a Shared Poster. A second call changes nothing."""
    kept = await redis.get(_search_key(search_id))
    if kept is None:
        raise NotFound
    link = share_id(search_id)
    await redis.set(_poster_key(link), kept, ex=SHARE_TTL, nx=True)
    return link


async def read(redis: Redis, link: str, today: dt.date) -> Made:
    """The Poster behind a link, without Concerts that have passed."""
    stored = await redis.get(_poster_key(link))
    if stored is None:
        raise NotFound
    made = Made.model_validate_json(stored)
    return made.model_copy(
        update={"recommendations": assemble.upcoming(made.recommendations, today)}
    )
