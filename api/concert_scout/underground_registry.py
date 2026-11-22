"""Explicit curated registry of flagship underground electronic and indie rooms.

Only rooms listed here are fetched by `/sync-underground` for public `schema.org/MusicEvent`
JSON-LD calendars. Coordinates and IANA time zones anchor geospatial and local-date filtering.
"""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator

from concert_scout import clock


class UndergroundVenue(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    city: str
    region: str
    lat: float
    lon: float
    time_zone: str
    calendar_url: str

    @field_validator("calendar_url")
    @classmethod
    def https_only(cls, value: str) -> str:
        if urlsplit(value).scheme != "https":
            raise ValueError("venue calendar URL must use HTTPS")
        return value

    @field_validator("time_zone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        if clock.known_zone(value) is None:
            raise ValueError(f"unknown IANA time zone: {value}")
        return value


VENUES: tuple[UndergroundVenue, ...] = (
    UndergroundVenue(
        slug="nowadays",
        name="Nowadays",
        city="Queens",
        region="NY",
        lat=40.6927,
        lon=-73.9016,
        time_zone="America/New_York",
        calendar_url="https://nowadays.nyc/calendar/",
    ),
    UndergroundVenue(
        slug="public-records",
        name="Public Records",
        city="Brooklyn",
        region="NY",
        lat=40.6808,
        lon=-73.9873,
        time_zone="America/New_York",
        calendar_url="https://publicrecords.nyc/calendar",
    ),
    UndergroundVenue(
        slug="elsewhere",
        name="Elsewhere",
        city="Brooklyn",
        region="NY",
        lat=40.7094,
        lon=-73.9231,
        time_zone="America/New_York",
        calendar_url="https://www.elsewherebrooklyn.com/events",
    ),
    UndergroundVenue(
        slug="smartbar",
        name="Smartbar",
        city="Chicago",
        region="IL",
        lat=41.9498,
        lon=-87.6589,
        time_zone="America/Chicago",
        calendar_url="https://smartbarchicago.com/events/",
    ),
    UndergroundVenue(
        slug="marble-bar",
        name="Marble Bar",
        city="Detroit",
        region="MI",
        lat=42.3718,
        lon=-83.0734,
        time_zone="America/Detroit",
        calendar_url="https://www.marblebardetroit.com/events",
    ),
    UndergroundVenue(
        slug="1015-folsom",
        name="1015 Folsom",
        city="San Francisco",
        region="CA",
        lat=37.7781,
        lon=-122.4058,
        time_zone="America/Los_Angeles",
        calendar_url="https://1015.com/events/",
    ),
    UndergroundVenue(
        slug="basement",
        name="Basement",
        city="Queens",
        region="NY",
        lat=40.7131,
        lon=-73.9114,
        time_zone="America/New_York",
        calendar_url="https://basementny.net/",
    ),
    UndergroundVenue(
        slug="good-room",
        name="Good Room",
        city="Brooklyn",
        region="NY",
        lat=40.7267,
        lon=-73.9529,
        time_zone="America/New_York",
        calendar_url="https://www.goodroombk.com/events",
    ),
)

_BY_SLUG: dict[str, UndergroundVenue] = {venue.slug: venue for venue in VENUES}


def by_slug(slug: str) -> UndergroundVenue | None:
    return _BY_SLUG.get(slug)
