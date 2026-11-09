"""Small, explicit aliases; unknown terms stay intact for the interpreter and geocoder."""

PLACE_ALIASES = {
    "sf": "San Francisco, California, United States",
    "sfo": "San Francisco, California, United States",
    "the bay": "San Francisco, California, United States",
    "san francisco bay area": "San Francisco, California, United States",
    "bay area": "San Francisco, California, United States",
    "the bay area": "San Francisco, California, United States",
    "la": "Los Angeles, California, United States",
    "lax": "Los Angeles, California, United States",
    "nyc": "New York City, New York, United States",
    "phl": "Philadelphia, Pennsylvania, United States",
    "philly": "Philadelphia, Pennsylvania, United States",
    "atl": "Atlanta, Georgia, United States",
    "chi": "Chicago, Illinois, United States",
    "chi town": "Chicago, Illinois, United States",
    "chitown": "Chicago, Illinois, United States",
    "dc": "Washington, District of Columbia, United States",
    "dmv": "Washington, District of Columbia, United States",
    "the dmv": "Washington, District of Columbia, United States",
    "nola": "New Orleans, Louisiana, United States",
    "pdx": "Portland, Oregon, United States",
    "atx": "Austin, Texas, United States",
    "dfw": "Dallas, Texas, United States",
    "slc": "Salt Lake City, Utah, United States",
    "stl": "St. Louis, Missouri, United States",
    "msp": "Minneapolis, Minnesota, United States",
    "kc": "Kansas City, Missouri, United States",
    "okc": "Oklahoma City, Oklahoma, United States",
}

GENRE_ALIASES = {
    "ukg": "uk garage",
    "uk garage": "uk garage",
    "ukgarage": "uk garage",
    "u.k. garage": "uk garage",
    "2 step": "2 step garage",
    "2step": "2 step garage",
    "two step garage": "2 step garage",
    "2 step garage": "2 step garage",
    "dnb": "drum and bass",
    "d&b": "drum and bass",
    "d n b": "drum and bass",
    "drum & bass": "drum and bass",
    "drum n bass": "drum and bass",
    "drum'n'bass": "drum and bass",
    "rnb": "r&b",
    "r n b": "r&b",
    "rhythm and blues": "r&b",
    "rhythm & blues": "r&b",
    "edm": "electronic dance music",
    "idm": "intelligent dance music",
    "ebm": "electronic body music",
    "d&b music": "drum and bass",
}


def _key(text: str) -> str:
    return " ".join(text.casefold().replace("-", " ").split())


def place_name(text: str) -> str:
    # Only the extracted place is expanded. LA in an Artist's name is never rewritten.
    return PLACE_ALIASES.get(_key(text), text.strip())


def music_tag(text: str) -> str:
    key = _key(text)
    return GENRE_ALIASES.get(key, key)
