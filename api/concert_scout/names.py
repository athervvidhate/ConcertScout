import re
import unicodedata

COLLAB_JOIN = re.compile(r"\s+(?:&|\+|/|x|with)\s+|\s*,\s+", re.IGNORECASE)
MAX_COLLAB_NAMES = 6
MAX_TITLE_NAME_LENGTH = 60

# The same job as frontend/lib/show-title.ts, which strips Artists out of a title to leave the
# show; this reads the Artists out of it. These words only describe an event, never an Artist.
SHOW_WORDS = frozenset(
    "annual homecoming run tour show live concert night weekend birthday bash party "
    "celebration anniversary residency reunion farewell holiday christmas".split()
)
# "Maddie Zahm: Everything All The Time Tour" and "X - 2026 Tour".
TOUR_TITLE = re.compile(r"^(?P<name>[^:]+?)\s*(?::|\s[-–—]\s)\s*.*\btour\b", re.IGNORECASE)
PRESENTS = re.compile(r"^(?P<name>.+?)\s+presents?\b", re.IGNORECASE)
POSSESSIVE = re.compile(r"^(?P<name>.+?)['’]s\s+(?P<rest>.+)$", re.IGNORECASE)


def normalize(name: str) -> str:
    """The form two spellings of one Artist's name share, for joins and cache keys."""
    decomposed = unicodedata.normalize("NFKD", name)
    unaccented = "".join(c for c in decomposed if not unicodedata.combining(c))
    words = unaccented.casefold().replace("&", " and ")
    bare = " ".join(re.sub(r"[^\w\s]", "", words).split())
    # A name that is all punctuation, such as "!!!", keeps it rather than becoming empty.
    return bare.removeprefix("the ") or " ".join(words.split())


def collab_names(name: str) -> list[str]:
    """The Artists in a billing like "Usher Raymond & Chris Brown". "and" stays out of the list,
    because it joins far more band names than tours. One name gives an empty list."""
    parts = [part.strip() for part in COLLAB_JOIN.split(name) if part.strip()]
    return parts[:MAX_COLLAB_NAMES] if len(parts) > 1 else []


def title_names(title: str) -> list[str]:
    """Names an event title may bill, for a listing with no Lineup. These are guesses, so each
    one must be confirmed before it counts as an Artist.

    The headliner comes from "X Presents: ...", "X: ... Tour" and "X's Annual ... Run". With none
    of those, a list such as "A, B, C" bills each name. Anything else bills nobody.
    """
    text = " ".join(title.replace("“", '"').replace("”", '"').strip('" ').split())
    if match := PRESENTS.match(text) or TOUR_TITLE.match(text):
        head = match["name"]
    elif (match := POSSESSIVE.match(text)) and _only_show_words(match["rest"]):
        head = match["name"]
    else:
        return _plausible(collab_names(text))
    return _plausible(collab_names(head) or [head])


def _only_show_words(text: str) -> bool:
    words = normalize(text).split()
    return bool(words) and all(word in SHOW_WORDS for word in words)


def _plausible(names: list[str]) -> list[str]:
    cleaned = (name.strip(' "-–—:') for name in names)
    return [n for n in cleaned if n and len(n) <= MAX_TITLE_NAME_LENGTH and not _only_show_words(n)]
