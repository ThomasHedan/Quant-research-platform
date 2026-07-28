"""Tests de edgelab.papers.repository (Phase 7)."""

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from edgelab.papers.models import (
    HypothesisDraftRequest,
    PaperAnalysisRequest,
    TriageStatus,
)
from edgelab.papers.repository import (
    PaperNotFoundError,
    PaperRepository,
    PaperRepositoryError,
)


def test_create_lands_a_paper_directly_in_fiche_faite(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un papier créé depuis le JSON collé atterrit en `fiche_faite` (pas `a_lire`)."""
    record = paper_repository.create(make_paper_analysis_request())

    assert record.status == TriageStatus.FICHE_FAITE
    assert record.hypothesis_draft is None
    assert record.dead_reason == ""


def test_get_returns_none_for_an_unknown_paper(paper_repository: PaperRepository) -> None:
    """Un identifiant inconnu renvoie `None`, jamais une exception."""
    assert paper_repository.get("does-not-exist") is None


def test_get_returns_the_created_paper(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un papier lu juste après création correspond à ce qui a été écrit."""
    created = paper_repository.create(make_paper_analysis_request(title="Un titre précis"))

    fetched = paper_repository.get(created.sheet.id)

    assert fetched is not None
    assert fetched.sheet.title == "Un titre précis"


def test_list_papers_is_empty_when_nothing_was_created(
    paper_repository: PaperRepository,
) -> None:
    """Aucun papier enregistré : liste vide, pas d'erreur."""
    assert paper_repository.list_papers() == []


def test_list_papers_returns_most_recently_updated_first(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """La liste est triée par mise à jour la plus récente, pas par création."""
    first = paper_repository.create(make_paper_analysis_request(title="Premier"))
    paper_repository.create(make_paper_analysis_request(title="Second"))

    # Toucher "Premier" après coup doit le faire remonter en tête de liste.
    paper_repository.attach_hypothesis(first.sheet.id, make_hypothesis_draft_request())

    records = paper_repository.list_papers()

    assert records[0].sheet.id == first.sheet.id


def test_attach_hypothesis_advances_status_to_hypothese_ecrite(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """Rattacher un brouillon valide fait avancer le papier dans la file de triage."""
    paper = paper_repository.create(make_paper_analysis_request())

    updated = paper_repository.attach_hypothesis(paper.sheet.id, make_hypothesis_draft_request())

    assert updated.status == TriageStatus.HYPOTHESE_ECRITE
    assert updated.hypothesis_draft is not None
    assert updated.hypothesis_draft.paper_id == paper.sheet.id


def test_attach_hypothesis_derives_strategy_id_from_the_paper(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """`strategy_id` est dérivé côté serveur, jamais accepté depuis le JSON externe."""
    paper = paper_repository.create(make_paper_analysis_request())

    updated = paper_repository.attach_hypothesis(paper.sheet.id, make_hypothesis_draft_request())

    assert updated.hypothesis_draft is not None
    assert updated.hypothesis_draft.hypothesis.strategy_id == f"paper_{paper.sheet.id}"


def test_attach_hypothesis_raises_for_an_unknown_paper(
    paper_repository: PaperRepository,
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """Rattacher un brouillon à un papier inconnu échoue explicitement."""
    with pytest.raises(PaperNotFoundError):
        paper_repository.attach_hypothesis("does-not-exist", make_hypothesis_draft_request())


def test_attach_hypothesis_rejects_an_unfalsifiable_draft(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """I2, même chemin qu'ailleurs dans le code : `where_it_should_not_work` vide est refusé.

    `HypothesisDraftRequest` ne porte pas cette règle elle-même — elle est
    appliquée par `HypothesisSheet` (`edgelab.strategies.models`), réutilisé
    tel quel par `attach_hypothesis`, ce qui est précisément le point testé.
    """
    paper = paper_repository.create(make_paper_analysis_request())
    unfalsifiable = make_hypothesis_draft_request(where_it_should_not_work="")

    with pytest.raises(ValueError, match="falsifiable"):
        paper_repository.attach_hypothesis(paper.sheet.id, unfalsifiable)


def test_set_status_moves_a_paper_to_en_test(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un statut de triage sans exigence de motif se met à jour librement."""
    paper = paper_repository.create(make_paper_analysis_request())

    updated = paper_repository.set_status(paper.sheet.id, TriageStatus.EN_TEST)

    assert updated.status == TriageStatus.EN_TEST


def test_set_status_raises_for_an_unknown_paper(paper_repository: PaperRepository) -> None:
    """Changer le statut d'un papier inconnu échoue explicitement."""
    with pytest.raises(PaperNotFoundError):
        paper_repository.set_status("does-not-exist", TriageStatus.EN_TEST)


def test_set_status_mort_without_reason_is_rejected(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Spec Phase 7 : le motif de mort doit rester conservé — pas de `mort` sans raison."""
    paper = paper_repository.create(make_paper_analysis_request())

    with pytest.raises(PaperRepositoryError):
        paper_repository.set_status(paper.sheet.id, TriageStatus.MORT, "   ")


def test_set_status_mort_with_reason_persists_the_reason(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Le motif de mort fourni est conservé et relisible."""
    paper = paper_repository.create(make_paper_analysis_request())

    paper_repository.set_status(paper.sheet.id, TriageStatus.MORT, "Marché inaccessible")

    reloaded = paper_repository.get(paper.sheet.id)
    assert reloaded is not None
    assert reloaded.dead_reason == "Marché inaccessible"


def test_set_status_clears_the_dead_reason_when_leaving_mort(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Un motif de mort ne doit pas survivre, trompeur, à un statut qui n'est plus `mort`."""
    paper = paper_repository.create(make_paper_analysis_request())
    paper_repository.set_status(paper.sheet.id, TriageStatus.MORT, "Marché inaccessible")

    reopened = paper_repository.set_status(paper.sheet.id, TriageStatus.EN_TEST)

    assert reopened.dead_reason == ""


def test_testability_score_is_computed_on_read_not_stored(
    paper_repository: PaperRepository,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Le score de testabilité accompagne toujours le `PaperRecord` lu."""
    record = paper_repository.create(make_paper_analysis_request())

    assert 0.0 <= record.testability_score <= 1.0


def test_deleting_a_paper_via_raw_sql_is_a_normal_row_delete(
    paper_repository: PaperRepository,
    papers_db_path: Path,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
) -> None:
    """Contrairement au registre d'essais (I1) et au journal holdout (I3), la table papers
    n'est volontairement pas append-only : un `DELETE` brut réussit et le papier disparaît."""
    paper = paper_repository.create(make_paper_analysis_request())

    with sqlite3.connect(papers_db_path) as raw_conn:
        raw_conn.execute("DELETE FROM papers WHERE id = ?", (paper.sheet.id,))
        raw_conn.commit()

    assert paper_repository.get(paper.sheet.id) is None
