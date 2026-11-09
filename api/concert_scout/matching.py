"""Steps 4 and 5: score Concerts against a Taste and keep the best. No network calls."""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from concert_scout.aliases import music_tag
from concert_scout.models import Artist, Concert, SeedArtist
from concert_scout.names import normalize

# Starting values, for the evals to tune. See docs/specs/02-search-pipeline.md.
SEED_WEIGHT = 1.0
ONE_HOP_WEIGHT = 0.8
TWO_HOP_WEIGHT = 0.5
TAGS_WEIGHT = 0.6
GENRE_WEIGHT = 0.15
NARROW_GENRE_WEIGHT = 0.3
NARROW_GENRE_ARTISTS = 30
SHORTLIST_SIZE = 40

ERA_TAG = re.compile(r"\d{2,4}s?( music)?|(19|20)\d\d.*|(fif|six|seven|eigh|nine)ties")
BLOCKED_TAGS = {
    "gen z",
    "seen live",
    "top 100",
    "queer",
    "female vocals",
    "male vocals",
    "american",
    "australian",
    "belgian",
    "brazilian",
    "british",
    "canadian",
    "dutch",
    "english",
    "french",
    "german",
    "irish",
    "italian",
    "japanese",
    "korean",
    "mexican",
    "norwegian",
    "scottish",
    "spanish",
    "swedish",
    "uk",
    "united kingdom",
    "united states",
    "usa",
    "welsh",
}

type Signal = Literal["seed", "one_hop", "two_hops", "tags", "genre"]


@dataclass(frozen=True)
class Neighbour:
    """An Artist near a seed. `closeness` runs from 0 to 1, the closest neighbour being 1."""

    name: str
    mbid: str | None
    hops: Literal[1, 2]
    closeness: float
    seed: str


@dataclass(frozen=True)
class Taste:
    seeds: Sequence[SeedArtist]
    neighbours: Sequence[Neighbour]
    tags: Sequence[str]
    # Ticketmaster's broad genres, so a style with no tagged Artists still reaches its neighbours.
    genres: Sequence[str] = ()

    def __bool__(self) -> bool:
        return bool(self.seeds or self.tags)


class Match(BaseModel):
    """Why a Concert scored. `via` names the seed behind the signal, when there is one.

    `score` is the best signal alone. `support` adds up every signal the Artist has, to order ties.
    """

    artist: str
    signal: Signal
    score: float
    support: float = 0
    via: str | None = None
    # The shared tags or genre behind a tag or genre signal, strongest first.
    styles: list[str] = []


class Candidate(BaseModel):
    concert: Concert
    match: Match | None = None


def usable_tags(tags: Iterable[str]) -> set[str]:
    """Tags that describe a sound. Era and demographic tags pull in Artists who only share those."""
    clean = {music_tag(tag) for tag in tags}
    return {tag for tag in clean if tag not in BLOCKED_TAGS and not ERA_TAG.fullmatch(tag)}


def score_concerts(
    concerts: Sequence[Concert], taste: Taste, artist_tags: Mapping[str, Sequence[str]]
) -> list[Candidate]:
    """Each Concert with the best match in its Lineup, keeping the order they came in."""
    lineups = [artist for concert in concerts for artist in concert.artists]
    tags = {a.mbid: usable_tags(artist_tags.get(a.mbid, [])) for a in lineups if a.mbid}
    known = _known_artists(taste)
    weights = _tag_weights(tags)
    tag_sets = _tag_sets(taste, weights)
    genres = _wanted_genres(lineups, taste, known)
    sizes = Counter(a.subgenre for a in {_key(a): a for a in lineups}.values() if a.subgenre)

    def best(artist: Artist) -> Match | None:
        options = [
            _known_match(artist, known),
            _tag_match(artist, tags.get(artist.mbid or "", set()), tag_sets, weights),
            _genre_match(artist, genres, sizes),
        ]
        matches = [m for m in options if m]
        top = max(matches, key=lambda m: m.score, default=None)
        return top and top.model_copy(update={"support": sum(m.score for m in matches)})

    def candidate(concert: Concert) -> Candidate:
        matches = (m for m in map(best, concert.artists) if m)
        return Candidate(concert=concert, match=max(matches, key=_rank, default=None))

    return [candidate(concert) for concert in concerts]


def shortlist(candidates: Sequence[Candidate]) -> list[Candidate]:
    """The top Concerts by score. Ties keep their order, so with no Taste the soonest stay first."""
    ranked = sorted(candidates, key=lambda c: _rank(c.match), reverse=True)
    return ranked[:SHORTLIST_SIZE]


def notable(concerts: Sequence[Concert]) -> list[Candidate]:
    """What to show with no Taste: Concerts headlined by an Artist Ticketmaster links to
    MusicBrainz, which leaves out most unbilled bar listings. One per headliner, order kept.
    """
    firsts: dict[str, Concert] = {}
    for concert in concerts:
        if concert.artists:
            artist = concert.artists[0]
            if artist.mbid or artist.source_id:
                firsts.setdefault(normalize(artist.name), concert)
    return [Candidate(concert=concert) for concert in list(firsts.values())[:SHORTLIST_SIZE]]


def candidate_names(candidates: Sequence[Candidate]) -> list[str]:
    """Who the shortlist is about, once each, falling back on the Concert's own name."""
    names = (
        c.match.artist
        if c.match
        else c.concert.artists[0].name
        if c.concert.artists
        else c.concert.name
        for c in candidates
    )
    return list(dict.fromkeys(names))


def _rank(match: Match | None) -> tuple[float, float]:
    return (match.score, match.support) if match else (0, 0)


def _key(artist: Artist) -> str:
    return artist.mbid or normalize(artist.name)


def _known_artists(taste: Taste) -> dict[str, Match]:
    """The seeds and their neighbours, under both ID and normalized name, best score kept.

    Listening counts fall off fast, so one hop takes a square root to keep good neighbours in
    range. A lone two-hop path is often noise, so two hops add up every path to the Artist.
    """
    known: dict[str, Match] = {}

    def keep(mbid: str | None, match: Match) -> None:
        for key in (mbid, normalize(match.artist)):
            if key and (key not in known or known[key].score < match.score):
                known[key] = match

    paths: defaultdict[str, list[Neighbour]] = defaultdict(list)
    for seed in taste.seeds:
        keep(seed.mbid, Match(artist=seed.name, signal="seed", score=SEED_WEIGHT, via=seed.name))
    for neighbour in taste.neighbours:
        if neighbour.hops == 1:
            score = ONE_HOP_WEIGHT * math.sqrt(neighbour.closeness)
            match = Match(artist=neighbour.name, signal="one_hop", score=score, via=neighbour.seed)
            keep(neighbour.mbid, match)
        else:
            paths[neighbour.mbid or normalize(neighbour.name)].append(neighbour)
    for group in paths.values():
        strongest = max(group, key=lambda n: n.closeness)
        score = TWO_HOP_WEIGHT * min(1, sum(n.closeness for n in group))
        match = Match(artist=strongest.name, signal="two_hops", score=score, via=strongest.seed)
        keep(strongest.mbid, match)
    return known


def _known_match(artist: Artist, known: Mapping[str, Match]) -> Match | None:
    # ID first: a name can belong to two Artists, so it only counts when the ID has nothing.
    match = (artist.mbid and known.get(artist.mbid)) or known.get(normalize(artist.name))
    return match.model_copy(update={"artist": artist.name}) if match else None


def _tag_weights(tags: Mapping[str, set[str]]) -> dict[str, float]:
    """A tag's rarity in the pool: near 0 for a tag on everyone, 1 for a tag on one Artist."""
    counts = Counter(tag for artist_tags in tags.values() for tag in artist_tags)
    if len(tags) < 2:
        return dict.fromkeys(counts, 1.0)
    return {tag: 1 - math.log(n) / math.log(len(tags)) for tag, n in counts.items()}


def _tag_sets(taste: Taste, weights: Mapping[str, float]) -> list[tuple[str | None, set[str]]]:
    """What each seed and the Search's own tags ask for. A tag absent from the pool can't help."""
    sets: list[tuple[str | None, set[str]]]
    sets = [(seed.name, usable_tags(seed.tags)) for seed in taste.seeds]
    sets.append((None, usable_tags(taste.tags)))
    return [(via, tags & weights.keys()) for via, tags in sets]


def _tag_match(
    artist: Artist,
    tags: set[str],
    tag_sets: Sequence[tuple[str | None, set[str]]],
    weights: Mapping[str, float],
) -> Match | None:
    best: Match | None = None
    for via, wanted in tag_sets:
        shared = tags & wanted
        if not shared:
            continue
        # How much of the Taste is met, discounted by how much the rarest shared tag says at all.
        total = sum(weights[tag] for tag in wanted) or 1
        met = sum(weights[tag] for tag in shared) / total
        score = TAGS_WEIGHT * met * max(weights[tag] for tag in shared)
        if score > 0 and (best is None or score > best.score):
            styles = sorted(shared, key=lambda tag: weights[tag], reverse=True)
            best = Match(artist=artist.name, signal="tags", score=score, via=via, styles=styles)
    return best


def _wanted_genres(lineups: Sequence[Artist], taste: Taste, known: Mapping[str, Match]) -> set[str]:
    """Genres named by the Taste's tags or reported for a seed playing in the pool."""
    seeds = [a for a in lineups if (m := _known_match(a, known)) and m.signal == "seed"]
    reported = {genre for a in seeds for genre in (a.genre, a.subgenre) if genre}
    tags = [tag for seed in taste.seeds for tag in seed.tags] + list(taste.tags)
    return {name.casefold() for name in reported} | usable_tags([*tags, *taste.genres])


def _genre_match(artist: Artist, genres: set[str], sizes: Mapping[str, int]) -> Match | None:
    if artist.subgenre and music_tag(artist.subgenre) in genres:
        narrow = sizes[artist.subgenre] < NARROW_GENRE_ARTISTS
        score = NARROW_GENRE_WEIGHT if narrow else GENRE_WEIGHT
        style = music_tag(artist.subgenre)
        return Match(artist=artist.name, signal="genre", score=score, styles=[style])
    if artist.genre and music_tag(artist.genre) in genres:
        style = music_tag(artist.genre)
        return Match(artist=artist.name, signal="genre", score=GENRE_WEIGHT, styles=[style])
    return None
