from concert_scout.models import Artist, Concert

# Ticketmaster bills GIVĒON as E followed by a combining macron (U+0304).
DECOMPOSED = "GIVĒON"
COMPOSED = "GIVĒON"


def test_source_text_is_composed_so_a_display_face_draws_one_letter() -> None:
    concert = Concert.model_validate(
        {
            "id": "tm-1",
            "name": DECOMPOSED,
            "url": "https://tickets.example/1",
            "artists": [{"name": DECOMPOSED}],
            "venue": "Carnegie Hall",
            "city": "Bogotá",
            "presales": [
                {
                    "name": f"{DECOMPOSED} Fan Presale",
                    "start": "2026-11-10T10:00:00Z",
                    "end": "2026-11-11T10:00:00Z",
                }
            ],
        }
    )

    assert concert.name == COMPOSED
    assert concert.artists == [Artist(name=COMPOSED)]
    assert concert.city == "Bogotá"
    assert concert.presales[0].name == f"{COMPOSED} Fan Presale"
    assert concert.venue == "Carnegie Hall"
    assert concert.region is None
