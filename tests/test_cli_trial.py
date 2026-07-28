"""Tests des commandes `edgelab trial *` (I1, lecture seule sur le registre)."""

from collections.abc import Callable
from pathlib import Path

from edgelab.cli import app
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository
from typer.testing import CliRunner

runner = CliRunner()


def test_trial_list_reports_no_trials_on_empty_registry(tmp_path: Path) -> None:
    """Un registre vide affiche un message clair plutôt qu'un tableau vide."""
    db_path = tmp_path / "registry.sqlite3"

    result = runner.invoke(app, ["trial", "list", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert "Aucun essai" in result.stdout


def test_trial_list_shows_recorded_trial(tmp_path: Path, make_trial: Callable[..., Trial]) -> None:
    """Un essai enregistré apparaît dans la sortie de `trial list`."""
    db_path = tmp_path / "registry.sqlite3"
    trial = make_trial()
    with TrialRepository(db_path) as repo:
        repo.record(trial)

    result = runner.invoke(app, ["trial", "list", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert trial.id in result.stdout
    assert trial.strategy_id in result.stdout


def test_trial_show_prints_trial_detail(tmp_path: Path, make_trial: Callable[..., Trial]) -> None:
    """`trial show` affiche le détail complet de l'essai demandé."""
    db_path = tmp_path / "registry.sqlite3"
    trial = make_trial()
    with TrialRepository(db_path) as repo:
        repo.record(trial)

    result = runner.invoke(app, ["trial", "show", trial.id, "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert trial.lineage_hash in result.stdout


def test_trial_show_exits_with_error_for_unknown_id(tmp_path: Path) -> None:
    """`trial show` sur un id inconnu sort en erreur, pas en silence."""
    db_path = tmp_path / "registry.sqlite3"

    result = runner.invoke(app, ["trial", "show", "does-not-exist", "--db-path", str(db_path)])

    assert result.exit_code == 1
