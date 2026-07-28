"""Tests des commandes `edgelab paper *` (Phase 7)."""

from collections.abc import Callable
from pathlib import Path

from edgelab.cli import app
from edgelab.papers.models import HypothesisDraftRequest, PaperAnalysisRequest
from typer.testing import CliRunner

runner = CliRunner()


def _write_json(tmp_path: Path, name: str, payload: str) -> Path:
    path = tmp_path / name
    path.write_text(payload, encoding="utf-8")
    return path


def test_paper_prompt_prints_the_static_analysis_prompt() -> None:
    """`paper prompt` affiche le prompt copiable, sans toucher au stockage."""
    result = runner.invoke(app, ["paper", "prompt"])

    assert result.exit_code == 0
    assert "language_source" in result.stdout


def test_paper_add_creates_a_paper_from_a_json_file(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """Un JSON valide crée une fiche et rapporte son score de testabilité."""
    db_path = tmp_path / "papers.sqlite3"
    json_path = _write_json(tmp_path, "paper.json", make_paper_analysis_request().model_dump_json())

    result = runner.invoke(app, ["paper", "add", str(json_path), "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "papier créé" in result.stdout
    assert "testabilité=" in result.stdout


def test_paper_add_reads_from_stdin_when_source_is_a_dash(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """`-` comme source lit le JSON depuis stdin, sans fichier intermédiaire."""
    db_path = tmp_path / "papers.sqlite3"
    payload = make_paper_analysis_request().model_dump_json()

    result = runner.invoke(app, ["paper", "add", "-", "--db-path", str(db_path)], input=payload)

    assert result.exit_code == 0
    assert "papier créé" in result.stdout


def test_paper_add_rejects_invalid_json(tmp_path: Path) -> None:
    """Un JSON invalide échoue proprement, sans traceback brut."""
    db_path = tmp_path / "papers.sqlite3"
    json_path = _write_json(tmp_path, "bad.json", "{not valid json")

    result = runner.invoke(app, ["paper", "add", str(json_path), "--db-path", str(db_path)])

    assert result.exit_code == 1
    assert "JSON invalide" in result.output


def test_paper_list_reports_no_papers_on_empty_store(tmp_path: Path) -> None:
    """Un stockage vide affiche un message clair plutôt qu'une liste vide silencieuse."""
    db_path = tmp_path / "papers.sqlite3"

    result = runner.invoke(app, ["paper", "list", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "Aucun papier" in result.stdout


def test_paper_list_shows_a_created_paper(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """Un papier créé apparaît dans `paper list`."""
    db_path = tmp_path / "papers.sqlite3"
    json_path = _write_json(
        tmp_path,
        "paper.json",
        make_paper_analysis_request(title="Titre Distinctif").model_dump_json(),
    )
    runner.invoke(app, ["paper", "add", str(json_path), "--db-path", str(db_path)])

    result = runner.invoke(app, ["paper", "list", "--db-path", str(db_path)])

    assert "Titre Distinctif" in result.stdout


def test_paper_show_prints_full_detail(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """`paper show` affiche le détail complet, y compris les champs imbriqués."""
    db_path = tmp_path / "papers.sqlite3"
    json_path = _write_json(tmp_path, "paper.json", make_paper_analysis_request().model_dump_json())
    add_result = runner.invoke(app, ["paper", "add", str(json_path), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]

    result = runner.invoke(app, ["paper", "show", paper_id, "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert paper_id in result.stdout
    assert "testability_score" in result.stdout


def test_paper_show_exits_with_error_for_unknown_id(tmp_path: Path) -> None:
    """`paper show` sur un id inconnu sort en erreur, pas en silence."""
    db_path = tmp_path / "papers.sqlite3"

    result = runner.invoke(app, ["paper", "show", "does-not-exist", "--db-path", str(db_path)])

    assert result.exit_code == 1


def test_paper_hypothesis_prompt_embeds_the_paper_fiche(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """Le prompt personnalisé embarque bien la fiche du papier concerné."""
    db_path = tmp_path / "papers.sqlite3"
    json_path = _write_json(
        tmp_path,
        "paper.json",
        make_paper_analysis_request(title="Titre Unique XYZ").model_dump_json(),
    )
    add_result = runner.invoke(app, ["paper", "add", str(json_path), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]

    result = runner.invoke(app, ["paper", "hypothesis-prompt", paper_id, "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "Titre Unique XYZ" in result.stdout


def test_paper_hypothesis_prompt_exits_with_error_for_unknown_id(tmp_path: Path) -> None:
    """Demander le prompt d'un papier inconnu échoue explicitement."""
    db_path = tmp_path / "papers.sqlite3"

    result = runner.invoke(
        app, ["paper", "hypothesis-prompt", "does-not-exist", "--db-path", str(db_path)]
    )

    assert result.exit_code == 1


def test_paper_hypothesis_attaches_a_valid_draft(
    tmp_path: Path,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """Un brouillon valide fait avancer le papier à `hypothese_ecrite`."""
    db_path = tmp_path / "papers.sqlite3"
    paper_json = _write_json(
        tmp_path, "paper.json", make_paper_analysis_request().model_dump_json()
    )
    add_result = runner.invoke(app, ["paper", "add", str(paper_json), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]
    hyp_json = _write_json(tmp_path, "hyp.json", make_hypothesis_draft_request().model_dump_json())

    result = runner.invoke(
        app, ["paper", "hypothesis", paper_id, str(hyp_json), "--db-path", str(db_path)]
    )

    assert result.exit_code == 0
    assert "hypothese_ecrite" in result.stdout


def test_paper_hypothesis_rejects_an_unfalsifiable_draft(
    tmp_path: Path,
    make_paper_analysis_request: Callable[..., PaperAnalysisRequest],
    make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest],
) -> None:
    """I2 : un brouillon dont `where_it_should_not_work` est vide est refusé, pas de traceback."""
    db_path = tmp_path / "papers.sqlite3"
    paper_json = _write_json(
        tmp_path, "paper.json", make_paper_analysis_request().model_dump_json()
    )
    add_result = runner.invoke(app, ["paper", "add", str(paper_json), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]
    unfalsifiable = make_hypothesis_draft_request(where_it_should_not_work="")
    hyp_json = _write_json(tmp_path, "hyp.json", unfalsifiable.model_dump_json())

    result = runner.invoke(
        app, ["paper", "hypothesis", paper_id, str(hyp_json), "--db-path", str(db_path)]
    )

    assert result.exit_code == 1
    assert "I2" in result.output


def test_paper_hypothesis_rejects_invalid_json(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """Un JSON de brouillon invalide échoue proprement, sans traceback brut."""
    db_path = tmp_path / "papers.sqlite3"
    paper_json = _write_json(
        tmp_path, "paper.json", make_paper_analysis_request().model_dump_json()
    )
    add_result = runner.invoke(app, ["paper", "add", str(paper_json), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]
    bad_json = _write_json(tmp_path, "bad.json", "{not valid json")

    result = runner.invoke(
        app, ["paper", "hypothesis", paper_id, str(bad_json), "--db-path", str(db_path)]
    )

    assert result.exit_code == 1
    assert "JSON invalide" in result.output


def test_paper_hypothesis_exits_with_error_for_unknown_paper(
    tmp_path: Path, make_hypothesis_draft_request: Callable[..., HypothesisDraftRequest]
) -> None:
    """Rattacher un brouillon à un papier inconnu échoue explicitement."""
    db_path = tmp_path / "papers.sqlite3"
    hyp_json = _write_json(tmp_path, "hyp.json", make_hypothesis_draft_request().model_dump_json())

    result = runner.invoke(
        app, ["paper", "hypothesis", "does-not-exist", str(hyp_json), "--db-path", str(db_path)]
    )

    assert result.exit_code == 1


def test_paper_set_status_updates_the_triage_status(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """Un statut sans exigence de motif se met à jour directement."""
    db_path = tmp_path / "papers.sqlite3"
    paper_json = _write_json(
        tmp_path, "paper.json", make_paper_analysis_request().model_dump_json()
    )
    add_result = runner.invoke(app, ["paper", "add", str(paper_json), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]

    result = runner.invoke(
        app, ["paper", "set-status", paper_id, "en_test", "--db-path", str(db_path)]
    )

    assert result.exit_code == 0
    assert "en_test" in result.stdout


def test_paper_set_status_mort_without_reason_is_rejected(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """`mort` sans `--reason` échoue explicitement, sans traceback."""
    db_path = tmp_path / "papers.sqlite3"
    paper_json = _write_json(
        tmp_path, "paper.json", make_paper_analysis_request().model_dump_json()
    )
    add_result = runner.invoke(app, ["paper", "add", str(paper_json), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]

    result = runner.invoke(
        app, ["paper", "set-status", paper_id, "mort", "--db-path", str(db_path)]
    )

    assert result.exit_code == 1


def test_paper_set_status_mort_with_reason_succeeds(
    tmp_path: Path, make_paper_analysis_request: Callable[..., PaperAnalysisRequest]
) -> None:
    """`mort` avec un motif écrit réussit."""
    db_path = tmp_path / "papers.sqlite3"
    paper_json = _write_json(
        tmp_path, "paper.json", make_paper_analysis_request().model_dump_json()
    )
    add_result = runner.invoke(app, ["paper", "add", str(paper_json), "--db-path", str(db_path)])
    paper_id = add_result.stdout.split()[3]

    result = runner.invoke(
        app,
        [
            "paper",
            "set-status",
            paper_id,
            "mort",
            "--reason",
            "Marché inaccessible",
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0


def test_paper_set_status_exits_with_error_for_unknown_paper(tmp_path: Path) -> None:
    """Changer le statut d'un papier inconnu échoue explicitement."""
    db_path = tmp_path / "papers.sqlite3"

    result = runner.invoke(
        app, ["paper", "set-status", "does-not-exist", "en_test", "--db-path", str(db_path)]
    )

    assert result.exit_code == 1
