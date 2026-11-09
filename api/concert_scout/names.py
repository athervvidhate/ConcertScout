import re
import unicodedata

COLLAB_JOIN = re.compile(r"\s+(?:&|\+|/|x|with)\s+|\s*,\s+", re.IGNORECASE)
MAX_COLLAB_NAMES = 6


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
