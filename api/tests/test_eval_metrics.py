from concert_scout.models import Artist, Concert, Recommendation
from evals.metrics import measure


def test_metrics_count_lineups_and_check_source_facts() -> None:
    concert = Concert(id="1", name="Concert", url="https://example.com", artists=[Artist(name="One"), Artist(name="Two")])
    altered = concert.model_copy(update={"venue": "Invented"})
    result = measure([Recommendation(concert=altered, reason="fit")], [concert], ["one", "Absent"], [], ["TWO"])
    assert result.bad_artists == 1
    assert (result.must_found, result.must_total) == (1, 2)
    assert (result.judged_good_recommendations, result.recommendations) == (1, 1)
    assert result.invented_or_unknown == 1
