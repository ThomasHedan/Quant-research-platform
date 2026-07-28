"""Tests de edgelab.papers.models (Phase 7)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from edgelab.papers.models import (
    HypothesisDraftRequest,
    PaperAnalysisRequest,
    PaperSheet,
)
from pydantic import ValidationError


def test_paper_analysis_request_rejects_empty_title(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un titre vide (ou blanc) est refusé."""
    with pytest.raises(ValidationError):
        make_paper_analysis_request(title="   ")


def test_paper_analysis_request_rejects_no_authors(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """La liste d'auteurs ne peut pas être vide."""
    with pytest.raises(ValidationError):
        make_paper_analysis_request(authors=())


def test_paper_analysis_request_rejects_a_single_letter_language_code(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """`language_source` doit ressembler à un code ISO 639-1 (au moins deux lettres)."""
    with pytest.raises(ValidationError):
        make_paper_analysis_request(language_source="z")


def test_paper_analysis_request_rejects_empty_economic_hypothesis(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """L'hypothèse économique ne peut pas être vide."""
    with pytest.raises(ValidationError):
        make_paper_analysis_request(economic_hypothesis="")


def test_paper_analysis_request_rejects_a_publication_year_before_1900(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Une année de publication antérieure à 1900 est implausible et refusée."""
    with pytest.raises(ValidationError):
        make_paper_analysis_request(publication_year=1899)


def test_paper_analysis_request_rejects_a_publication_year_far_in_the_future(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Une année de publication trop en avance sur aujourd'hui est refusée."""
    far_future_year = datetime.now(UTC).year + 5
    with pytest.raises(ValidationError):
        make_paper_analysis_request(publication_year=far_future_year)


def test_paper_analysis_request_accepts_next_year_as_a_preprint(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un preprint daté de l'année prochaine reste plausible."""
    next_year = datetime.now(UTC).year + 1

    request = make_paper_analysis_request(publication_year=next_year)

    assert request.publication_year == next_year


def test_paper_sheet_from_request_preserves_language_source(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un papier en chinois produit une fiche portant `language_source: zh`.

    Adaptation du critère d'acceptation Phase 7 : la traduction en français
    est déléguée à l'IA d'extraction (voir `edgelab/papers/README.md`), donc
    ce test vérifie ce que le code contrôle réellement — la préservation du
    code de langue d'origine, indépendamment du contenu textuel.
    """
    request = make_paper_analysis_request(language_source="zh")

    sheet = PaperSheet.from_request(request)

    assert sheet.language_source == "zh"


def test_paper_sheet_from_request_generates_a_unique_id(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Deux fiches construites depuis la même requête reçoivent des identifiants distincts."""
    request = make_paper_analysis_request()

    first = PaperSheet.from_request(request)
    second = PaperSheet.from_request(request)

    assert first.id != second.id


def test_paper_sheet_nests_testability_inputs(
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Les trois booléens de testabilité sont regroupés dans `testability_inputs`."""
    request = make_paper_analysis_request(
        instrument_available_at_prop_firms=True,
        data_accessible=False,
        mechanizable_without_discretion=True,
    )

    sheet = PaperSheet.from_request(request)

    assert sheet.testability_inputs.instrument_available_at_prop_firms is True
    assert sheet.testability_inputs.data_accessible is False
    assert sheet.testability_inputs.mechanizable_without_discretion is True


def test_hypothesis_draft_request_rejects_an_empty_strategy_code_skeleton(
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """Un squelette de code vide n'a aucune valeur pour démarrer une stratégie."""
    with pytest.raises(ValidationError):
        make_hypothesis_draft_request(strategy_code_skeleton="   ")


def test_hypothesis_draft_request_accepts_a_minimal_valid_payload(
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """Un brouillon valide se construit sans lever."""
    request = make_hypothesis_draft_request()

    assert request.predicted_direction == "long"
    assert len(request.kill_criteria) == 1
