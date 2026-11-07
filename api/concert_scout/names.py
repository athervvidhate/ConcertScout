import re
import unicodedata


def normalize(name: str) -> str:
    """The form two spellings of one Artist's name share, for joins and cache keys."""
    decomposed = unicodedata.normalize("NFKD", name)
    unaccented = "".join(c for c in decomposed if not unicodedata.combining(c))
    words = unaccented.casefold().replace("&", " and ")
    bare = " ".join(re.sub(r"[^\w\s]", "", words).split())
    # A name that is all punctuation, such as "!!!", keeps it rather than becoming empty.
    return bare.removeprefix("the ") or " ".join(words.split())
