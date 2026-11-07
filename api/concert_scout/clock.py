"""Calendar days depend on where you stand, so nothing here reads the server's own zone."""

import datetime as dt
from zoneinfo import ZoneInfo


def known_zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError):
        return None


def now_in(name: str) -> dt.datetime:
    """Now in a visitor's zone. A browser that reports no real zone gets UTC."""
    return dt.datetime.now(known_zone(name) or dt.UTC)


def date_at(moment: dt.datetime, name: str | None) -> dt.date:
    """The calendar day in a zone, or the moment's own day when the zone is unknown."""
    zone = known_zone(name)
    return moment.astimezone(zone).date() if zone else moment.date()
