import pytest

from concert_scout.names import normalize, title_names


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


@pytest.mark.parametrize(
    ("title", "names"),
    [
        # The five Boise listings with no Lineup, captured on November 9, 2026.
        ("Olivia O’Brien Presents: The PIXIE Tour", ["Olivia O’Brien"]),
        ("Maddie Zahm: Everything All The Time Tour", ["Maddie Zahm"]),
        ("JEFF CROSBY'S ANNUAL HOMECOMING RUN", ["JEFF CROSBY"]),
        (
            "THE SLIGHTEST BITS, cryshadow, Eunoian, The Mall Goth Moths",
            ["THE SLIGHTEST BITS", "cryshadow", "Eunoian", "The Mall Goth Moths"],
        ),
        ("Triptides, Eunoian", ["Triptides", "Eunoian"]),
        # Obvious cousins.
        ("Foo Presents Bar and Baz", ["Foo"]),
        ("Foo - 2026 Tour", ["Foo"]),
        ("Foo's Annual Holiday Show", ["Foo"]),
        # Nothing says who plays, so nobody is billed. A bare name might be a show.
        ("Triptides", []),
        ("Mike's Bar Open Mic", []),
        ("Halloween Party", []),
        ("Annual Show, Tour", []),
    ],
)
def test_a_title_bills_the_names_it_reads_and_nothing_else(title: str, names: list[str]) -> None:
    assert title_names(title) == names
