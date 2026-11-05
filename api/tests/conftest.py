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
CHICAGO = Place(name="Chicago, IL, United States of America", lat=41.8755616, lon=-87.6244212)


@pytest.fixture(autouse=True)
def fast_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "SLOT_SECONDS", 0.001)


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
            "attractions": [{"name": "Khruangbin"}, {"name": "Men I Trust"}],
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


def model_returning(*outputs: dict[str, Any]) -> FunctionModel:
    """A model that answers each request with the next output, without any network."""
    remaining = iter(outputs)

    def respond(_: list[ModelMessage], __: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(remaining)))])

    return FunctionModel(respond)
