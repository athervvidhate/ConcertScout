from typing import Any


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
