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


class Status(BaseModel):
    step: str
    message: str


class SearchError(BaseModel):
    code: str
    message: str
    retry_after: int | None = None
