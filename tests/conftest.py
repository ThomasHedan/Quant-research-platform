"""Fixtures et factories partagées entre tous les modules de test.

Convention du projet : exercer les vraies dépendances (SQLite `sqlite://`,
`tmp_path`, DuckDB en mémoire) plutôt que de mocker. Les fixtures ajoutées
ici doivent rester génériques ; les factories spécifiques à un module
vivent dans le `test_<module>.py` correspondant si elles ne sont utilisées
qu'une fois.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from edgelab.data.lockbox import HoldoutLockbox
from edgelab.registry.models import Trial, TrialType
from edgelab.registry.repository import TrialRepository


@pytest.fixture
def registry_db_path(tmp_path: Path) -> Path:
    """Chemin d'un registre SQLite isolé pour un test."""
    return tmp_path / "registry.sqlite3"


@pytest.fixture
def trial_repository(registry_db_path: Path) -> Iterator[TrialRepository]:
    """Un `TrialRepository` adossé à un fichier SQLite temporaire."""
    with TrialRepository(registry_db_path) as repo:
        yield repo


@pytest.fixture
def make_trial() -> Callable[..., Trial]:
    """Factory produisant un `Trial` valide, personnalisable via overrides."""

    def _make_trial(**overrides: Any) -> Trial:
        defaults: dict[str, Any] = {
            "trial_type": TrialType.EVENT_STUDY,
            "strategy_id": "orb-fade-v1",
            "code_hash": "c0de" * 16,
            "params": {"horizon": 10},
            "params_hash": "params" * 10 + "abcd",
            "dataset_hash": "data" * 16,
            "lineage_hash": "1ineage" * 9 + "abc",
        }
        defaults.update(overrides)
        return Trial(**defaults)

    return _make_trial


@pytest.fixture
def lockbox_db_path(tmp_path: Path) -> Path:
    """Chemin d'une lockbox SQLite isolée pour un test."""
    return tmp_path / "lockbox.sqlite3"


@pytest.fixture
def lockbox(lockbox_db_path: Path) -> Iterator[HoldoutLockbox]:
    """Une `HoldoutLockbox` adossée à un fichier SQLite temporaire."""
    with HoldoutLockbox(lockbox_db_path) as box:
        yield box
