import datetime as dt

from pydantic import BaseModel


class Price(BaseModel):
    min: float
    max: float
    currency: str


class Concert(BaseModel):
    """A Concert's facts, as reported by its source. A missing fact stays None."""

    id: str
    name: str
    url: str
    artists: list[str]
    date: dt.date | None = None
    time: dt.time | None = None
    venue: str | None = None
    city: str | None = None
    region: str | None = None
    price: Price | None = None


class Recommendation(BaseModel):
    concert: Concert


class Poster(BaseModel):
    recommendations: list[Recommendation]


class Place(BaseModel):
    """Where a Search looks, as reported by the geocoder."""

    name: str
    lat: float
    lon: float


class Status(BaseModel):
    step: str
    message: str


class Interpreted(BaseModel):
    place: str | None
    start: dt.date | None
    end: dt.date | None
    artists: list[str]


class PoolTotal(BaseModel):
    total: int


class SearchError(BaseModel):
    code: str
    message: str
    retry_after: int | None = None
