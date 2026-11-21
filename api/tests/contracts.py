"""Domain fixtures at app-owned adapter boundaries, with all vendor HTTP forbidden."""

import datetime as dt
import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout import pool, ranker, refinement, security, similarity
from concert_scout.config import Settings
from concert_scout.models import Artist, Concert, Place, Price, SeedArtist
from concert_scout.sources import (
    geocoder,
    jev,
    listenbrainz,
    musicbrainz,
    spotify_catalog,
    venues,
)

PLACE = Place(name="San Francisco, California", lat=37.77, lon=-122.42)
DAY = dt.date.today() + dt.timedelta(days=14)
# A week before the Concerts, so a Search dated DAY never reaches back past its month.
NOW = dt.datetime.combine(DAY - dt.timedelta(days=7), dt.time(12), dt.UTC)
CONCERTS = [
    Concert(
        id="contract-one",
        name="Contract Concert One",
        artists=[Artist(name="Contract Artist", mbid="contract-artist")],
        date=DAY,
        time=dt.time(19, 30),
        venue="Source Hall",
        city="San Francisco",
        region="CA",
        price=Price(min=38, max=38, currency="USD"),
        url="https://tickets.example/one",
        image="/spotify-logo-white.svg",
    ),
    Concert(
        id="contract-two",
        name="Contract Concert Two",
        artists=[Artist(name="Second Contract Artist", mbid="second-artist")],
        date=DAY + dt.timedelta(days=1),
        venue="Second Hall",
        city="San Francisco",
        region="CA",
        url="https://tickets.example/two",
    ),
    Concert(
        id="contract-three",
        name="Contract Concert Three",
        artists=[Artist(name="Contract Artist", mbid="contract-artist")],
        date=DAY + dt.timedelta(days=3),
        venue="Third Hall",
        city="Oakland",
        region="CA",
        url="https://tickets.example/three",
    ),
]


def settings_with(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "tm_key": SecretStr("unused-test-key"),
        "anthropic_api_key": SecretStr("unused-test-key"),
        "geoapify_key": SecretStr("unused-test-key"),
        "typesafe_api_key": SecretStr("unused-test-key"),
        "cors_origins": ["http://localhost:3000"],
    }
    return Settings(_env_file=None, **(defaults | overrides))  # pyright: ignore[reportCallIssue]


def forbidden_http(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Unexpected vendor HTTP: {request.url.host}")


def idle_musicbrainz() -> httpx.AsyncClient:
    """For a test whose Concerts all have a Lineup, so nothing should ask MusicBrainz."""
    return musicbrainz.make_client(httpx.MockTransport(forbidden_http))


def _contract_refinement(prompt: dict[str, Any]) -> dict[str, Any]:
    reading: dict[str, Any] = dict(prompt.get("reading", {}))
    poster_artists: list[str] = list(prompt.get("poster_artists", []))
    raw = str(prompt.get("refinement", "")).strip()
    lower = raw.casefold()

    if any(word in lower for word in ("all ages", "age", "park", "parking", "doors", "set time")):
        matched = poster_artists[0] if poster_artists else None
        for name in poster_artists:
            if name.casefold() in lower:
                matched = name
                break
        return {
            "kind": "unanswerable",
            "note": (
                "Concert Scout can't tell from the Concert listing. "
                "Check the ticket page for details."
            ),
            "artist": matched,
        }

    base: dict[str, Any] = {
        "kind": "refined",
        "chip_label": raw[:48],
        "artists": list(reading.get("artists", [])),
        "descriptors": list(reading.get("descriptors", [])),
        "tags": list(reading.get("tags", [])),
        "genres": list(reading.get("genres", [])),
        "place": reading.get("place"),
        "region": reading.get("region"),
        "radius_miles": reading.get("radius_miles"),
        "start": reading.get("start"),
        "end": reading.get("end"),
        "max_price": reading.get("max_price"),
        "weekends_only": bool(reading.get("weekends_only", False)),
        "weekdays": list(reading.get("weekdays", [])),
        "boost_artists": [],
        "exclude_artists": [],
    }

    if "saturday" in lower:
        base["weekdays"] = [5]
        base["weekends_only"] = False
        base["chip_label"] = "Saturdays only"
    elif "weekend" in lower:
        base["weekends_only"] = True
        base["weekdays"] = []
        base["chip_label"] = "Weekends only"
    elif "oakland" in lower:
        base["place"] = "Oakland, California, United States"
        base["region"] = None
        base["radius_miles"] = None
        base["chip_label"] = "Try Oakland"
    elif "cheaper" in lower or "under $" in lower:
        current = reading.get("max_price")
        cap = 40.0 if current is None else max(20.0, round(float(current) * 0.65))
        base["max_price"] = cap
        base["chip_label"] = f"Under ${int(cap)}"
    elif "more like" in lower:
        chosen: str | None = None
        if ("second" in lower or "#2" in lower) and len(poster_artists) >= 2:
            chosen = poster_artists[1]
        elif ("first" in lower or "#1" in lower) and poster_artists:
            chosen = poster_artists[0]
        else:
            for name in poster_artists:
                if name.casefold() in lower:
                    chosen = name
                    break
        if chosen is None:
            chosen = raw.split("like", 1)[-1].strip()
        if chosen:
            if chosen not in base["artists"]:
                base["artists"].append(chosen)
            base["boost_artists"] = [chosen]
            base["chip_label"] = f"More like {chosen}"

    return base


def contract_model() -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = " ".join(
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart) and isinstance(p.content, str)
        )
        output: dict[str, Any]
        if info.instructions == ranker.REASONS:
            prompt = json.loads(text)
            output = {
                "reasons": [
                    {"id": row["id"], "reason": "A source-backed match"}
                    for row in prompt["candidates"]
                ]
            }
        elif (info.instructions or "").startswith(refinement.INSTRUCTIONS):
            output = _contract_refinement(json.loads(text))
        else:
            output = {
                "artists": [],
                "descriptors": []
                if "place only" in text
                else ["empty" if "empty" in text else "UKG"],
                "tags": [] if "place only" in text else ["ukg"],
                "genres": ["Dance/Electronic"] if "sound" in text else [],
                "place": None if "near me" in text else "SF",
                "start": None,
                "end": None,
            }
        return ModelResponse(parts=[TextPart(json.dumps(output))])

    return FunctionModel(respond)


async def contract_grades(
    _: httpx.AsyncClient, taste: dict[str, list[str]], rows: dict[str, str]
) -> dict[str, int]:
    """Every row a strong fit, except that an "empty" Taste is a verdict that nothing fits."""
    level = 0 if "empty" in taste["descriptors"] else 3
    return {id_: level for id_ in rows}


async def contract_concert(_: httpx.AsyncClient, __: object, concert_id: str) -> Concert:
    """A saved Concert's facts, from the same source records the Poster used."""
    for concert in CONCERTS:
        if concert.id == concert_id:
            return concert
    raise pool.ConcertNotFound


async def contract_venue(
    _musicbrainz: object,
    _wikidata: object,
    _redis: object,
    name: str,
    city: str | None = None,
    _lat: float | None = None,
    _lon: float | None = None,
) -> venues.VenueCharacter:
    """One verified venue and one unverified venue from the contract Concerts."""
    if venues.venue_key(name, city) == venues.venue_key("Source Hall", "San Francisco"):
        return venues.VenueCharacter(
            name=name,
            city=city,
            capacity=450,
            tier="Intimate club",
            venue_type="Music venue",
        )
    return venues.VenueCharacter(name=name, city=city)


def install_sources(patch: pytest.MonkeyPatch) -> None:
    patch.setattr(pool, "find_concert", contract_concert)
    patch.setattr(venues, "lookup", contract_venue)
    patch.setattr(jev, "grade", contract_grades)
    patch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    patch.setattr(pool, "find_concerts", AsyncMock(return_value=CONCERTS))
    patch.setattr(pool, "find_elsewhere", AsyncMock(return_value=[]))
    patch.setattr(
        musicbrainz, "resolve", AsyncMock(return_value=SeedArtist(name="Contract Artist"))
    )
    patch.setattr(similarity, "find_neighbours", AsyncMock(return_value=[]))
    patch.setattr(spotify_catalog, "artist_page", AsyncMock(return_value=None))
    patch.setattr(
        listenbrainz.TagFetch,
        "tags",
        AsyncMock(return_value={"contract-artist": ["uk garage"], "second-artist": ["uk garage"]}),
    )

    async def verify(_: httpx.AsyncClient, __: SecretStr, token: str, ___: str) -> None:
        if token == "reject":
            raise security.Refused(403, "bot_check_failed", "The bot check did not pass.")

    patch.setattr(security, "verify_turnstile", verify)
