"""Opt-in checks of actual provider contracts. These make network calls and may spend money."""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic_ai import models

from concert_scout.aliases import music_tag
from concert_scout.config import Settings
from concert_scout.interpreter import interpret, make_model
from concert_scout.sources import geocoder, lastfm, listenbrainz, musicbrainz, ticketmaster

pytestmark = pytest.mark.live


@pytest.fixture
async def provider_cache() -> AsyncIterator[FakeAsyncRedis]:
    # Fresh on every check so cached answers cannot hide a changed upstream contract.
    async with FakeAsyncRedis() as redis:
        yield redis


async def test_real_geocoding_resolves_shorthand_and_preserves_state_boundaries(
    provider_cache: FakeAsyncRedis,
) -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    async with geocoder.make_client(settings.geoapify_key.get_secret_value()) as client:
        city = await geocoder.geocode(client, provider_cache, "SF")
        state = await geocoder.geocode(client, provider_cache, "Texas")
    assert city and "San Francisco" in city.name
    assert city.state_code is None
    assert state and (state.country_code, state.state_code) == ("US", "TX")


async def test_real_ticketmaster_records_keep_their_ids_urls_dates_and_missing_values() -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    today = dt.date.today()
    async with ticketmaster.make_client(settings.tm_key.get_secret_value()) as client:
        response = await client.get(
            "/events.json",
            params={
                "segmentName": "Music",
                "countryCode": "US",
                "stateCode": "TX",
                "size": 5,
                "localStartDateTime": f"{today}T00:00:00,{today + dt.timedelta(days=30)}T23:59:59",
            },
        )
    assert response.status_code == 200
    records = response.json().get("_embedded", {}).get("events", [])
    assert records, "The live contract probe returned no records to validate"
    for record in records:
        concert = ticketmaster.parse_concert(record)
        assert (concert.id, concert.name, concert.url) == (
            record["id"],
            record["name"],
            record["url"],
        )
        start = record["dates"]["start"]
        if concert.date:
            assert concert.date.isoformat() == start["localDate"]
        if not start.get("localTime") or start.get("timeTBA") or start.get("noSpecificTime"):
            assert concert.time is None
        if concert.time:
            assert concert.time.isoformat() == start["localTime"]
        if concert.price:
            price = record["priceRanges"][0]
            assert (concert.price.min, concert.price.max, concert.price.currency) == (
                price["min"],
                price["max"],
                price["currency"],
            )
        elif not record.get("priceRanges"):
            assert concert.price is None


async def test_real_musicbrainz_resolves_an_artist_and_returns_domain_tags(
    provider_cache: FakeAsyncRedis,
) -> None:
    async with musicbrainz.make_client() as client:
        artist = await musicbrainz.resolve(client, provider_cache, "Khruangbin")
    assert artist.mbid and artist.name.casefold() == "khruangbin"


async def test_real_listenbrainz_metadata_is_read_by_the_adapter(
    provider_cache: FakeAsyncRedis,
) -> None:
    async with musicbrainz.make_client() as mb:
        seed = await musicbrainz.resolve(mb, provider_cache, "Khruangbin")
    assert seed.mbid
    async with listenbrainz.make_client() as client:
        tags = await listenbrainz.artist_tags(client, provider_cache, [seed.mbid])
    assert seed.mbid in tags and tags[seed.mbid], "No live metadata was available to validate"


async def test_real_lastfm_adapter_preserves_the_actual_response(
    provider_cache: FakeAsyncRedis,
) -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    if settings.lastfm_key is None:
        pytest.skip("LASTFM_KEY is not configured")
    bodies: list[dict[str, Any]] = []

    async def observe(response: httpx.Response) -> None:
        await response.aread()
        bodies.append(response.json())

    async with lastfm.make_client(settings.lastfm_key.get_secret_value()) as client:
        client.event_hooks["response"].append(observe)
        artists = await lastfm.similar_artists(client, provider_cache, "Khruangbin")
    records = bodies[0]["similarartists"]["artist"]
    assert [(a.name, a.mbid, a.score) for a in artists] == [
        (r["name"], r.get("mbid") or None, float(r["match"])) for r in records
    ]


async def test_real_interpreter_understands_ukg_and_sf_without_an_extra_call() -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    with models.override_allow_model_requests(True):
        result = await interpret(
            "UKG in SF", dt.date.today(), make_model(settings.anthropic_api_key.get_secret_value())
        )
    assert result.place and "san francisco" in result.place.casefold()
    assert "uk garage" in {music_tag(tag) for tag in result.tags}
    assert not result.artists
