"""Official YouTube Data API reads for Watch Live, and the code that picks a peak moment.

Everything here is a documented endpoint: `videos.list`, `commentThreads.list` and `search.list`,
which cost 1, 1 and 100 units. YouTube's "Most Replayed" heatmap is not in the API and is never
scraped. A start time comes from the stamps the crowd's comments agree on, a chapter of a
best-known track or the video's length, never a model.
"""

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, cast

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from concert_scout.names import normalize
from concert_scout.sources import youtube

# A start before this is still the intro, and a start after the duration less this has no show left.
EARLIEST_START = 15
SHOW_LEFT = 30
# Beyond this a video is a whole set, which opens with tuning and talk.
SET_LENGTH = 600
SKIPPED_INTRO = 180
INTRO_SHARE = 0.2
SEARCH_RESULTS = 5
# A page of comments costs 1 unit whatever its size, so it takes the largest.
TOP_COMMENTS = 100
# A stamp counts once plus once per like on its comment. Below this many votes it may be one fan's.
MIN_VOTES = 10
# Stamps this close are one moment, as "40:23" and "40:30" for one drop.
MOMENT_SECONDS = 20
# More stamps than this make a tracklist, which has no single moment but may name a hit.
MAX_COMMENT_STAMPS = 3
# "+" makes another Artist of the same letters, as "Omar+" beside "Omar".
NAME_SYMBOLS = "+"
MUSIC_CATEGORY = "10"
# Comments can be off, and a video can be gone since it was indexed.
UNREADABLE_COMMENTS = frozenset({"commentsDisabled", "videoNotFound", "forbidden"})

STAMP = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?!\d|:\d)")
# A chapter line may open with a bullet or bracket, and may put a dash or colon after its stamp.
BEFORE_STAMP = " \t[(•*▶►-–—"
AFTER_STAMP = " \t])-–—:|•."
LINK = re.compile(r"https?://|www\.|\.(?:com|net|org|ly|me)\b", re.IGNORECASE)
PARENTHESIS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
DURATION = TypeAdapter(dt.timedelta)


def artist_key(name: str) -> str:
    """The form an Artist's name takes in Watch Live, which keeps the symbols that tell Artists
    apart. Both the index and a lookup use it."""
    return normalize(name, NAME_SYMBOLS)


def names_artist(title: str, name: str) -> bool:
    """Whether a video title names the Artist in whole words, so "Omar" is not found in
    "Omari" or "Omar+"."""
    wanted = artist_key(name)
    return bool(wanted) and f" {wanted} " in f" {artist_key(title)} "


class LiveVideo(BaseModel):
    """A video of a live performance. `session` is what to call it: its series or its channel."""

    video_id: str
    title: str
    session: str


class LiveClip(BaseModel):
    """A video to embed and the second to start it at."""

    video_id: str
    title: str
    session: str
    start: int


class Details(BaseModel):
    description: str
    duration: int
    embeddable: bool


class Chapter(BaseModel):
    start: int
    title: str


class Comment(BaseModel):
    text: str
    likes: int


def seconds_of(stamp: re.Match[str]) -> int | None:
    """`4:12` and `1:02:03` as seconds. A stamp with 60 or more minutes or seconds is not one."""
    hours, minutes, seconds = stamp[1], stamp[2], stamp[3]
    if int(minutes) > 59 or int(seconds) > 59:
        return None
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def chapters(description: str) -> list[Chapter]:
    """The lines of a description that open with a stamp and name what starts there."""
    found: list[Chapter] = []
    for line in description.splitlines():
        text = line.lstrip(BEFORE_STAMP)
        stamp = STAMP.match(text)
        if not stamp or (start := seconds_of(stamp)) is None:
            continue
        if title := text[stamp.end() :].lstrip(AFTER_STAMP).strip():
            found.append(Chapter(start=start, title=title))
    return found


def _bare(title: str) -> str:
    return normalize(PARENTHESIS.sub("", title))


def chapter_start(found: Sequence[Chapter], tracks: Sequence[str], duration: int) -> int | None:
    """Where the Artist's best-known track starts. Tracks come most played first."""
    for track in tracks:
        name = _bare(track)
        for chapter in found:
            title = _bare(chapter.title)
            # Whole words, so the track "Time" is not found inside "Sometimes".
            if name and f" {name} " in f" {title} " and chapter.start <= duration - SHOW_LEFT:
                return chapter.start
    return None


def crowd_start(comments: Sequence[Comment], duration: int) -> int | None:
    """The moment the crowd's comments agree on: every stamp in the part worth watching votes
    once plus once per like, stamps within `MOMENT_SECONDS` add up, and the moment with the most
    votes wins if it has `MIN_VOTES`. It starts at its own most voted stamp."""
    votes: dict[int, int] = defaultdict(int)
    for comment in comments:
        if LINK.search(comment.text):
            continue
        stamps = [seconds_of(match) for match in STAMP.finditer(comment.text)]
        if len(stamps) > MAX_COMMENT_STAMPS:
            continue
        for start in {s for s in stamps if s is not None}:
            if EARLIEST_START <= start <= duration - SHOW_LEFT:
                votes[start] += 1 + comment.likes

    def moment(start: int) -> int:
        return sum(n for other, n in votes.items() if abs(other - start) <= MOMENT_SECONDS)

    if not votes:
        return None
    best = max(votes, key=lambda start: (moment(start), votes[start], -start))
    return best if moment(best) >= MIN_VOTES else None


def comment_chapters(comments: Sequence[Comment]) -> list[Chapter]:
    """The longest tracklist a commenter wrote out, as chapters."""
    lists = [chapters(comment.text) for comment in comments if not LINK.search(comment.text)]
    tracklists = [found for found in lists if len(found) > MAX_COMMENT_STAMPS]
    return max(tracklists, key=len) if tracklists else []


def intro_start(duration: int) -> int:
    """A whole set skips its tuning and talk. A song starts at its start."""
    return int(min(SKIPPED_INTRO, duration * INTRO_SHARE)) if duration > SET_LENGTH else 0


def _refuse_unless(response: httpx.Response, tolerated: frozenset[str]) -> None:
    reasons = youtube.error_reasons(response)
    if response.status_code == 429 or reasons & youtube.QUOTA_REASONS:
        raise youtube.QuotaExceeded
    if not reasons & tolerated:
        raise youtube.YouTubeError(f"status {response.status_code}")


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: Mapping[str, str],
    tolerated: frozenset[str] = frozenset(),
) -> list[Mapping[str, Any]]:
    """The `items` of one answer. Messages never hold the request URL, which carries the API key."""
    try:
        response = await client.get(path, params=dict(params))
        if response.status_code >= 400:
            _refuse_unless(response, tolerated)
            return []
        body = cast(Mapping[str, Any], response.json())
        items = body["items"]
        if not isinstance(items, list):
            raise youtube.YouTubeError("unreadable response: items")
        return cast(list[Mapping[str, Any]], items)
    except httpx.HTTPError as exc:
        raise youtube.YouTubeError(type(exc).__name__) from None
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise youtube.YouTubeError(f"unreadable response: {type(exc).__name__}") from None


async def video_details(client: httpx.AsyncClient, video_ids: Sequence[str]) -> dict[str, Details]:
    """One `videos.list` call, 1 unit, for any number of videos up to 50. Only public videos that
    allow embedding are kept, because any other cannot play in a Ticket."""
    params = {"part": "snippet,contentDetails,status", "id": ",".join(video_ids)}
    found: dict[str, Details] = {}
    for item in await _get(client, "/videos", params):
        try:
            status = cast(Mapping[str, Any], item["status"])
            if status["privacyStatus"] != "public" or status["embeddable"] is not True:
                continue
            duration = DURATION.validate_python(item["contentDetails"]["duration"])
            description = item["snippet"].get("description") or ""
            found[item["id"]] = Details(
                description=description,
                duration=int(duration.total_seconds()),
                embeddable=True,
            )
        except (KeyError, TypeError, ValidationError):
            continue
    return found


async def top_comments(client: httpx.AsyncClient, video_id: str) -> list[Comment]:
    """The most relevant top-level comments, one `commentThreads.list` call, 1 unit."""
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",
        "maxResults": str(TOP_COMMENTS),
        "textFormat": "plainText",
    }
    comments: list[Comment] = []
    for item in await _get(client, "/commentThreads", params, UNREADABLE_COMMENTS):
        try:
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comments.append(Comment(text=snippet["textDisplay"], likes=snippet["likeCount"]))
        except (KeyError, TypeError, ValidationError):
            continue
    return comments


async def search_videos(client: httpx.AsyncClient, name: str) -> list[LiveVideo]:
    """Embeddable music videos for "{name} live performance". One `search.list` call, 100 units,
    so the caller counts it. A result must name the Artist, or it is somebody else's. Anyone's
    upload counts, a fan's included."""
    params = {
        "part": "snippet",
        "q": f"{name} live performance",
        "type": "video",
        "videoEmbeddable": "true",
        "videoCategoryId": MUSIC_CATEGORY,
        "maxResults": str(SEARCH_RESULTS),
    }
    found: list[LiveVideo] = []
    for item in await _get(client, "/search", params):
        try:
            title: str = item["snippet"]["title"]
            if names_artist(title, name):
                found.append(
                    LiveVideo(
                        video_id=item["id"]["videoId"],
                        title=title,
                        session=item["snippet"]["channelTitle"],
                    )
                )
        except (KeyError, TypeError, ValidationError):
            continue
    return found
