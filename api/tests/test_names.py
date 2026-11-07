import pytest

from concert_scout.names import normalize


@pytest.mark.parametrize(
    ("name", "normal"),
    [
        ("  Beyoncé   KNOWLES ", "beyonce knowles"),
        ("The Red Clay Strays", "red clay strays"),
        ("Hiss Golden Messenger!", "hiss golden messenger"),
        ("Simon & Garfunkel", "simon and garfunkel"),
        ("AC/DC", "acdc"),
        ("!!!", "!!!"),
        ("The The", "the"),
    ],
)
def test_normalize_gives_two_spellings_one_form(name: str, normal: str) -> None:
    assert normalize(name) == normal
