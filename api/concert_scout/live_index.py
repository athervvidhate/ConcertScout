"""Watch Live: a curated index of official live sessions, and the clip to open for an Artist.

A weekly job reads the upload playlists of seven channels that film live sets, at 1 unit a page,
and files each video under the Artist its title names. A visitor who presses Watch Live then
costs a cache read, and 2 units the first time. An Artist the index lacks gets one official
search, 100 units, which a daily limit keeps rare. Every fact is a source record (ADR 0002).
"""

import asyncio
import datetime as dt
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from pydantic import AliasPath, BaseModel, Field, ValidationError
from redis.asyncio import Redis

from concert_scout import cache, limits
from concert_scout.names import normalize
from concert_scout.sources import lastfm, live_clips, setlistfm, youtube
from concert_scout.sources.live_clips import Details, LiveClip, LiveVideo

logger = logging.getLogger(__name__)

# A weekly sync keeps each Artist fresh with a week to spare.
INDEX_TTL = dt.timedelta(days=14)
CLIP_TTL = dt.timedelta(days=30)
MISS_TTL = dt.timedelta(days=14)
# 30 pages of 50 are the 1,500 newest uploads of a channel, 30 units a channel.
PAGES_PER_CHANNEL = 30
# A `whole` pattern that always or never holds, for a series of whole sets or of single songs.
SETS = re.compile("")
SONGS = re.compile("(?!)")


@dataclass(frozen=True)
class Series:
    """One channel's live sessions. `title` reads the Artist out of a video's title, and is also
    what tells a session from the channel's other uploads."""

    name: str
    channel_id: str
    title: re.Pattern[str]
    # Matches a title whose video holds an Artist's whole set, which beats a single song of it.
    whole: re.Pattern[str] = SONGS

    @property
    def uploads(self) -> str:
        """A channel's uploads are a playlist, whose ID is the channel's with UC changed to UU."""
        return "UU" + self.channel_id.removeprefix("UC")


# In the order a Ticket's clip is chosen from, which is the order of the spec.
SERIES = (
    Series(
        "Tiny Desk Concert",
        "UC4eYXhJI4-7wSWc8UNRwD4A",
        re.compile(r"^(?P<artist>.+?): Tiny Desk(?: \(Home\))? Concert\b"),
        SETS,
    ),
    Series(
        "KEXP",
        "UC3I2GFN_F8WudD_2jUZbojA",
        re.compile(r"^(?P<artist>.+?) - .+ \(Live on KEXP\)$"),
        re.compile(r"Full Performance", re.IGNORECASE),
    ),
    Series(
        "Boiler Room",
        "UCGBpxWJr9FNOcFYA5GkKrMg",
        re.compile(r"^(?P<artist>.+?) \| Boiler Room\b"),
        SETS,
    ),
    Series(
        "Cercle",
        "UCPKT_csvP72boVX0XrMtagQ",
        re.compile(r"^(?P<artist>.+?)\s+(?:-|–|\||@)\s+.*\bCercle\b"),
        SETS,
    ),
    Series(
        "Audiotree Live",
        "UCWjmAUHmajb1-eo5WKk_22A",
        re.compile(r"^(?P<artist>.+?)(?: - .+ \| | on )Audiotree Live"),
        re.compile(r"Full Session", re.IGNORECASE),
    ),
    Series(
        "COLORS",
        "UC2Qw1dzXDBAZPwS7zm37g8g",
        re.compile(r"^(?P<artist>.+?) - .+ \| A COLORS SHOW$"),
    ),
    Series(
        "Radio 1 Live Lounge",
        "UC-FQUIVQ-bZiefzBiQAa8Fw",
        re.compile(r"^(?P<artist>.+?) - .*Live Lounge\b"),
    ),
)


SESSION_CHANNELS = frozenset(series.channel_id for series in SERIES)


class IndexedVideos(BaseModel):
    videos: list[LiveVideo]


class LiveClipResult(BaseModel):
    """What a lookup found, as the route answers and the cache keeps it. `None` is a miss, kept
    so the same Artist is not looked up again at once."""

    clip: LiveClip | None


class PlaylistVideo(BaseModel):
    """The two fields of a `playlistItems.list` item that a session is read from."""

    video_id: str = Field(validation_alias=AliasPath("snippet", "resourceId", "videoId"))
    title: str = Field(validation_alias=AliasPath("snippet", "title"))


class Indexed(BaseModel):
    series: str
    videos: int = 0
    error: str | None = None


def parse_session(series: Series, title: str) -> tuple[str, bool] | None:
    """The Artist a session's title names, and whether the video holds their whole set."""
    if not (match := series.title.match(title)):
        return None
    artist = match["artist"].strip()
    # A promo clip opens with a handle or a hashtag, never with an Artist's name.
    if not artist or artist[0] in "@#" or not normalize(artist):
        return None
    return artist, bool(series.whole and series.whole.search(title))


def index_videos(
    series: Series, items: Sequence[Mapping[str, Any]]
) -> dict[str, tuple[LiveVideo, bool]]:
    """An Artist's best video in one series: the whole set if there is one, else the first listed,
    which in an uploads playlist is the newest. Keyed by the normalized name."""
    best: dict[str, tuple[LiveVideo, bool]] = {}
    for item in items:
        try:
            listed = PlaylistVideo.model_validate(item)
        except ValidationError:
            continue
        if not (parsed := parse_session(series, listed.title)):
            continue
        key = normalize(parsed[0])
        if key not in best or (parsed[1] and not best[key][1]):
            video = LiveVideo(video_id=listed.video_id, title=listed.title, session=series.name)
            best[key] = (video, parsed[1])
    return best


async def _read_series(
    client: httpx.AsyncClient, series: Series
) -> tuple[Indexed, dict[str, tuple[LiveVideo, bool]]]:
    try:
        items = await youtube.fetch_playlist_items(client, series.uploads, PAGES_PER_CHANNEL)
    except (
        youtube.YouTubeError,
        youtube.QuotaExceeded,
        youtube.PlaylistNotFound,
        youtube.PlaylistPrivate,
    ) as exc:
        logger.warning("Live sessions of %s not read: %s", series.name, type(exc).__name__)
        return Indexed(series=series.name, error=type(exc).__name__), {}
    found = index_videos(series, items)
    return Indexed(series=series.name, videos=len(found)), found


async def sync(client: httpx.AsyncClient, redis: Redis) -> list[Indexed]:
    """Reads every series and files its videos by Artist, in the order of `SERIES`. A series that
    fails leaves the others indexed, and its Artists keep their old entries until they expire."""
    results = await asyncio.gather(*(_read_series(client, series) for series in SERIES))
    by_artist: dict[str, list[LiveVideo]] = {}
    for _, found in results:
        for key, (video, _) in found.items():
            by_artist.setdefault(key, []).append(video)
    await cache.write_many(
        redis,
        {_index_key(key): IndexedVideos(videos=videos) for key, videos in by_artist.items()},
        INDEX_TTL,
    )
    return [indexed for indexed, _ in results]


def _index_key(artist_key: str) -> str:
    return f"live:index:{artist_key}"


def _clip_key(artist_key: str) -> str:
    return f"live:clip:{artist_key}"


type TrackNames = Callable[[], Awaitable[list[str]]]


async def _track_names(
    lastfm_client: httpx.AsyncClient | None,
    setlistfm_client: httpx.AsyncClient | None,
    redis: Redis,
    name: str,
) -> list[str]:
    """Songs the Artist plays on stage, from Setlist.fm's staples, then their best-known tracks,
    most played first, from Last.fm. Either source may be off or fail, and the other still helps."""
    names: list[str] = []
    if setlistfm_client:
        try:
            summary = await setlistfm.artist_setlist(setlistfm_client, redis, name)
            names += [staple.name for staple in summary.staples]
        except setlistfm.SetlistfmError as exc:
            logger.warning("Setlist.fm staples for a live clip not read: %s", exc)
    if lastfm_client:
        try:
            profile = await lastfm.artist_profile(lastfm_client, redis, name)
            names += [track.name for track in profile.top_tracks]
        except lastfm.LastfmError as exc:
            logger.warning("Last.fm tracks for a live clip not read: %s", exc)
    return names


async def _start(
    client: httpx.AsyncClient, video_id: str, details: Details, tracks: TrackNames
) -> int:
    """The chapter of a best-known track, else the most liked comment's stamp, else the start a
    video's length calls for. A video of no length is live, so it starts where it is."""
    duration = details.duration
    if not duration:
        return 0
    if found := live_clips.chapters(details.description):
        start = live_clips.chapter_start(found, await tracks(), duration)
        if start is not None:
            return start
    comments = await live_clips.top_comments(client, video_id)
    start = live_clips.comment_start(comments, duration)
    return live_clips.intro_start(duration) if start is None else start


async def _clip_of(
    client: httpx.AsyncClient, videos: Sequence[LiveVideo], tracks: TrackNames
) -> LiveClip | None:
    """The first of the videos that can play in a Ticket, with its start."""
    if not videos:
        return None
    details = await live_clips.video_details(client, [video.video_id for video in videos])
    for video in videos:
        if video.video_id in details:
            start = await _start(client, video.video_id, details[video.video_id], tracks)
            return LiveClip(**video.model_dump(), start=start)
    return None


async def find_clip(
    client: httpx.AsyncClient,
    redis: Redis,
    name: str,
    *,
    lastfm_client: httpx.AsyncClient | None = None,
    setlistfm_client: httpx.AsyncClient | None = None,
) -> LiveClip | None:
    """The Artist's live clip, or None when YouTube has no official, embeddable one.

    The curated index comes first. Only an Artist it cannot serve costs a search, which the
    daily limit counts and raises `DailyLimitReached` past. Both answers are cached, a miss for
    less time.
    """
    key = normalize(name)
    if cached := await cache.read(redis, _clip_key(key), LiveClipResult):
        return cached.clip
    tracks: TrackNames = partial(_track_names, lastfm_client, setlistfm_client, redis, name)
    indexed = await cache.read(redis, _index_key(key), IndexedVideos)
    clip = await _clip_of(client, indexed.videos, tracks) if indexed else None
    if clip is None:
        await limits.youtube_search_call(redis)
        clip = await _clip_of(
            client, await live_clips.search_videos(client, name, SESSION_CHANNELS), tracks
        )
    await cache.write(
        redis, _clip_key(key), LiveClipResult(clip=clip), CLIP_TTL if clip else MISS_TTL
    )
    return clip
