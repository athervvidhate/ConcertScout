import json
from typing import Any

from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from concert_scout.models import Place

# A test that reaches a real model fails instead of spending money.
models.ALLOW_MODEL_REQUESTS = False

CHICAGO = Place(name="Chicago, IL, United States of America", lat=41.8755616, lon=-87.6244212)


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


def tm_body(*records: dict[str, Any]) -> dict[str, Any]:
    if not records:
        return {"page": {"size": 50, "totalElements": 0, "totalPages": 0, "number": 0}}
    return {"_embedded": {"events": list(records)}}


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
