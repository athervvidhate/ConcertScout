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

from concert_scout import pool, security, similarity
from concert_scout.config import Settings
from concert_scout.models import Artist, Concert, Place, Price, SeedArtist
from concert_scout.sources import geocoder, listenbrainz, musicbrainz

PLACE = Place(name="San Francisco, California", lat=37.77, lon=-122.42)
DAY = dt.date.today() + dt.timedelta(days=14)
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
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        tm_key=SecretStr("unused-test-key"),
        anthropic_api_key=SecretStr("unused-test-key"),
        geoapify_key=SecretStr("unused-test-key"),
        cors_origins=["http://localhost:3000", "http://127.0.0.1:3146"],
        **overrides,
    )


def forbidden_http(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Unexpected vendor HTTP: {request.url.host}")


def contract_model() -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = " ".join(
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart) and isinstance(p.content, str)
        )
        output: dict[str, Any]
        if info.instructions and "Choose the Concerts" in info.instructions:
            prompt = json.loads(text)
            ids = [] if "empty" in prompt["taste"]["descriptors"] else [c.id for c in CONCERTS]
            output = {
                "picks": [
                    {"id": id, "score": 85, "reason": "A source-backed match"}
                    for id in [*ids, "unknown-id"]
                ]
            }
            if not ids:
                output = {"picks": []}
        else:
            output = {
                "artists": [],
                "descriptors": ["empty"] if "empty" in text else ["UKG"],
                "tags": ["ukg"],
                "place": None if "near me" in text else "SF",
                "start": None,
                "end": None,
            }
        return ModelResponse(parts=[TextPart(json.dumps(output))])

    return FunctionModel(respond)


def install_sources(patch: pytest.MonkeyPatch) -> None:
    patch.setattr(geocoder, "geocode", AsyncMock(return_value=PLACE))
    patch.setattr(pool, "find_concerts", AsyncMock(return_value=CONCERTS))
    patch.setattr(
        musicbrainz, "resolve", AsyncMock(return_value=SeedArtist(name="Contract Artist"))
    )
    patch.setattr(similarity, "find_neighbours", AsyncMock(return_value=[]))
    patch.setattr(
        listenbrainz,
        "artist_tags",
        AsyncMock(return_value={"contract-artist": ["uk garage"], "second-artist": ["uk garage"]}),
    )

    async def verify(_: httpx.AsyncClient, __: SecretStr, token: str, ___: str) -> None:
        if token == "reject":
            raise security.Refused(403, "bot_check_failed", "The bot check did not pass.")

    patch.setattr(security, "verify_turnstile", verify)
