"""Watch Live contracts: the curated index, the peak moment finder, the cache and the routes."""

import datetime as dt
import logging
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from concert_scout import cache, limits, live_index
from concert_scout.app import create_app
from concert_scout.sources import lastfm, live_clips, setlistfm, youtube
from concert_scout.sources.live_clips import Chapter, Comment
from tests.contracts import contract_model, forbidden_http, install_sources, settings_with

API_KEY = "youtube-secret-api-key-12345"
CRON = "cron-secret"
SERIES = {series.name: series for series in live_index.SERIES}


@pytest.fixture(autouse=True)
def sources(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch)


def stamp(text: str) -> int:
    match = live_clips.STAMP.search(text)
    assert match
    start = live_clips.seconds_of(match)
    assert start is not None
    return start


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("0:15", 15), ("4:12", 252), ("04:12", 252), ("1:02:03", 3723), ("59:59", 3599)],
)
def test_a_stamp_is_minutes_and_seconds_or_hours(text: str, seconds: int) -> None:
    assert stamp(text) == seconds


@pytest.mark.parametrize("text", ["4:75", "75:10", "1:75:10", "12:345", "ratio 3:2", "v1.2.3"])
def test_what_is_not_a_stamp_is_not_read_as_one(text: str) -> None:
    match = live_clips.STAMP.search(text)
    assert match is None or live_clips.seconds_of(match) is None


def test_chapters_are_the_lines_that_open_with_a_stamp() -> None:
    description = "\n".join(
        [
            "Recorded live in 2025. Follow us for more.",
            "0:00 Intro",
            "1:15 - Maria Tambien",
            "[4:12] Time (You and I)",
            "• 1:02:03: Evaluation",
            "Directed by Someone at 12:00 pm",
            "5:99 Not a time",
            "6:00",
        ]
    )
    assert live_clips.chapters(description) == [
        Chapter(start=0, title="Intro"),
        Chapter(start=75, title="Maria Tambien"),
        Chapter(start=252, title="Time (You and I)"),
        Chapter(start=3723, title="Evaluation"),
    ]


CHAPTERS = [
    Chapter(start=0, title="Intro"),
    Chapter(start=75, title="Maria Tambien (Live)"),
    Chapter(start=252, title="Time You and I"),
    Chapter(start=700, title="Sometimes"),
]


def test_the_chapter_of_the_best_known_track_wins() -> None:
    tracks = ["Evaluation", "Time (You and I)", "Maria Tambien"]
    assert live_clips.chapter_start(CHAPTERS, tracks, 900) == 252
    assert live_clips.chapter_start(CHAPTERS, ["Maria Tambien"], 900) == 75


def test_a_track_must_match_whole_words_of_a_chapter() -> None:
    assert live_clips.chapter_start(CHAPTERS, ["Time"], 900) == 252
    assert live_clips.chapter_start(CHAPTERS[:1] + CHAPTERS[3:], ["Time"], 900) is None


def test_a_chapter_with_no_show_left_is_not_a_peak() -> None:
    assert live_clips.chapter_start(CHAPTERS, ["Sometimes"], 710) is None
    assert live_clips.chapter_start(CHAPTERS, ["Sometimes"], 730) == 700
    assert live_clips.chapter_start(CHAPTERS, [], 900) is None


def comment(text: str, likes: int) -> Comment:
    return Comment(text=text, likes=likes)


def test_the_most_liked_comment_stamp_is_the_peak() -> None:
    comments = [
        comment("amazing 2:10 is the drop", 40),
        comment("4:12 THE SOLO", 310),
        comment("love this", 900),
        comment("1:05", 20),
    ]
    assert live_clips.comment_start(comments, 600) == 252


@pytest.mark.parametrize(
    ("text", "likes"),
    [
        ("0:10 the count in", 500),
        ("9:50 the last note", 500),
        ("check out my mix https://example.com 4:12", 500),
        ("buy followers www.spam 4:12", 500),
        ("1:00 2:00 3:00 4:00 tracklist", 500),
        ("4:12 only my friend liked this", 2),
    ],
)
def test_a_comment_outside_the_show_or_a_spammer_or_a_tracklist_is_skipped(
    text: str, likes: int
) -> None:
    assert live_clips.comment_start([comment(text, likes)], 600) is None


def test_a_comment_with_its_first_stamp_out_of_range_uses_the_next_valid_one() -> None:
    assert live_clips.comment_start([comment("0:05 count in, 3:30 the peak", 50)], 600) == 210


@pytest.mark.parametrize(
    ("duration", "start"),
    [(200, 0), (600, 0), (601, 120), (900, 180), (3600, 180), (0, 0)],
)
def test_the_fallback_skips_a_whole_sets_intro_and_starts_a_song_at_its_start(
    duration: int, start: int
) -> None:
    assert live_clips.intro_start(duration) == start


@pytest.mark.parametrize(
    ("series", "title", "artist", "whole"),
    [
        ("Tiny Desk Concert", "Mike D: Tiny Desk Concert", "Mike D", True),
        ("Tiny Desk Concert", "Khruangbin: Tiny Desk (Home) Concert", "Khruangbin", True),
        ("Tiny Desk Concert", "What sets these nominations for the Latin Grammys apart", None, 0),
        ("KEXP", "SLIFT - Full Performance (Live on KEXP)", "SLIFT", True),
        ("KEXP", "SLIFT - The Story (Live on KEXP)", "SLIFT", False),
        ("KEXP", 'SLIFT performs "Fantasia" & more Live on KEXP', None, 0),
        ("Boiler Room", "Makoto | Boiler Room: Osaka", "Makoto", True),
        (
            "Boiler Room",
            "MSBHVR & Avocado Man | Boiler Room Lamu: MAJI",
            "MSBHVR & Avocado Man",
            True,
        ),
        ("Cercle", "Rival Consoles - Live from Somewhere | Cercle", "Rival Consoles", True),
        ("Cercle", "Fred again.. @ Louvre | Cercle", "Fred again..", True),
        ("Cercle", "@ANNAMUSIC performed Bloom live at Cercle Festival.", None, 0),
        ("Audiotree Live", "INOHA - Burden | Audiotree Live", "INOHA", False),
        ("Audiotree Live", "INOHA on Audiotree Live (Full Session)", "INOHA", True),
        ("Audiotree Live", "#AltRock INOHA on Audiotree Live - OUT NOW", None, 0),
        ("COLORS", "Milo J - Ama De Mi Sol | A COLORS SHOW", "Milo J", False),
        ("COLORS", "Milo J - Ama De Mi Sol | A COLORS MOMENT", None, 0),
        (
            "Radio 1 Live Lounge",
            "Rachel Chinouriri - Pretty Girls in the Radio 1 Live Lounge",
            "Rachel Chinouriri",
            False,
        ),
        ("Radio 1 Live Lounge", "Freya Skye tries to guess songs! | Speed Test", None, 0),
    ],
)
def test_a_sessions_title_names_its_artist(
    series: str, title: str, artist: str | None, whole: bool | int
) -> None:
    parsed = live_index.parse_session(SERIES[series], title)
    assert parsed == ((artist, bool(whole)) if artist else None)


def playlist_item(video_id: str, title: str) -> dict[str, Any]:
    return {"snippet": {"title": title, "resourceId": {"videoId": video_id}}}


def test_an_artists_whole_set_beats_a_single_song_and_the_first_listed_beats_a_later_one() -> None:
    kexp = SERIES["KEXP"]
    items = [
        playlist_item("song1", "SLIFT - The Story (Live on KEXP)"),
        playlist_item("full1", "SLIFT - Full Performance (Live on KEXP)"),
        playlist_item("song2", "SLIFT - The Village (Live on KEXP)"),
        playlist_item("old", "Slift - Full Performance (Live on KEXP)"),
        playlist_item("gone", "Private video"),
        {"snippet": {"title": "Slift - Broken (Live on KEXP)"}},
    ]
    found = live_index.index_videos(kexp, items)
    assert list(found) == ["slift"]
    assert found["slift"][0].video_id == "full1"
    assert found["slift"][0].session == "KEXP"


class Youtube:
    """The YouTube Data API as videos, comments and a search answer, with a record of calls."""

    def __init__(
        self,
        videos: dict[str, dict[str, Any]] | None = None,
        comments: dict[str, list[tuple[str, int]]] | None = None,
        search: list[tuple[str, str, str]] | None = None,
        playlists: dict[str, list[dict[str, Any]] | int] | None = None,
        failure: tuple[int, str] | None = None,
    ) -> None:
        self.videos = videos or {}
        self.comments = comments or {}
        self.search = search or []
        self.playlists = playlists or {}
        self.failure = failure
        self.calls: list[httpx.Request] = []

    def paths(self) -> list[str]:
        return [call.url.path.removeprefix("/youtube/v3") for call in self.calls]

    def params(self, path: str) -> dict[str, str]:
        [call] = [c for c in self.calls if c.url.path.endswith(path)]
        return dict(call.url.params)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.failure:
            status, reason = self.failure
            return httpx.Response(status, json={"error": {"errors": [{"reason": reason}]}})
        params = request.url.params
        path = request.url.path.removeprefix("/youtube/v3")
        if path == "/videos":
            ids = params["id"].split(",")
            return httpx.Response(
                200, json={"items": [{"id": i, **self.videos[i]} for i in ids if i in self.videos]}
            )
        if path == "/commentThreads":
            video = params["videoId"]
            if video not in self.comments:
                body = {"error": {"code": 403, "errors": [{"reason": "commentsDisabled"}]}}
                return httpx.Response(403, json=body)
            threads = [
                {"snippet": {"topLevelComment": {"snippet": {"textDisplay": t, "likeCount": n}}}}
                for t, n in self.comments[video]
            ]
            return httpx.Response(200, json={"items": threads})
        if path == "/search":
            items = [
                {"id": {"videoId": i}, "snippet": {"title": t, "channelTitle": c}}
                for i, t, c in self.search
            ]
            return httpx.Response(200, json={"items": items})
        if path == "/playlistItems":
            playlist = self.playlists.get(params["playlistId"], [])
            if isinstance(playlist, int):
                return httpx.Response(playlist, json={"error": {"errors": [{"reason": "x"}]}})
            return httpx.Response(200, json={"items": playlist})
        raise AssertionError(f"Unexpected YouTube call: {path}")

    def client(self) -> httpx.AsyncClient:
        return youtube.make_client(API_KEY, httpx.MockTransport(self.handle))


def video(
    duration: str = "PT15M", description: str = "", embeddable: bool = True, privacy: str = "public"
) -> dict[str, Any]:
    return {
        "snippet": {"description": description},
        "contentDetails": {"duration": duration},
        "status": {"embeddable": embeddable, "privacyStatus": privacy},
    }


def lastfm_tracks(names: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["method"] == "artist.getTopTracks":
            tracks = [{"name": n, "url": f"https://www.last.fm/{n}"} for n in names]
            return httpx.Response(200, json={"toptracks": {"track": tracks}})
        return httpx.Response(200, json={"artist": {"url": "https://www.last.fm/music/x"}})

    return lastfm.make_client("key", httpx.MockTransport(handler))


def indexed(redis: FakeAsyncRedis, name: str, *videos: tuple[str, str, str]) -> Any:
    """Files videos, as `(id, title, series)`, in the curated index, as a sync would."""
    entries = live_index.IndexedVideos(
        videos=[live_clips.LiveVideo(video_id=i, title=t, session=s) for i, t, s in videos]
    )
    return redis.set(f"live:index:{name}", entries.model_dump_json())


async def test_sync_reads_each_channels_uploads_by_playlistitems_and_files_artists() -> None:
    desk, kexp, boiler = SERIES["Tiny Desk Concert"], SERIES["KEXP"], SERIES["Boiler Room"]
    api = Youtube(
        playlists={
            desk.uploads: [
                playlist_item("desk1", "Khruangbin: Tiny Desk Concert"),
                playlist_item("news", "Women dominate the Grammy nominations"),
            ],
            kexp.uploads: [
                playlist_item("kexp1", "Khruangbin - Full Performance (Live on KEXP)"),
                playlist_item("kexp2", "Bonobo - Kerala (Live on KEXP)"),
            ],
            boiler.uploads: 500,
        }
    )
    redis = FakeAsyncRedis()
    async with api.client() as client:
        steps = await live_index.sync(client, redis)

    assert {step.series: (step.videos, step.error) for step in steps} == {
        "Tiny Desk Concert": (1, None),
        "KEXP": (2, None),
        "Boiler Room": (0, "YouTubeError"),
        "Cercle": (0, None),
        "Audiotree Live": (0, None),
        "COLORS": (0, None),
        "Radio 1 Live Lounge": (0, None),
    }
    # Only playlistItems.list, one request a channel, and never search.list.
    assert set(api.paths()) == {"/playlistItems"}
    assert len(api.calls) == len(live_index.SERIES)
    sample = api.calls[0].url.params
    assert sample["part"] == "snippet" and sample["maxResults"] == "50"
    assert {call.url.params["playlistId"] for call in api.calls} == {
        series.uploads for series in live_index.SERIES
    }

    entries = await cache.read(redis, "live:index:khruangbin", live_index.IndexedVideos)
    assert entries
    # In the order of the spec's series, so a Ticket's clip prefers a Tiny Desk.
    assert [(v.video_id, v.session) for v in entries.videos] == [
        ("desk1", "Tiny Desk Concert"),
        ("kexp1", "KEXP"),
    ]
    assert 13 * 86400 < await redis.ttl("live:index:khruangbin") <= 14 * 86400
    assert await redis.exists("live:index:bonobo", "live:index:khruangbin") == 2
    assert not await redis.exists("live:index:the grammys")


def test_every_series_reads_a_distinct_uploads_playlist() -> None:
    assert len({series.channel_id for series in live_index.SERIES}) == 7
    assert SERIES["Tiny Desk Concert"].uploads == "UU4eYXhJI4-7wSWc8UNRwD4A"
    assert [series.name for series in live_index.SERIES] == [
        "Tiny Desk Concert",
        "KEXP",
        "Boiler Room",
        "Cercle",
        "Audiotree Live",
        "COLORS",
        "Radio 1 Live Lounge",
    ]


async def test_a_curated_artist_opens_at_the_stamp_of_its_most_liked_comment() -> None:
    api = Youtube(
        videos={"desk1": video("PT15M")},
        comments={"desk1": [("3:10 the whole room sings", 90), ("0:12 intro", 400)]},
    )
    redis = FakeAsyncRedis()
    await indexed(
        redis, "khruangbin", ("desk1", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert")
    )
    async with api.client() as client:
        clip = await live_index.find_clip(client, redis, "Khruangbin")

    assert clip == live_clips.LiveClip(
        video_id="desk1",
        title="Khruangbin: Tiny Desk Concert",
        session="Tiny Desk Concert",
        start=190,
    )
    # Two 1-unit calls and no search, which costs 100.
    assert api.paths() == ["/videos", "/commentThreads"]
    assert api.params("/videos")["part"] == "snippet,contentDetails,status"
    comments = api.params("/commentThreads")
    assert comments["order"] == "relevance" and comments["maxResults"] == "15"
    assert await redis.get(f"youtube:search:calls:{dt.datetime.now(dt.UTC).date()}") is None


async def test_a_chapter_of_a_top_track_beats_comments_and_costs_no_comment_call() -> None:
    description = "Setlist\n0:00 Intro\n2:30 Maria Tambien\n6:40 Evaluation\n"
    api = Youtube(
        videos={"desk1": video("PT15M", description)},
        comments={"desk1": [("9:00 amazing", 999)]},
    )
    redis = FakeAsyncRedis()
    await indexed(
        redis, "khruangbin", ("desk1", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert")
    )
    async with api.client() as client, lastfm_tracks(["Evaluation", "Maria Tambien"]) as lf:
        clip = await live_index.find_clip(client, redis, "Khruangbin", lastfm_client=lf)

    assert clip and clip.start == 400
    assert api.paths() == ["/videos"]


async def test_a_setlist_staple_is_matched_before_a_studio_track(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = setlistfm.SetlistSummary(
        artist="Khruangbin", staples=[setlistfm.SetlistStaple(name="Maria Tambien", shows=5)]
    )
    monkeypatch.setattr(setlistfm, "artist_setlist", AsyncMock(return_value=summary))
    description = "0:00 Intro\n2:30 Maria Tambien\n6:40 Evaluation\n"
    api = Youtube(videos={"desk1": video("PT15M", description)})
    redis = FakeAsyncRedis()
    await indexed(
        redis, "khruangbin", ("desk1", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert")
    )
    async with (
        api.client() as client,
        lastfm_tracks(["Evaluation"]) as lf,
        setlistfm.make_client("key") as setlist,
    ):
        clip = await live_index.find_clip(
            client, redis, "Khruangbin", lastfm_client=lf, setlistfm_client=setlist
        )
    assert clip and clip.start == 150


async def test_a_setlist_fm_failure_leaves_lastfm_to_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = AsyncMock(side_effect=setlistfm.SetlistfmError("status 500"))
    monkeypatch.setattr(setlistfm, "artist_setlist", failing)
    api = Youtube(videos={"desk1": video("PT15M", "0:00 Intro\n6:40 Evaluation\n")})
    redis = FakeAsyncRedis()
    await indexed(
        redis, "khruangbin", ("desk1", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert")
    )
    async with (
        api.client() as client,
        lastfm_tracks(["Evaluation"]) as lf,
        setlistfm.make_client("key") as setlist,
    ):
        clip = await live_index.find_clip(
            client, redis, "Khruangbin", lastfm_client=lf, setlistfm_client=setlist
        )
    assert clip and clip.start == 400


async def test_chapters_with_no_top_track_in_them_fall_through_to_comments() -> None:
    description = "0:00 Intro\n2:30 Some Other Song\n"
    api = Youtube(
        videos={"desk1": video("PT15M", description)},
        comments={"desk1": [("5:05 the peak", 20)]},
    )
    redis = FakeAsyncRedis()
    await indexed(
        redis, "khruangbin", ("desk1", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert")
    )
    async with api.client() as client, lastfm_tracks(["Evaluation"]) as lf:
        clip = await live_index.find_clip(client, redis, "Khruangbin", lastfm_client=lf)
    assert clip and clip.start == 305


@pytest.mark.parametrize(
    ("duration", "comments", "start"),
    [
        ("PT15M", [("nice one", 90)], 180),
        ("PT45M", [], 180),
        ("PT11M", [], 132),
        ("PT4M10S", [("0:05 first note", 90)], 0),
        ("P0D", [("2:00 live", 90)], 0),
    ],
)
async def test_with_no_chapter_or_comment_stamp_the_start_is_the_lengths(
    duration: str, comments: list[tuple[str, int]], start: int
) -> None:
    api = Youtube(videos={"v": video(duration)}, comments={"v": comments})
    redis = FakeAsyncRedis()
    await indexed(redis, "khruangbin", ("v", "Khruangbin - Live", "KEXP"))
    async with api.client() as client:
        clip = await live_index.find_clip(client, redis, "Khruangbin")
    assert clip and clip.start == start


async def test_a_video_with_comments_off_still_opens() -> None:
    api = Youtube(videos={"v": video("PT20M")})
    redis = FakeAsyncRedis()
    await indexed(redis, "khruangbin", ("v", "Khruangbin - Live", "KEXP"))
    async with api.client() as client:
        clip = await live_index.find_clip(client, redis, "Khruangbin")
    assert clip and clip.start == 180


async def test_the_next_embeddable_public_video_stands_in_for_one_that_cannot_play() -> None:
    api = Youtube(
        videos={
            "locked": video(embeddable=False),
            "private": video(privacy="private"),
            "ok": video("PT3M"),
        },
    )
    redis = FakeAsyncRedis()
    await indexed(
        redis,
        "khruangbin",
        ("locked", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert"),
        ("private", "Khruangbin - Full Performance (Live on KEXP)", "KEXP"),
        ("ok", "Khruangbin | Boiler Room: Osaka", "Boiler Room"),
    )
    async with api.client() as client:
        clip = await live_index.find_clip(client, redis, "Khruangbin")
    assert clip and (clip.video_id, clip.session, clip.start) == ("ok", "Boiler Room", 0)
    # One videos.list for all three candidates.
    assert api.paths() == ["/videos", "/commentThreads"]


async def test_a_clip_is_cached_for_30_days_and_asked_for_once() -> None:
    api = Youtube(videos={"v": video("PT3M")})
    redis = FakeAsyncRedis()
    await indexed(redis, "khruangbin", ("v", "Khruangbin - Live", "KEXP"))
    async with api.client() as client:
        first = await live_index.find_clip(client, redis, "Khruangbin")
        second = await live_index.find_clip(client, redis, "khruangbin")
    assert first == second and first is not None
    assert api.paths() == ["/videos", "/commentThreads"]
    assert 29 * 86400 < await redis.ttl("live:clip:khruangbin") <= 30 * 86400


async def test_an_artist_the_index_lacks_costs_one_search_and_a_miss_is_kept_14_days() -> None:
    api = Youtube()
    redis = FakeAsyncRedis()
    async with api.client() as client:
        assert await live_index.find_clip(client, redis, "Nobody Known") is None
        assert await live_index.find_clip(client, redis, "Nobody Known") is None
    assert api.paths() == ["/search"]
    params = api.params("/search")
    assert params["q"] == "Nobody Known live performance"
    assert params["videoEmbeddable"] == "true" and params["videoCategoryId"] == "10"
    assert params["type"] == "video"
    assert 13 * 86400 < await redis.ttl("live:clip:nobody known") <= 14 * 86400
    assert await redis.get("live:clip:nobody known") == b'{"clip":null}'


async def test_a_search_result_must_carry_the_artists_name_and_embeds_by_its_channel() -> None:
    api = Youtube(
        videos={"theirs": video("PT4M")},
        search=[
            ("other", "Someone Else - Live at the Fillmore", "Venue TV"),
            ("theirs", "Khruangbin: Live at Funkhaus Berlin", "Funkhaus"),
        ],
    )
    redis = FakeAsyncRedis()
    async with api.client() as client:
        clip = await live_index.find_clip(client, redis, "Khruangbin")
    assert clip == live_clips.LiveClip(
        video_id="theirs", title="Khruangbin: Live at Funkhaus Berlin", session="Funkhaus", start=0
    )
    assert api.paths() == ["/search", "/videos", "/commentThreads"]


async def test_an_indexed_artist_whose_videos_cannot_play_falls_back_to_a_search() -> None:
    api = Youtube(
        videos={"locked": video(embeddable=False), "found": video("PT4M")},
        search=[("found", "Khruangbin Live", "A Channel")],
    )
    redis = FakeAsyncRedis()
    await indexed(
        redis, "khruangbin", ("locked", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert")
    )
    async with api.client() as client:
        clip = await live_index.find_clip(client, redis, "Khruangbin")
    assert clip and clip.video_id == "found"


async def test_sixty_searches_a_day_then_none_and_a_limited_artist_is_not_cached_as_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert limits.YOUTUBE_SEARCHES_PER_DAY == 60
    monkeypatch.setattr(limits, "YOUTUBE_SEARCHES_PER_DAY", 2)
    api = Youtube()
    redis = FakeAsyncRedis()
    async with api.client() as client:
        await live_index.find_clip(client, redis, "One")
        await live_index.find_clip(client, redis, "Two")
        with pytest.raises(limits.DailyLimitReached):
            await live_index.find_clip(client, redis, "Three")
        # An Artist the index holds needs no search, so the limit does not touch it.
        await indexed(redis, "four", ("v", "Four - Live", "KEXP"))
        api.videos["v"] = video("PT3M")
        assert await live_index.find_clip(client, redis, "Four")
    assert api.paths().count("/search") == 2
    assert await redis.get("live:clip:three") is None


@pytest.mark.parametrize(
    ("status", "reason", "error"),
    [
        (403, "quotaExceeded", youtube.QuotaExceeded),
        (429, "rateLimitExceeded", youtube.QuotaExceeded),
        (403, "keyInvalid", youtube.YouTubeError),
        (500, "backendError", youtube.YouTubeError),
    ],
)
async def test_youtube_failures_raise_without_the_key_and_are_not_cached(
    status: int, reason: str, error: type[Exception]
) -> None:
    redis = FakeAsyncRedis()
    async with Youtube(failure=(status, reason)).client() as client:
        with pytest.raises(error) as caught:
            await live_index.find_clip(client, redis, "Khruangbin")
    assert API_KEY not in str(caught.value)
    assert await redis.get("live:clip:khruangbin") is None


def live_app(
    api: Youtube,
    redis: FakeAsyncRedis | None = None,
    lastfm_names: list[str] | None = None,
    **kw: Any,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "ws.audioscrobbler.com":
            if request.url.params["method"] == "artist.getInfo":
                return httpx.Response(200, json={"artist": {"url": "https://www.last.fm/music/x"}})
            tracks = [{"name": n, "url": "u"} for n in lastfm_names or []]
            return httpx.Response(200, json={"toptracks": {"track": tracks}})
        if request.url.host == "www.googleapis.com":
            return api.handle(request)
        return forbidden_http(request)

    settings: dict[str, Any] = {"youtube_api_key": SecretStr(API_KEY)} | kw
    app = create_app(
        settings_with(**settings),
        httpx.MockTransport(handler),
        redis or FakeAsyncRedis(),
        contract_model(),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")


async def test_the_route_answers_a_clip_for_an_artist() -> None:
    api = Youtube(videos={"v": video("PT20M")}, comments={"v": [("12:30 the key change", 300)]})
    redis = FakeAsyncRedis()
    await indexed(redis, "khruangbin", ("v", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert"))
    async with live_app(api, redis) as client:
        response = await client.get("/artist/live-clip", params={"name": "Khruangbin"})
    assert response.status_code == 200
    assert response.json() == {
        "clip": {
            "video_id": "v",
            "title": "Khruangbin: Tiny Desk Concert",
            "session": "Tiny Desk Concert",
            "start": 750,
        }
    }


async def test_the_route_answers_no_clip_for_an_artist_youtube_has_none_of() -> None:
    async with live_app(Youtube()) as client:
        response = await client.get("/artist/live-clip", params={"name": "Nobody Known"})
    assert response.status_code == 200
    assert response.json() == {"clip": None}


async def test_the_route_matches_chapters_to_the_artists_lastfm_tracks() -> None:
    description = "0:00 Intro\n3:21 Evaluation\n"
    api = Youtube(videos={"v": video("PT20M", description)})
    redis = FakeAsyncRedis()
    await indexed(redis, "khruangbin", ("v", "Khruangbin: Tiny Desk Concert", "Tiny Desk Concert"))
    async with live_app(api, redis, ["Evaluation"], lastfm_key=SecretStr("lastfm")) as client:
        response = await client.get("/artist/live-clip", params={"name": "Khruangbin"})
    assert response.json()["clip"]["start"] == 201


async def test_the_route_needs_a_name_and_a_youtube_key() -> None:
    async with live_app(Youtube()) as client:
        missing = await client.get("/artist/live-clip")
    assert missing.status_code == 422 and missing.json()["code"] == "invalid_artist"
    async with live_app(Youtube(), youtube_api_key=None) as client:
        keyless = await client.get("/artist/live-clip", params={"name": "Khruangbin"})
    assert keyless.status_code == 503 and keyless.json()["code"] == "live_clips_unavailable"


async def test_the_route_is_limited_per_visitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "LIVE_CLIP_PER_HOUR", 2)
    async with live_app(Youtube()) as client:
        statuses = [
            (await client.get("/artist/live-clip", params={"name": f"Artist {n}"})).status_code
            for n in range(3)
        ]
    assert statuses == [200, 200, 429]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ((403, "quotaExceeded"), "live_clips_limit"),
        ((500, "backendError"), "live_clips_unavailable"),
    ],
)
async def test_the_route_explains_a_youtube_failure_without_its_key(
    failure: tuple[int, str], code: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        async with live_app(Youtube(failure=failure)) as client:
            response = await client.get("/artist/live-clip", params={"name": "Khruangbin"})
    assert response.status_code == 503 and response.json()["code"] == code
    # httpx logs its own request lines, URL and key included. Our lines must not hold the key.
    ours = [r.getMessage() for r in caplog.records if r.name.startswith("concert_scout")]
    assert API_KEY not in response.text and API_KEY not in "".join(ours)


async def test_the_route_stops_at_the_daily_search_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "YOUTUBE_SEARCHES_PER_DAY", 0)
    api = Youtube()
    async with live_app(api) as client:
        response = await client.get("/artist/live-clip", params={"name": "Khruangbin"})
    assert response.status_code == 503 and response.json()["code"] == "live_clips_limit"
    assert api.calls == []


async def test_the_weekly_sync_route_is_for_the_scheduler_alone() -> None:
    desk = SERIES["Tiny Desk Concert"]
    api = Youtube(playlists={desk.uploads: [playlist_item("d", "Mike D: Tiny Desk Concert")]})
    redis = FakeAsyncRedis()
    async with live_app(api, redis, cron_secret=SecretStr(CRON)) as client:
        refused = await client.get("/sync-live-clips")
        wrong = await client.get("/sync-live-clips", headers={"Authorization": "Bearer nope"})
        ran = await client.get("/sync-live-clips", headers={"Authorization": f"Bearer {CRON}"})
    assert refused.status_code == wrong.status_code == 401
    assert ran.status_code == 200
    assert {step["series"]: step["videos"] for step in ran.json()}["Tiny Desk Concert"] == 1
    assert await redis.exists("live:index:mike d") == 1


async def test_without_a_youtube_key_there_is_no_sync_route() -> None:
    async with live_app(Youtube(), youtube_api_key=None, cron_secret=SecretStr(CRON)) as client:
        response = await client.get("/sync-live-clips", headers={"Authorization": f"Bearer {CRON}"})
    assert response.status_code == 404
