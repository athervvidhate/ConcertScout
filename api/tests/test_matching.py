from pathlib import Path
from typing import Any

import pytest

from concert_scout import matching
from concert_scout.matching import Candidate, Match, Neighbour, Taste
from concert_scout.models import Artist, Concert, SeedArtist

SEED = SeedArtist(name="Tyler Childers", mbid="tyler", tags=["americana", "alternative country"])


def concert(id: str, *artists: Artist) -> Concert:
    return Concert(id=id, name=f"Concert {id}", url="https://example.com", artists=list(artists))


def neighbour(name: str, hops: Any, closeness: float, mbid: str | None = None) -> Neighbour:
    return Neighbour(name=name, mbid=mbid, hops=hops, closeness=closeness, seed=SEED.name)


def only_match(
    artist: Artist,
    taste: Taste,
    tags: dict[str, list[str]] | None = None,
    pool: tuple[Concert, ...] = (),
) -> Match | None:
    concerts = [concert("wanted", artist), *pool]
    return matching.score_concerts(concerts, taste, tags or {})[0].match


def test_a_seed_scores_highest_by_id_even_under_another_name() -> None:
    match = only_match(Artist(name="T. Childers", mbid="tyler"), Taste([SEED], [], []))

    assert match is not None
    assert (match.signal, match.score, match.artist) == ("seed", 1.0, "T. Childers")


def test_a_seed_with_no_id_in_the_pool_joins_by_normalized_name() -> None:
    match = only_match(Artist(name="TYLER CHILDERS"), Taste([SEED], [], []))

    assert match is not None
    assert match.signal == "seed"


def test_an_id_beats_a_name_shared_with_a_different_artist() -> None:
    taste = Taste([], [neighbour("Wednesday", 1, 1.0, mbid="the-band")], [])

    match = only_match(Artist(name="Wednesday", mbid="the-band"), taste)
    assert match is not None
    assert match.score == matching.ONE_HOP_WEIGHT


def test_one_hop_outranks_two_hops_at_full_closeness() -> None:
    taste = Taste([], [neighbour("Near", 1, 1.0), neighbour("Far", 2, 1.0)], [])
    near = only_match(Artist(name="Near"), taste)
    far = only_match(Artist(name="Far"), taste)

    assert near is not None and far is not None
    assert (near.score, far.score) == (matching.ONE_HOP_WEIGHT, matching.TWO_HOP_WEIGHT)


def test_one_hop_shrinks_with_distance_on_a_root_scale() -> None:
    match = only_match(Artist(name="Near"), Taste([], [neighbour("Near", 1, 0.25)], []))

    assert match is not None
    assert match.score == pytest.approx(matching.ONE_HOP_WEIGHT * 0.5)  # pyright: ignore[reportUnknownMemberType]


def test_many_two_hop_paths_beat_one_stronger_path() -> None:
    paths = [neighbour("Hiss Golden Messenger", 2, 0.2) for _ in range(4)]
    taste = Taste([], [*paths, neighbour("Kim Petras", 2, 0.3)], [])
    many = only_match(Artist(name="Hiss Golden Messenger"), taste)
    lone = only_match(Artist(name="Kim Petras"), taste)

    assert many is not None and lone is not None
    assert many.score > lone.score


def test_two_hop_paths_never_pass_the_base_weight() -> None:
    taste = Taste([], [neighbour("Far", 2, 0.9) for _ in range(5)], [])
    match = only_match(Artist(name="Far"), taste)

    assert match is not None
    assert match.score == matching.TWO_HOP_WEIGHT


def test_an_artist_gets_the_best_signal_it_qualifies_for() -> None:
    taste = Taste([SEED], [neighbour("Near", 1, 1.0, mbid="near")], [])
    tags = {"near": ["americana"]}

    match = only_match(Artist(name="Near", mbid="near"), taste, tags)
    assert match is not None
    assert match.signal == "one_hop"


def test_a_festival_scores_by_the_best_match_in_its_lineup() -> None:
    festival = concert("f", Artist(name="Nobody"), Artist(name="Tyler Childers", mbid="tyler"))

    candidate = matching.score_concerts([festival], Taste([SEED], [], []), {})[0]

    assert candidate.match is not None
    assert candidate.match.artist == "Tyler Childers"


def tagged(mbid: str) -> Artist:
    return Artist(name=mbid, mbid=mbid)


def test_rare_shared_tags_score_far_above_a_common_one() -> None:
    seed = SeedArtist(name="Seed", tags=["shoegaze", "pop"])
    tags = {f"pop-{n}": ["pop"] for n in range(30)} | {"rare": ["shoegaze"]}
    pool = tuple(concert(mbid, tagged(mbid)) for mbid in tags)

    rare = only_match(tagged("rare"), Taste([seed], [], []), tags, pool)
    common = only_match(tagged("pop-0"), Taste([seed], [], []), tags, pool)

    assert rare is not None and common is not None
    assert (rare.signal, common.signal) == ("tags", "tags")
    assert rare.score > 10 * common.score
    assert rare.score <= matching.TAGS_WEIGHT


def test_a_tag_on_everyone_in_the_pool_scores_nothing() -> None:
    seed = SeedArtist(name="Seed", tags=["rock"])
    tags = {"a": ["rock"], "b": ["rock"]}

    candidates = matching.score_concerts(
        [concert("1", tagged("a")), concert("2", tagged("b"))], Taste([seed], [], []), tags
    )

    assert [c.match for c in candidates] == [None, None]


def test_the_searchs_own_tags_match_and_name_no_seed() -> None:
    tags = {"a": ["shoegaze"], "b": ["pop"]}
    pool = (concert("2", tagged("b")),)

    match = only_match(tagged("a"), Taste([], [], ["Shoegaze"]), tags, pool)

    assert match is not None
    assert (match.signal, match.via) == ("tags", None)


def test_each_seed_is_measured_against_its_own_tags() -> None:
    seeds = [SEED, SeedArtist(name="Four Tet", tags=["folktronica"])]
    tags = {"a": ["folktronica"], "b": ["pop"], "c": ["americana"]}
    pool = (concert("2", tagged("b")), concert("3", tagged("c")))

    match = only_match(tagged("a"), Taste(seeds, [], []), tags, pool)

    assert match is not None
    assert match.via == "Four Tet"


@pytest.mark.parametrize(
    "tag",
    [
        "gen z",
        "Gen-Z",
        "seen live",
        "2020s",
        "90s",
        "1990s",
        "80s music",
        "2008 universal fire victim",
        "nineties",
        "american",
        "British",
        "united states",
        "female vocals",
    ],
)
def test_era_and_demographic_tags_are_dropped(tag: str) -> None:
    assert matching.usable_tags([tag]) == set()


def test_tags_that_describe_a_sound_survive_and_share_one_spelling() -> None:
    assert matching.usable_tags(["Post-Punk", "post punk", "dream pop"]) == {
        "post punk",
        "dream pop",
    }


def test_a_blocked_tag_cannot_match_two_artists() -> None:
    seed = SeedArtist(name="Clairo", tags=["gen z", "2020s"])
    tags = {"glorilla": ["gen z", "2020s"], "b": ["pop"]}
    pool = (concert("2", tagged("b")),)

    assert only_match(tagged("glorilla"), Taste([seed], [], []), tags, pool) is None


def artists_in_subgenre(count: int, subgenre: str) -> tuple[Concert, ...]:
    return tuple(
        concert(str(n), Artist(name=f"{subgenre} {n}", genre="Rock", subgenre=subgenre))
        for n in range(count)
    )


def test_a_narrow_subgenre_counts_for_more_than_a_broad_one() -> None:
    narrow = Artist(name="Drug Church", genre="Rock", subgenre="Punk")
    broad = Artist(name="Styx", genre="Rock", subgenre="Pop")
    taste = Taste([], [], ["punk", "pop"])
    pool = artists_in_subgenre(matching.NARROW_GENRE_ARTISTS, "Pop")

    narrow_match = only_match(narrow, taste, pool=pool)
    broad_match = only_match(broad, taste, pool=pool)

    assert narrow_match is not None and broad_match is not None
    assert (narrow_match.signal, narrow_match.score) == ("genre", matching.NARROW_GENRE_WEIGHT)
    assert (broad_match.signal, broad_match.score) == ("genre", matching.GENRE_WEIGHT)


def test_the_top_level_genre_is_only_ever_weak() -> None:
    match = only_match(Artist(name="Styx", genre="Rock", subgenre="Pop"), Taste([], [], ["rock"]))

    assert match is not None
    assert match.score == matching.GENRE_WEIGHT


def test_a_seed_playing_in_the_pool_lends_its_ticketmaster_genre() -> None:
    seed_in_pool = concert("s", Artist(name="Tyler Childers", genre="Country", subgenre="Folk"))
    artist = Artist(name="Another", genre="Blues", subgenre="Folk")

    match = only_match(
        artist, Taste([SeedArtist(name="Tyler Childers")], [], []), None, (seed_in_pool,)
    )

    assert match is not None
    assert match.signal == "genre"


def test_no_taste_scores_nothing_and_keeps_the_order() -> None:
    concerts = [concert(str(n), Artist(name=f"A{n}")) for n in range(3)]

    candidates = matching.score_concerts(concerts, Taste([], [], []), {})

    assert [c.match for c in candidates] == [None, None, None]
    assert [c.concert.id for c in matching.shortlist(candidates)] == ["0", "1", "2"]


def scored(id: str, score: float, support: float = 0) -> Candidate:
    match = Match(artist=id, signal="tags", score=score, support=support)
    return Candidate(concert=concert(id, Artist(name=id)), match=match)


def test_the_shortlist_keeps_the_top_sixty_by_score() -> None:
    candidates = [scored(str(n), n / 100) for n in range(90)]

    picked = matching.shortlist(candidates)

    assert len(picked) == matching.SHORTLIST_SIZE == 60
    assert picked[0].concert.id == "89"
    assert picked[-1].concert.id == "30"


def test_ties_go_to_the_artist_with_more_supporting_signals_then_the_soonest() -> None:
    candidates = [
        scored("first", 0.15, 0.15),
        scored("second", 0.15, 0.15),
        scored("more", 0.15, 0.2),
    ]

    assert [c.concert.id for c in matching.shortlist(candidates)] == ["more", "first", "second"]


def test_a_taste_ranks_matches_above_concerts_with_no_signal() -> None:
    candidates = [Candidate(concert=concert("none")), scored("match", 0.1)]

    assert [c.concert.id for c in matching.shortlist(candidates)] == ["match", "none"]


def test_candidate_names_use_the_matched_artist_once_then_the_lineup_then_the_concert() -> None:
    tyler = concert("1", Artist(name="Opener"), Artist(name="Tyler Childers"))
    candidates = [
        Candidate(concert=tyler, match=Match(artist="Tyler Childers", signal="seed", score=1)),
        Candidate(concert=tyler, match=Match(artist="Tyler Childers", signal="seed", score=1)),
        Candidate(concert=concert("2", Artist(name="Unmatched"))),
        Candidate(concert=concert("3")),
    ]

    assert matching.candidate_names(candidates) == ["Tyler Childers", "Unmatched", "Concert 3"]


def test_matching_imports_nothing_that_can_reach_a_network() -> None:
    source = Path(matching.__file__).read_text(encoding="utf-8")

    assert "import httpx" not in source
    assert "redis" not in source
    assert "sources" not in source


@pytest.mark.parametrize(
    ("typed", "reported"),
    [("UKG", "uk garage"), ("DnB", "drum & bass"), ("RnB", "rhythm and blues")],
)
def test_genre_aliases_match_source_tags(typed: str, reported: str) -> None:
    match = only_match(
        tagged("a"),
        Taste([], [], [typed]),
        {"a": [reported], "b": ["rock"]},
        (concert("b", tagged("b")),),
    )
    assert match is not None and match.signal == "tags"
