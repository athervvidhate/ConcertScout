"""Fill the cache for busy places, so a first Search there skips the slowest source calls.

It runs the same pool and tag lookups a Search would, so it writes the very keys a Search reads.
"""

import datetime as dt
import logging
import time
from dataclasses import dataclass

from concert_scout import limits, pool
from concert_scout.pipeline import Services
from concert_scout.sources import geocoder, jambase, listenbrainz, ticketmaster

logger = logging.getLogger(__name__)

# Written as the interpreter writes places, so each geocodes to the point a Search there uses.
PLACES = (
    "New York, New York, United States",
    "Los Angeles, California, United States",
    "Chicago, Illinois, United States",
    "San Francisco, California, United States",
    "Seattle, Washington, United States",
    "Austin, Texas, United States",
    "Nashville, Tennessee, United States",
    "Denver, Colorado, United States",
    "Boston, Massachusetts, United States",
    "Atlanta, Georgia, United States",
    "Washington, District of Columbia, United States",
    "London, England, United Kingdom",
)


@dataclass(frozen=True)
class Warmed:
    place: str
    concerts: int
    artists: int
    seconds: float
    error: str | None = None


async def warm(services: Services, now: dt.datetime) -> list[Warmed]:
    """One place at a time, since every Ticketmaster call shares one rate limit anyway.

    Today's Ticketmaster allowance belongs to visitors first, so reaching it stops the run.
    """
    warmed: list[Warmed] = []
    if services.jambase:
        reports = await jambase.refresh(
            services.jambase,
            services.redis,
            services.jambase_regions,
            services.jambase_days,
            now,
        )
        warmed.extend(
            Warmed(f"JamBase {r.region}", r.concerts, 0, r.seconds, r.error) for r in reports
        )
    for name in PLACES:
        try:
            warmed.append(await _warm_place(services, name, now))
        except limits.DailyLimitReached:
            logger.warning("Warming stopped at the Ticketmaster daily limit")
            break
    return warmed


async def _warm_place(services: Services, name: str, now: dt.datetime) -> Warmed:
    started = time.perf_counter()
    tag_fetch = listenbrainz.TagFetch(services.listenbrainz, services.redis)
    try:
        place = await geocoder.geocode(services.geocoder, services.redis, name)
        if place is None:
            return Warmed(name, 0, 0, time.perf_counter() - started, "not found")
        concerts = await pool.find_concerts(
            services.ticketmaster,
            services.redis,
            place,
            [],
            None,
            None,
            now,
            on_found=tag_fetch.add,
        )
        tags = await tag_fetch.tags()
        return Warmed(name, len(concerts), len(tags), time.perf_counter() - started)
    except (geocoder.GeocoderError, ticketmaster.TicketmasterError) as exc:
        logger.warning("Warming %s failed: %s", name, exc)
        return Warmed(name, 0, 0, time.perf_counter() - started, str(exc))
    finally:
        await tag_fetch.close()
