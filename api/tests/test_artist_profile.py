from concert_scout.sources import lastfm, spotify_catalog

INFO = {
    "artist": {
        "name": "Son Volt",
        "url": "https://www.last.fm/music/Son+Volt",
        "stats": {"listeners": "412000", "playcount": "1"},
        "bio": {"summary": 'An American band. <a href="https://www.last.fm">Read more</a>'},
        "tags": {"tag": [{"name": "alt-country"}, {"name": "americana"}]},
        "similar": {"artist": [{"name": "Uncle Tupelo"}]},
    }
}
TRACKS = {"toptracks": {"track": [{"name": "Windfall", "url": "https://www.last.fm/w"}]}}


def test_profile_keeps_source_facts_and_drops_the_read_more_link() -> None:
    profile = lastfm.parse_profile("Son Volt", INFO, TRACKS)
    assert profile.listeners == 412000
    assert profile.bio == "An American band."
    assert profile.tags == ["alt-country", "americana"]
    assert profile.similar == ["Uncle Tupelo"]
    assert profile.top_tracks[0].name == "Windfall"


def test_an_unknown_artist_has_an_empty_profile() -> None:
    profile = lastfm.parse_profile("Nobody", {"error": 6}, {"error": 6})
    assert profile.model_dump(exclude_defaults=True) == {"name": "Nobody"}


def test_a_missing_listener_count_stays_missing() -> None:
    profile = lastfm.parse_profile("Son Volt", {"artist": {"url": "x"}}, {})
    assert profile.listeners is None and profile.bio is None


def test_only_an_exact_name_earns_a_spotify_link() -> None:
    def record(name: str) -> dict[str, object]:
        return {"name": name, "external_urls": {"spotify": f"https://open.spotify.com/{name}"}}

    body = {"artists": {"items": [record("Whiskey Myers"), record("49 WINCHESTER")]}}
    assert spotify_catalog.exact_page("49 Winchester", body) == (
        "https://open.spotify.com/49 WINCHESTER"
    )
    assert spotify_catalog.exact_page("Timothy Wayne", body) is None
