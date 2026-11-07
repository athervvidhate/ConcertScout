import datetime as dt

from pydantic import BaseModel

# A circle this wide already covers most of a large country.
MAX_RADIUS_MILES = 500


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


class Presale(BaseModel):
    name: str
    start: dt.datetime
    end: dt.datetime


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
    image: str | None = None
    general_sale: dt.datetime | None = None
    presales: list[Presale] = []


class Recommendation(BaseModel):
    """One Artist on a Poster. `also` holds the same Artist's other dates, from the same source."""

    concert: Concert
    reason: str
    score: int | None = None
    also: list[Concert] = []


class Poster(BaseModel):
    recommendations: list[Recommendation]


class Place(BaseModel):
    """Where a Search looks, as reported by the geocoder."""

    name: str
    lat: float
    lon: float
    state_code: str | None = None
    country_code: str | None = None
    # How far a region reaches. Without one, a place gets the standard radius.
    radius_miles: int | None = None


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


class Places(BaseModel):
    places: list[Place]


class Nearby(BaseModel):
    concerts: list[Concert]


class Track(BaseModel):
    name: str
    url: str


class ArtistProfile(BaseModel):
    """What the Artist panel shows. Anything a source does not report stays empty."""

    name: str
    lastfm_url: str | None = None
    spotify_url: str | None = None
    listeners: int | None = None
    bio: str | None = None
    tags: list[str] = []
    top_tracks: list[Track] = []
    similar: list[str] = []


class ArtistProfiles(BaseModel):
    """One profile, or one for each Artist on a tour billed as a single name."""

    profiles: list[ArtistProfile]


class Status(BaseModel):
    step: str
    message: str


class Interpreted(BaseModel):
    place: str | None
    region: str | None
    radius_miles: int | None
    start: dt.date | None
    end: dt.date | None
    artists: list[str]
    genres: list[str]


class PoolTotal(BaseModel):
    total: int


class Candidates(BaseModel):
    names: list[str]
    total: int


class SearchError(BaseModel):
    code: str
    message: str
    retry_after: int | None = None


class ImportedTaste(BaseModel):
    """A person's Artists, favourites first. The server keeps none of this."""

    artists: list[str]
