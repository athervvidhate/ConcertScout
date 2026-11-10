import datetime as dt
import unicodedata
from typing import Annotated, Literal, Self, get_args

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

# A circle this wide already covers most of a large country.
MAX_RADIUS_MILES = 500

# Sources may send a letter and its accent as two characters, such as E and a combining macron.
# A display face places a precomposed letter well but may not stack the pair. NFC is the same text.
Text = Annotated[str, AfterValidator(lambda value: unicodedata.normalize("NFC", value))]

# The broad listing genres a Taste can fall under.
Genre = Literal[
    "Rock",
    "Alternative",
    "Pop",
    "Hip-Hop/Rap",
    "R&B",
    "Dance/Electronic",
    "Country",
    "Folk",
    "Jazz",
    "Blues",
    "Metal",
    "Latin",
    "Reggae",
    "World",
    "Classical",
]
GENRES: frozenset[str] = frozenset(get_args(Genre))


class Price(BaseModel):
    min: float
    max: float
    currency: str


class Artist(BaseModel):
    """A Lineup entry, as reported by the Concert's source. A missing fact stays None."""

    name: Text
    mbid: str | None = None
    # A public catalog identity when the source does not expose a MusicBrainz ID.
    source_id: str | None = None
    genre: str | None = None
    subgenre: str | None = None


class Presale(BaseModel):
    name: Text
    start: dt.datetime
    end: dt.datetime


class Concert(BaseModel):
    """A Concert's facts, as reported by its source. A missing fact stays None."""

    id: str
    name: Text
    url: str
    artists: list[Artist]
    source: Literal["ticketmaster", "jambase"] = "ticketmaster"
    date: dt.date | None = None
    time: dt.time | None = None
    # The venue's IANA zone. `date` and `time` already read in it.
    time_zone: str | None = None
    venue: Text | None = None
    city: Text | None = None
    region: Text | None = None
    price: Price | None = None
    image: str | None = None
    general_sale: dt.datetime | None = None
    presales: list[Presale] = []
    # The source bills the Concert under its own name, such as a festival's, above its Lineup.
    # Its name then says what the Concert is, and no one Artist stands for it.
    festival: bool = False


class Recommendation(BaseModel):
    """One Artist on a Poster. `also` holds the same Artist's other source-backed dates."""

    concert: Concert
    reason: str
    # The ranker's level, 0 to 3. A seed or a fallback Recommendation has none.
    score: int | None = None
    also: list[Concert] = []
    # A festival's Lineup entries that suit the Search, best first, named as the source names them.
    lineup_match: list[str] = []


class Poster(BaseModel):
    recommendations: list[Recommendation]


class Elsewhere(BaseModel):
    """Nothing fit the Search's place, so these match its words anywhere. No model chose them."""

    keyword: str
    concerts: list[Concert]


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

    name: Text
    mbid: str | None = None
    tags: list[str] = []


class SimilarArtist(BaseModel):
    """A neighbour from a similarity source. `score` is that source's own raw number."""

    name: Text
    mbid: str | None = None
    score: float


class Places(BaseModel):
    places: list[Place]


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


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# Bounds on a Reading. A Search's 500 characters hold no more than this, so a corrected Reading
# can ask for nothing a typed Search could not.
MAX_ARTISTS = 20
MAX_WORDS = 30


class Reading(BaseModel):
    """What a Search was taken to mean. The interpreter writes it, and a person can correct it."""

    artists: Annotated[list[Name], Field(max_length=MAX_ARTISTS)] = []
    # The Search's own words for a sound, and the music tags they expand to.
    descriptors: Annotated[list[Word], Field(max_length=MAX_WORDS)] = []
    tags: Annotated[list[Word], Field(max_length=MAX_WORDS)] = []
    genres: Annotated[list[Genre], Field(max_length=len(GENRES))] = []
    place: Name | None = None
    # A named area wider than a city. `place` is then a large city near its middle.
    region: Word | None = None
    radius_miles: Annotated[int, Field(ge=1, le=MAX_RADIUS_MILES)] | None = None
    start: dt.date | None = None
    end: dt.date | None = None

    @model_validator(mode="after")
    def holds_together(self) -> Self:
        if self.start and self.end and self.end < self.start:
            raise ValueError("end is before start")
        if self.radius_miles and not self.place:
            raise ValueError("a radius needs a place")
        if self.region and not self.radius_miles:
            raise ValueError("a region needs a radius")
        return self


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
