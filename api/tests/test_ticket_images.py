"""A Ticket photo comes from the source, and a generic placeholder never counts as one."""

from typing import Any

import pytest

from concert_scout.sources.ticketmaster import parse_concert


def photo(url: str, *, width: int = 1024, ratio: str = "16_9", fallback: bool = False) -> Any:
    return {"url": url, "width": width, "ratio": ratio, "fallback": fallback}


def event(images: list[Any], artist_images: list[Any]) -> dict[str, Any]:
    return {
        "id": "one",
        "name": "One",
        "url": "https://tickets.example/one",
        "dates": {"start": {}},
        "images": images,
        "_embedded": {"attractions": [{"name": "Artist", "images": artist_images}]},
    }


def test_the_lead_artists_photo_wins_at_the_smallest_usable_size() -> None:
    artist = [
        photo("tiny", width=205),
        photo("huge", width=2048),
        photo("right"),
        photo("square", ratio="4_3"),
    ]
    assert parse_concert(event([photo("event")], artist)).image == "right"


def test_a_placeholder_gives_way_to_the_concert_image() -> None:
    placeholder = [photo("generic", fallback=True)]
    assert parse_concert(event([photo("event")], placeholder)).image == "event"


def test_a_real_photo_of_another_shape_beats_no_photo() -> None:
    # TicketWeb listings often report only a 3:2 photo, or none of the usual ratios.
    shapes = [photo("small", width=305, ratio="3_2"), photo("wide", width=640, ratio="3_2")]
    assert parse_concert(event(shapes, [])).image == "wide"
    unnamed = {"url": "unnamed", "width": 640}
    assert parse_concert(event([unnamed], [])).image == "unnamed"


def test_only_placeholders_leave_the_image_out() -> None:
    assert parse_concert(event([photo("generic", fallback=True)], [])).image is None


@pytest.mark.parametrize(("reported", "kept"), [("America/Chicago", True), ("Not/A_Zone", False)])
def test_a_concert_keeps_only_a_real_venue_zone(reported: str, kept: bool) -> None:
    record = event([], [])
    record["_embedded"]["venues"] = [{"name": "Venue", "timezone": reported}]
    assert parse_concert(record).time_zone == (reported if kept else None)
