"""Tests des commandes `edgelab config *` (clés API locales)."""

from __future__ import annotations

from pathlib import Path

import pytest
from edgelab.cli import app
from edgelab.settings import CredentialStore
from typer.testing import CliRunner

from tests.test_constants import SAMPLE_API_KEY

runner = CliRunner()
_ENV_VAR = "LSE_API_KEY"


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise toute clé exportée dans l'environnement réel de la machine de test."""
    monkeypatch.delenv(_ENV_VAR, raising=False)


@pytest.fixture
def credentials_file(tmp_path: Path) -> Path:
    """Le fichier de clés temporaire passé à chaque commande."""
    return tmp_path / "credentials.env"


def test_config_list_shows_an_empty_slot_before_anything_is_set(credentials_file: Path) -> None:
    """L'emplacement LSE est listé même vide : l'utilisateur doit savoir qu'il existe."""
    result = runner.invoke(app, ["config", "list", "--credentials-file", str(credentials_file)])

    assert result.exit_code == 0
    assert _ENV_VAR in result.stdout
    assert "source=absent" in result.stdout


def test_config_set_stores_the_key_and_never_echoes_it(credentials_file: Path) -> None:
    """La clé est enregistrée, et la sortie n'en montre que les derniers caractères."""
    result = runner.invoke(
        app,
        [
            "config",
            "set",
            _ENV_VAR,
            "--value",
            SAMPLE_API_KEY,
            "--credentials-file",
            str(credentials_file),
        ],
    )

    assert result.exit_code == 0
    assert SAMPLE_API_KEY not in result.output
    assert SAMPLE_API_KEY[-4:] in result.stdout
    assert CredentialStore(credentials_file).read_all() == {_ENV_VAR: SAMPLE_API_KEY}


def test_config_list_never_prints_a_stored_key_in_clear(credentials_file: Path) -> None:
    """Le garde-fou principal : aucune commande ne rend une clé lisible."""
    CredentialStore(credentials_file).set(_ENV_VAR, SAMPLE_API_KEY)

    result = runner.invoke(app, ["config", "list", "--credentials-file", str(credentials_file)])

    assert SAMPLE_API_KEY not in result.output
    assert "source=file" in result.stdout


def test_config_set_warns_when_the_environment_variable_would_win(
    credentials_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Écrire une clé qu'une variable exportée masquera doit être dit, pas subi."""
    monkeypatch.setenv(_ENV_VAR, "valeur-de-l-environnement")

    result = runner.invoke(
        app,
        [
            "config",
            "set",
            _ENV_VAR,
            "--value",
            SAMPLE_API_KEY,
            "--credentials-file",
            str(credentials_file),
        ],
    )

    assert result.exit_code == 0
    assert "gardera la priorité" in result.output


def test_config_set_rejects_an_invalid_name(credentials_file: Path) -> None:
    """Un nom qui ne serait pas sourçable dans un shell est refusé proprement."""
    result = runner.invoke(
        app,
        [
            "config",
            "set",
            "ma-cle",
            "--value",
            SAMPLE_API_KEY,
            "--credentials-file",
            str(credentials_file),
        ],
    )

    assert result.exit_code == 1
    assert "nom de clé invalide" in result.output


def test_config_unset_removes_a_stored_key(credentials_file: Path) -> None:
    """La suppression retire bien la clé du fichier."""
    CredentialStore(credentials_file).set(_ENV_VAR, SAMPLE_API_KEY)

    result = runner.invoke(
        app, ["config", "unset", _ENV_VAR, "--credentials-file", str(credentials_file)]
    )

    assert result.exit_code == 0
    assert CredentialStore(credentials_file).read_all() == {}


def test_config_unset_reports_a_key_that_was_not_stored(credentials_file: Path) -> None:
    """Supprimer une clé absente sort en erreur nommée plutôt qu'en succès silencieux."""
    result = runner.invoke(
        app, ["config", "unset", _ENV_VAR, "--credentials-file", str(credentials_file)]
    )

    assert result.exit_code == 1
    assert "n'était pas enregistrée" in result.output
