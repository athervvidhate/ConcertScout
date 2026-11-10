"""A festival keeps its own name, and names the Artists in its Lineup who suit the Search."""

from typing import Any

from concert_scout import assemble, matching, ranker
from concert_scout.matching import Neighbour, Taste
from concert_scout.models import Artist, Concert, SeedArtist
from concert_scout.sources.ticketmaster import parse_concert

SEED = SeedArtist(name="Calvin Harris", mbid="calvin", tags=["house"])


def attraction(name: str, kind: str = "Individual", *, linked: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"name": name, "classifications": [{"type": {"name": kind}}]}
    if linked:
        record["externalLinks"] = {"musicbrainz": [{"id": f"mb-{name}"}]}
    return record


def event(title: str, *attractions: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": title,
        "name": title,
        "url": "https://tickets.example/one",
        "dates": {"start": {}},
        "_embedded": {"attractions": list(attractions)},
    }


def lineup(count: int) -> list[dict[str, Any]]:
    return [attraction(f"DJ {n}") for n in range(count)]


def test_an_untyped_entry_named_like_a_festival_leaves_its_lineup() -> None:
    record = event(
        "Insomniac Countdown", attraction("Insomniac Countdown", "Undefined"), *lineup(5)
    )

    concert = parse_concert(record)

    assert concert.festival
    assert concert.name == "Insomniac Countdown"
    assert [a.name for a in concert.artists] == [f"DJ {n}" for n in range(5)]


def test_an_event_style_entry_leaves_its_lineup_under_a_longer_title() -> None:
    record = event(
        "Vans Warped Tour Orlando", attraction("Vans Warped Tour", "Event Style"), *lineup(4)
    )

    assert parse_concert(record).festival


def test_a_headliner_whose_tour_has_their_name_stays_an_artist() -> None:
    # Ticketmaster leaves many small-room headliners untyped and unlinked, and types a few as
    # Event Style, so a short bill is never read as a festival.
    record = event("Slayer: Reign In Blood", attraction("Slayer", "Undefined"), *lineup(3))
    typed = event(
        "Frank Turner: Last Evenings", attraction("Frank Turner", "Event Style"), *lineup(2)
    )

    assert not parse_concert(record).festival
    assert not parse_concert(typed).festival
    assert parse_concert(record).artists[0].name == "Slayer"
    assert parse_concert(typed).artists[0].name == "Frank Turner"


def test_a_linked_artist_is_never_a_festival_brand() -> None:
    record = event("THROWN", attraction("THROWN", "Event Style", linked=True), *lineup(5))

    assert not parse_concert(record).festival


def test_a_festival_billed_alone_keeps_its_one_entry() -> None:
    concert = parse_concert(event("Coachella", attraction("Coachella", "Event Style")))

    assert not concert.festival
    assert [a.name for a in concert.artists] == ["Coachella"]


def festival(*artists: Artist, id: str = "countdown") -> Concert:
    return Concert(
        id=id,
        name="Insomniac Countdown",
        url="https://tickets.example/countdown",
        artists=list(artists),
        festival=True,
    )


TASTE = Taste(
    [SEED],
    [
        Neighbour(name="Alesso", mbid="alesso", hops=1, closeness=1, seed=SEED.name),
        Neighbour(name="DJ Snake", mbid="snake", hops=2, closeness=0.5, seed=SEED.name),
    ],
    [],
)


def test_a_festival_names_its_lineup_by_similarity_best_first() -> None:
    concert = festival(
        Artist(name="33 Below"),
        Artist(name="DJ Snake", mbid="snake"),
        Artist(name="Alesso", mbid="alesso"),
    )

    candidate = matching.score_concerts([concert], TASTE, {})[0]

    assert candidate.lineup_match == ["Alesso", "DJ Snake"]
    assert candidate.match is not None
    assert candidate.match.artist == "Alesso"


def test_a_broad_shared_tag_names_no_one_on_a_festival() -> None:
    tags = {"calvin": ["house"], "wax": ["house"], "other": ["metal"]}
    concert = festival(Artist(name="Wax Motif", mbid="wax"))
    pool = [
        concert,
        *(
            Concert(id=f"c{n}", name="x", url="u", artists=[Artist(name=f"H{n}", mbid=f"h{n}")])
            for n in range(20)
        ),
    ]
    tags |= {f"h{n}": ["house"] for n in range(20)}

    candidate = matching.score_concerts(pool, TASTE, tags)[0]

    assert candidate.lineup_match == []


def test_a_regular_concert_names_no_lineup_match() -> None:
    concert = Concert(
        id="show",
        name="Alesso with DJ Snake",
        url="u",
        artists=[Artist(name="Alesso", mbid="alesso"), Artist(name="DJ Snake", mbid="snake")],
    )

    assert matching.score_concerts([concert], TASTE, {})[0].lineup_match == []


def test_a_festival_stacks_apart_from_its_artists_own_concerts() -> None:
    countdown = festival(Artist(name="Alesso", mbid="alesso"))
    own = Concert(id="club", name="Alesso", url="u", artists=[Artist(name="Alesso", mbid="alesso")])
    shortlist = matching.score_concerts([countdown, own], TASTE, {})

    rows = ranker.rows(shortlist, {})
    poster = assemble.from_levels({"countdown": 3, "club": 3}, shortlist)

    assert set(rows) == {"countdown", "club"}
    assert {r.concert.id for r in poster} == {"countdown", "club"}
    assert next(r for r in poster if r.concert.festival).lineup_match == ["Alesso"]


def _graded(id_: str, names: list[str], *, score: float = 0.5) -> matching.Candidate:
    concert = Concert(id=id_, name=id_, url="u", artists=[Artist(name=id_)], festival=bool(names))
    match = matching.Match(artist=id_, score=score, signal="one_hop")
    return matching.Candidate(concert=concert, match=match, lineup_match=names)


def test_several_matched_artists_lift_a_fair_festival_beside_a_strong_concert() -> None:
    single = _graded("single", [], score=0.9)
    fest = _graded("fest", ["A", "B", "C"], score=0.1)

    poster = assemble.from_levels({"single": 3, "fest": 2}, [single, fest])

    assert [r.concert.id for r in poster] == ["fest", "single"]


def test_a_festival_with_few_matches_keeps_its_own_level() -> None:
    single = _graded("single", [], score=0.9)
    fest = _graded("fest", ["A", "B"], score=0.1)

    poster = assemble.from_levels({"single": 3, "fest": 2}, [single, fest])

    assert [r.concert.id for r in poster] == ["single", "fest"]


def test_the_lift_never_rescues_a_stretch() -> None:
    fest = _graded("fest", ["A", "B", "C", "D"])

    assert assemble.from_levels({"fest": 1}, [fest]) == []
