"""Tests de edgelab.settings (stockage local des clés API)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from edgelab.settings import (
    KNOWN_CREDENTIALS,
    CredentialError,
    CredentialStore,
    describe,
    mask,
    resolve,
    validate_env_var,
)

from tests.test_constants import SAMPLE_API_KEY

_ENV_VAR = "LSE_API_KEY"


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise toute clé exportée dans l'environnement réel de la machine de test."""
    monkeypatch.delenv(_ENV_VAR, raising=False)


@pytest.fixture
def store(tmp_path: Path) -> CredentialStore:
    """Un store de clés adossé à un fichier temporaire."""
    return CredentialStore(tmp_path / "state" / "credentials.env")


# --- masquage ----------------------------------------------------------------


def test_mask_keeps_only_the_last_four_characters() -> None:
    """Une clé masquée laisse juste de quoi la reconnaître, jamais de quoi l'utiliser."""
    masked = mask("sk-live-abcdefgh1234")

    assert masked.endswith("1234")
    assert "abcdefgh" not in masked
    assert len(masked) == len("sk-live-abcdefgh1234")


def test_mask_reveals_nothing_of_a_short_secret() -> None:
    """Sur une clé courte, révéler quatre caractères serait une fuite, pas un indice."""
    assert mask("abc123") == "••••••"


# --- validation des noms -----------------------------------------------------


@pytest.mark.parametrize("name", ["LSE_API_KEY", "A", "X9_Z"])
def test_validate_env_var_accepts_environment_variable_names(name: str) -> None:
    """Un nom en majuscules, chiffres et tirets bas est accepté."""
    assert validate_env_var(f" {name} ") == name


@pytest.mark.parametrize("name", ["lse_api_key", "9KEY", "MY-KEY", "", "MY KEY"])
def test_validate_env_var_rejects_anything_else(name: str) -> None:
    """Tout ce qui ne serait pas sourçable dans un shell est refusé."""
    with pytest.raises(CredentialError, match="nom de clé invalide"):
        validate_env_var(name)


# --- store -------------------------------------------------------------------


def test_set_then_resolve_round_trips_the_secret(store: CredentialStore) -> None:
    """Une clé écrite est relue telle quelle par `resolve`."""
    store.set(_ENV_VAR, SAMPLE_API_KEY)

    assert resolve(_ENV_VAR, store=store) == SAMPLE_API_KEY


def test_the_credentials_file_is_readable_by_its_owner_only(store: CredentialStore) -> None:
    """Le fichier de clés est en 0600 : une clé lisible par toute la machine n'est pas un secret."""
    store.set(_ENV_VAR, SAMPLE_API_KEY)

    mode = stat.S_IMODE(store.path.stat().st_mode)

    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_set_replaces_an_existing_key_without_duplicating_it(store: CredentialStore) -> None:
    """Réécrire une clé remplace la ligne au lieu d'en ajouter une seconde."""
    store.set(_ENV_VAR, "premiere-valeur-longue")
    store.set(_ENV_VAR, "seconde-valeur-longue")

    assert store.read_all() == {_ENV_VAR: "seconde-valeur-longue"}


def test_set_rejects_an_empty_value(store: CredentialStore) -> None:
    """Une valeur vide est une suppression déguisée : elle est refusée explicitement."""
    with pytest.raises(CredentialError, match="valeur vide"):
        store.set(_ENV_VAR, "   ")


def test_unset_removes_the_key_and_reports_whether_it_existed(store: CredentialStore) -> None:
    """Supprimer une clé absente n'est pas une erreur, mais renvoie `False`."""
    store.set(_ENV_VAR, SAMPLE_API_KEY)

    assert store.unset(_ENV_VAR) is True
    assert store.unset(_ENV_VAR) is False
    assert store.read_all() == {}


def test_read_all_ignores_comments_and_malformed_lines(store: CredentialStore) -> None:
    """Le fichier est éditable à la main : une ligne de travers n'invalide pas les autres."""
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        '# commentaire\n\nune ligne sans egal\nlowercase=ignoree\nLSE_API_KEY="valeur"\n',
        encoding="utf-8",
    )

    assert store.read_all() == {_ENV_VAR: "valeur"}


def test_read_all_is_empty_when_no_file_exists(store: CredentialStore) -> None:
    """Une installation neuve n'a pas de fichier de clés, et ce n'est pas une erreur."""
    assert store.read_all() == {}


# --- précédence --------------------------------------------------------------


def test_the_environment_variable_wins_over_the_file(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une clé exportée décide, même si le fichier en contient une autre.

    L'inverse rendrait un déploiement imprévisible : on croit configurer par
    l'environnement et un fichier oublié décide à sa place.
    """
    store.set(_ENV_VAR, "valeur-du-fichier")
    monkeypatch.setenv(_ENV_VAR, "valeur-de-l-environnement")

    assert resolve(_ENV_VAR, store=store) == "valeur-de-l-environnement"


def test_resolve_returns_none_when_nothing_is_configured(store: CredentialStore) -> None:
    """Sans clé nulle part, `resolve` renvoie None plutôt qu'une chaîne vide."""
    assert resolve(_ENV_VAR, store=store) is None


def test_resolve_ignores_a_blank_environment_variable(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une variable exportée mais vide ne masque pas la clé du fichier."""
    store.set(_ENV_VAR, SAMPLE_API_KEY)
    monkeypatch.setenv(_ENV_VAR, "  ")

    assert resolve(_ENV_VAR, store=store) == SAMPLE_API_KEY


# --- describe ----------------------------------------------------------------


def test_describe_never_returns_the_secret_itself(store: CredentialStore) -> None:
    """Le point entier du module : l'état est observable, la valeur ne l'est pas."""
    store.set(_ENV_VAR, SAMPLE_API_KEY)

    statuses = describe(store)

    assert SAMPLE_API_KEY not in repr(statuses)
    status = next(s for s in statuses if s.env_var == _ENV_VAR)
    assert status.configured is True
    assert status.hint == mask(SAMPLE_API_KEY)


def test_describe_lists_every_known_slot_even_when_empty(store: CredentialStore) -> None:
    """Un emplacement connu mais vide reste listé : l'UI doit pouvoir le proposer."""
    statuses = describe(store)

    assert {s.env_var for s in statuses} == {spec.env_var for spec in KNOWN_CREDENTIALS}
    assert all(s.source == "absent" and not s.configured for s in statuses)


def test_describe_reports_the_effective_source(
    store: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La provenance affichée est celle qui gagne réellement, pas celle qu'on espère."""
    store.set(_ENV_VAR, "valeur-du-fichier")
    assert next(s for s in describe(store) if s.env_var == _ENV_VAR).source == "file"

    monkeypatch.setenv(_ENV_VAR, "valeur-de-l-environnement")

    assert next(s for s in describe(store) if s.env_var == _ENV_VAR).source == "environment"


def test_describe_marks_a_user_added_key_as_read_by_nothing(store: CredentialStore) -> None:
    """Une clé rangée pour un fournisseur non branché est affichée comme telle, pas comme active."""
    store.set("POLYGON_API_KEY", SAMPLE_API_KEY)

    status = next(s for s in describe(store) if s.env_var == "POLYGON_API_KEY")

    assert status.wired is False
    assert status.configured is True
