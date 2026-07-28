"""Tests de edgelab.data.lockbox (I3)."""

import sqlite3
from pathlib import Path

import pytest
from edgelab.data.lockbox import (
    RED_FLAG_THRESHOLD,
    HoldoutAccessDeniedError,
    HoldoutLockbox,
)


def test_access_without_reason_is_denied(lockbox: HoldoutLockbox) -> None:
    """Critère d'acceptation Phase 0 : l'accès holdout sans raison écrite lève."""
    with pytest.raises(HoldoutAccessDeniedError):
        lockbox.access("orb-fade-v1", "")


def test_access_with_only_whitespace_reason_is_denied(lockbox: HoldoutLockbox) -> None:
    """Une raison composée uniquement d'espaces ne compte pas comme une justification."""
    with pytest.raises(HoldoutAccessDeniedError):
        lockbox.access("orb-fade-v1", "   ")


def test_access_with_reason_increments_and_persists_counter(lockbox_db_path: Path) -> None:
    """Critère d'acceptation Phase 0 : avec raison, le compteur s'incrémente et persiste."""
    with HoldoutLockbox(lockbox_db_path) as box:
        count = box.access("orb-fade-v1", "vérification finale avant financement")
    assert count == 1

    with HoldoutLockbox(lockbox_db_path) as reopened_box:
        assert reopened_box.access_count("orb-fade-v1") == 1


def test_access_count_increments_across_calls(lockbox: HoldoutLockbox) -> None:
    """Chaque accès supplémentaire fait progresser le compteur."""
    lockbox.access("orb-fade-v1", "premier accès")
    second_count = lockbox.access("orb-fade-v1", "second accès")

    assert second_count == 2


def test_access_count_is_scoped_per_strategy(lockbox: HoldoutLockbox) -> None:
    """Le compteur d'une stratégie n'est pas affecté par les accès d'une autre."""
    lockbox.access("strategy-a", "raison a")
    lockbox.access("strategy-b", "raison b")

    assert lockbox.access_count("strategy-a") == 1
    assert lockbox.access_count("strategy-b") == 1


def test_is_flagged_below_threshold(lockbox: HoldoutLockbox) -> None:
    """En dessous du seuil, la stratégie n'est pas signalée."""
    for _ in range(RED_FLAG_THRESHOLD - 1):
        lockbox.access("orb-fade-v1", "consultation")

    assert lockbox.is_flagged("orb-fade-v1") is False


def test_is_flagged_at_threshold(lockbox: HoldoutLockbox) -> None:
    """I3 : trois accès déclenchent le drapeau rouge."""
    for _ in range(RED_FLAG_THRESHOLD):
        lockbox.access("orb-fade-v1", "consultation")

    assert lockbox.is_flagged("orb-fade-v1") is True


def test_access_log_records_reason_and_order(lockbox: HoldoutLockbox) -> None:
    """Le journal conserve la raison de chaque accès, dans l'ordre chronologique."""
    lockbox.access("orb-fade-v1", "premier accès")
    lockbox.access("orb-fade-v1", "second accès")

    log = lockbox.access_log("orb-fade-v1")

    assert [entry.reason for entry in log] == ["premier accès", "second accès"]


def test_deleting_an_access_record_via_raw_sql_is_rejected(
    lockbox: HoldoutLockbox, lockbox_db_path: Path
) -> None:
    """Le journal d'accès est append-only, comme le registre d'essais."""
    lockbox.access("orb-fade-v1", "raison")

    with (
        sqlite3.connect(lockbox_db_path) as raw_conn,
        pytest.raises(sqlite3.IntegrityError),
    ):
        raw_conn.execute("DELETE FROM holdout_access WHERE strategy_id = ?", ("orb-fade-v1",))
