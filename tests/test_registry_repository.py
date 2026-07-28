"""Tests de edgelab.registry.repository (I1)."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository, TrialRepositoryError


def test_record_then_get_roundtrips_the_trial(
    trial_repository: TrialRepository, make_trial: Callable[..., Trial]
) -> None:
    """Un essai enregistré est relisible tel quel via `get`."""
    trial = make_trial()

    trial_repository.record(trial)
    retrieved = trial_repository.get(trial.id)

    assert retrieved == trial


def test_get_returns_none_for_unknown_id(trial_repository: TrialRepository) -> None:
    """`get` sur un id inconnu renvoie `None`, pas une exception."""
    assert trial_repository.get("does-not-exist") is None


def test_list_trials_orders_most_recent_first(
    trial_repository: TrialRepository, make_trial: Callable[..., Trial]
) -> None:
    """`list_trials` trie du plus récent au plus ancien."""
    older = make_trial(id="older", created_at=datetime(2024, 1, 1, tzinfo=UTC))
    newer = make_trial(id="newer", created_at=datetime(2024, 1, 2, tzinfo=UTC))
    trial_repository.record(older)
    trial_repository.record(newer)

    trials = trial_repository.list_trials()

    assert [trial.id for trial in trials] == ["newer", "older"]


def test_record_rejects_duplicate_id(
    trial_repository: TrialRepository, make_trial: Callable[..., Trial]
) -> None:
    """Deux essais avec le même id ne peuvent pas coexister."""
    trial = make_trial()
    trial_repository.record(trial)

    with pytest.raises(TrialRepositoryError):
        trial_repository.record(trial)


def test_deleting_a_trial_via_raw_sql_is_rejected(
    trial_repository: TrialRepository,
    make_trial: Callable[..., Trial],
    registry_db_path: Path,
) -> None:
    """Critère d'acceptation Phase 0 : supprimer un essai lève, même en SQL brut."""
    trial = make_trial()
    trial_repository.record(trial)

    with sqlite3.connect(registry_db_path) as raw_conn, pytest.raises(sqlite3.IntegrityError):
        raw_conn.execute("DELETE FROM trials WHERE id = ?", (trial.id,))


def test_updating_a_trial_via_raw_sql_is_rejected(
    trial_repository: TrialRepository,
    make_trial: Callable[..., Trial],
    registry_db_path: Path,
) -> None:
    """Une tentative d'UPDATE brut sur un essai existant lève également (I1)."""
    trial = make_trial()
    trial_repository.record(trial)

    with sqlite3.connect(registry_db_path) as raw_conn, pytest.raises(sqlite3.IntegrityError):
        raw_conn.execute("UPDATE trials SET note = 'edited' WHERE id = ?", (trial.id,))
