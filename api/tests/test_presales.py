"""Sale dates come from the source, and only a real presale ever reaches a Ticket."""

import datetime as dt
from typing import Any

from concert_scout.models import Presale
from concert_scout.sources.ticketmaster import parse_concert

GENERAL = "2027-01-15T18:00:00Z"
OPENS = dt.datetime(2027, 1, 13, 18, tzinfo=dt.UTC)
CLOSES = dt.datetime(2027, 1, 14, 18, tzinfo=dt.UTC)


def presale(name: str) -> dict[str, str]:
    return {
        "name": name,
        "startDateTime": "2027-01-13T18:00:00Z",
        "endDateTime": "2027-01-14T18:00:00Z",
    }


def event(public: dict[str, Any], presales: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "id": "one",
        "name": "One",
        "url": "https://tickets.example/one",
        "dates": {"start": {}},
        "sales": {"public": public, "presales": presales},
    }


def test_presale_keeps_source_times_and_reads_as_a_presale() -> None:
    concert = parse_concert(
        event(
            {"startDateTime": GENERAL},
            [presale("LIVE NATION PRESALE"), presale("Reserved by Spotify")],
        )
    )
    assert concert.general_sale == dt.datetime(2027, 1, 15, 18, tzinfo=dt.UTC)
    assert concert.presales == [
        Presale(name="Live Nation Presale", start=OPENS, end=CLOSES),
        Presale(name="Reserved by Spotify presale", start=OPENS, end=CLOSES),
    ]


def test_vip_packages_and_public_onsales_are_not_presales() -> None:
    names = ["VIP Package Onsale", "Artist VIP Packages Presale", "Public Onsale"]
    concert = parse_concert(event({"startDateTime": GENERAL}, [presale(n) for n in names]))
    assert concert.presales == []


def test_ticketmasters_placeholder_sale_date_means_no_presale() -> None:
    concert = parse_concert(
        event({"startDateTime": "1900-01-01T06:00:00Z"}, [presale("Artist Presale")])
    )
    assert concert.general_sale is None
    assert concert.presales == []


def test_a_general_sale_still_to_be_announced_keeps_its_presale() -> None:
    concert = parse_concert(event({"startTBA": True}, [presale("Artist Presale")]))
    assert concert.general_sale is None
    assert [p.name for p in concert.presales] == ["Artist Presale"]


def test_a_presale_missing_a_time_is_left_out() -> None:
    concert = parse_concert(event({"startDateTime": GENERAL}, [{"name": "Artist Presale"}]))
    assert concert.presales == []
