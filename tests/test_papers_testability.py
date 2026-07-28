"""Tests de edgelab.papers.testability (Phase 7)."""

from collections.abc import Callable
from datetime import date

from edgelab.papers.models import PaperAnalysisRequest, PaperSheet
from edgelab.papers.testability import (
    POST_PUBLICATION_SATURATION_YEARS,
    compute_testability_score,
    post_publication_years,
)

_REFERENCE_DATE = date(2026, 1, 1)


def test_post_publication_years_is_never_negative_for_a_future_paper() -> None:
    """Un papier daté du futur ne produit pas une ancienneté négative."""
    years = post_publication_years(2030, as_of=_REFERENCE_DATE)

    assert years == 0.0


def test_post_publication_years_counts_elapsed_years() -> None:
    """Le nombre d'années post-publication est la différence simple de millésimes."""
    years = post_publication_years(2016, as_of=_REFERENCE_DATE)

    assert years == 10.0


def test_testability_score_is_strictly_lower_for_a_paper_published_in_2023_than_in_2005(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Critère d'acceptation Phase 7 : toutes choses égales par ailleurs, un papier plus
    récent est strictement moins testable qu'un papier plus ancien (McLean & Pontiff)."""
    recent = PaperSheet.from_request(make_paper_analysis_request(publication_year=2023))
    old = PaperSheet.from_request(make_paper_analysis_request(publication_year=2005))

    recent_score = compute_testability_score(recent, as_of=_REFERENCE_DATE)
    old_score = compute_testability_score(old, as_of=_REFERENCE_DATE)

    assert recent_score < old_score


def test_testability_score_saturates_beyond_the_saturation_window(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Au-delà de la fenêtre de saturation, deux papiers d'âges différents ne se distinguent
    plus sur le facteur post-publication — le score plafonne, il ne diverge pas indéfiniment."""
    just_saturated_year = _REFERENCE_DATE.year - int(POST_PUBLICATION_SATURATION_YEARS)
    ancient_year = just_saturated_year - 20
    just_saturated = PaperSheet.from_request(
        make_paper_analysis_request(publication_year=just_saturated_year)
    )
    ancient = PaperSheet.from_request(make_paper_analysis_request(publication_year=ancient_year))

    assert compute_testability_score(
        just_saturated, as_of=_REFERENCE_DATE
    ) == compute_testability_score(ancient, as_of=_REFERENCE_DATE)


def test_testability_score_is_higher_when_all_boolean_inputs_are_true(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Chaque composante booléenne favorable augmente strictement le score."""
    favorable = PaperSheet.from_request(
        make_paper_analysis_request(
            instrument_available_at_prop_firms=True,
            data_accessible=True,
            mechanizable_without_discretion=True,
            costs_considered="oui",
        )
    )
    unfavorable = PaperSheet.from_request(
        make_paper_analysis_request(
            instrument_available_at_prop_firms=False,
            data_accessible=False,
            mechanizable_without_discretion=False,
            costs_considered="non",
        )
    )

    assert compute_testability_score(favorable, as_of=_REFERENCE_DATE) > compute_testability_score(
        unfavorable, as_of=_REFERENCE_DATE
    )


def test_testability_score_stays_within_unit_interval(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Le score reste dans [0, 1] même au meilleur des cas."""
    best_case = PaperSheet.from_request(
        make_paper_analysis_request(
            publication_year=1990,
            instrument_available_at_prop_firms=True,
            data_accessible=True,
            mechanizable_without_discretion=True,
            costs_considered="oui",
        )
    )

    score = compute_testability_score(best_case, as_of=_REFERENCE_DATE)

    assert 0.0 <= score <= 1.0
