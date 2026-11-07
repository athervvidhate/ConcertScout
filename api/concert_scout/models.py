import datetime as dt

from pydantic import BaseModel


class Price(BaseModel):
    min: float
    max: float
    currency: str


class Artist(BaseModel):
    """A Lineup entry, as reported by the Concert's source. A missing fact stays None."""

    name: str
    mbid: str | None = None
    genre: str | None = None
    subgenre: str | None = None


class Concert(BaseModel):
    """A Concert's facts, as reported by its source. A missing fact stays None."""

    id: str
    name: str
    url: str
    artists: list[Artist]
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


class SeedArtist(BaseModel):
    """An Artist named in a Search. With no MusicBrainz match, only the name is known."""

    name: str
    mbid: str | None = None
    tags: list[str] = []


class SimilarArtist(BaseModel):
    """A neighbour from a similarity source. `score` is that source's own raw number."""

    name: str
    mbid: str | None = None
    score: float


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


class Candidates(BaseModel):
    names: list[str]
    total: int


class SearchError(BaseModel):
    code: str
    message: str
    retry_after: int | None = None
