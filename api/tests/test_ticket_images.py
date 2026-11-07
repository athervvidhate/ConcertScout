"""A Ticket photo comes from the source, and a generic placeholder never counts as one."""

from typing import Any

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


def test_only_placeholders_leave_the_image_out() -> None:
    assert parse_concert(event([photo("generic", fallback=True)], [])).image is None
