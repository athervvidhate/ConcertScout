import datetime as dt
import json
from typing import Any

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import limits
from concert_scout.models import Place
from concert_scout.sources import ticketmaster

# A test that reaches a real model fails instead of spending money.
models.ALLOW_MODEL_REQUESTS = False

UPCOMING = dt.date.today() + dt.timedelta(days=14)
TYLER_MBID = "9947e874-ddd0-4e1a-b0d4-a76f6532fe45"
KHRUANGBIN_MBID = "khruangbin-mbid"
CHICAGO = Place(name="Chicago, IL, United States of America", lat=41.8755616, lon=-87.6244212)


@pytest.fixture(autouse=True)
def fast_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "SLOT_SECONDS", 0.001)
    monkeypatch.setattr(limits, "MUSICBRAINZ_GAP", dt.timedelta(milliseconds=1))


def tm_record(**overrides: Any) -> dict[str, Any]:
    """A Ticketmaster event record, in the shape the live API returns."""
    record: dict[str, Any] = {
        "name": "Khruangbin: The Ether Tour",
        "type": "event",
        "id": "vvG18Z_ueUZbii",
        "url": "https://www.ticketmaster.com/event/040064D0B6018B2C",
        "dates": {
            "start": {
                "localDate": "2026-11-20",
                "localTime": "19:30:00",
                "dateTime": "2026-11-21T01:30:00Z",
                "dateTBD": False,
                "dateTBA": False,
                "timeTBA": False,
                "noSpecificTime": False,
            },
            "timezone": "America/Chicago",
            "status": {"code": "onsale"},
        },
        "priceRanges": [{"type": "standard", "currency": "USD", "min": 45.5, "max": 120.0}],
        "_embedded": {
            "venues": [
                {
                    "name": "The Salt Shed",
                    "city": {"name": "Chicago"},
                    "state": {"name": "Illinois", "stateCode": "IL"},
                    "country": {"name": "United States Of America", "countryCode": "US"},
                }
            ],
            "attractions": [
                {"name": "Khruangbin", "externalLinks": {"musicbrainz": [{"id": KHRUANGBIN_MBID}]}},
                {"name": "Men I Trust"},
            ],
        },
    }
    return record | overrides


def upcoming_record(**overrides: Any) -> dict[str, Any]:
    """A record inside the default date window, whenever the tests run."""
    record = tm_record(**overrides)
    record["dates"]["start"]["localDate"] = str(UPCOMING)
    return record


def tm_body(*records: dict[str, Any], total: int | None = None) -> dict[str, Any]:
    elements = len(records) if total is None else total
    size = ticketmaster.PAGE_SIZE
    page = {
        "size": size,
        "totalElements": elements,
        "totalPages": -(-elements // size),
        "number": 0,
    }
    if not records:
        return {"page": page}
    return {"_embedded": {"events": list(records)}, "page": page}


def geoapify_result(**overrides: Any) -> dict[str, Any]:
    """A Geoapify autocomplete result, in the shape the docs describe for `format=json`."""
    result: dict[str, Any] = {
        "name": "Chicago",
        "city": "Chicago",
        "state": "Illinois",
        "state_code": "IL",
        "country": "United States",
        "country_code": "us",
        "lat": CHICAGO.lat,
        "lon": CHICAGO.lon,
        "formatted": CHICAGO.name,
        "result_type": "city",
        "rank": {"confidence": 1, "match_type": "full_match"},
    }
    return result | overrides


def mb_artist(**overrides: Any) -> dict[str, Any]:
    """A MusicBrainz search hit, in the shape the live API returns."""
    artist: dict[str, Any] = {
        "id": TYLER_MBID,
        "name": "Tyler Childers",
        "sort-name": "Childers, Tyler",
        "score": 100,
        "type": "Person",
        "country": "US",
        "tags": [
            {"count": 3, "name": "country"},
            {"count": 4, "name": "americana"},
            {"count": 3, "name": "alternative country"},
        ],
    }
    return artist | overrides


def lb_similar(*names_and_mbids: tuple[str, str], top_score: int = 300) -> list[dict[str, Any]]:
    """A ListenBrainz Labs similar-artists body, closest first, in the live shape."""
    return [
        {
            "artist_mbid": mbid,
            "name": name,
            "comment": "",
            "type": "Person",
            "gender": "Male",
            "score": top_score // (n + 1),
            "reference_mbid": TYLER_MBID,
        }
        for n, (name, mbid) in enumerate(names_and_mbids)
    ]


def lb_metadata(**tags_by_mbid: list[str]) -> list[dict[str, Any]]:
    """A ListenBrainz artist metadata body with `inc=tag`, in the live shape."""
    return [
        {
            "artist_mbid": mbid,
            "mbid": mbid,
            "name": "An Artist",
            "tag": {"artist": [{"artist_mbid": mbid, "count": 1, "tag": t} for t in tags]},
        }
        for mbid, tags in tags_by_mbid.items()
    ]


def lastfm_similar(*names: str) -> dict[str, Any]:
    """A Last.fm artist.getSimilar body, in the shape its docs show. `match` is a string."""
    artists = [
        {"name": name, "mbid": "", "match": str(1 - n / 10), "url": "https://www.last.fm/music/x"}
        for n, name in enumerate(names)
    ]
    return {"similarartists": {"artist": artists, "@attr": {"artist": "Tyler Childers"}}}


def interpretation(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "artists": [],
        "descriptors": [],
        "tags": [],
        "place": None,
        "start": None,
        "end": None,
    }
    return fields | overrides


def picks(*picked: tuple[str, int, str]) -> dict[str, Any]:
    """A ranker answer."""
    return {"picks": [{"id": id, "score": score, "reason": reason} for id, score, reason in picked]}


def model_returning(*outputs: dict[str, Any]) -> FunctionModel:
    """A model that answers each request with the next output, without any network."""
    remaining = iter(outputs)

    def respond(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(remaining)))])

    return FunctionModel(respond)
