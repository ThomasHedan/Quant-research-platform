"""Tests de edgelab.data.manifest."""

from datetime import UTC, datetime

import pytest
from edgelab.data.integrity import IntegrityIssue, IntegrityReport, IntegritySeverity
from edgelab.data.manifest import (
    DatasetManifest,
    DatasetPartition,
    DatasetStatus,
    QuarantinedDatasetError,
    ensure_backtest_ready,
)
from pydantic import ValidationError


def test_dataset_partition_rejects_research_end_after_validation_end() -> None:
    """`research_end` doit précéder strictement `validation_end`."""
    with pytest.raises(ValueError, match="research_end"):
        DatasetPartition(
            research_end=datetime(2024, 2, 1, tzinfo=UTC),
            validation_end=datetime(2024, 1, 1, tzinfo=UTC),
        )


def test_dataset_partition_rejects_equal_bounds() -> None:
    """`research_end` == `validation_end` ne laisse aucune fenêtre de validation."""
    same = datetime(2024, 1, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="research_end"):
        DatasetPartition(research_end=same, validation_end=same)


def _make_manifest(
    status: DatasetStatus, issues: tuple[IntegrityIssue, ...] = ()
) -> DatasetManifest:
    return DatasetManifest(
        dataset_id="ds1",
        instrument_symbol="EURUSD",
        source="csv",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
        timezone="UTC",
        roll_method=None,
        partition=DatasetPartition(
            research_end=datetime(2024, 1, 1, 12, tzinfo=UTC),
            validation_end=datetime(2024, 1, 1, 18, tzinfo=UTC),
        ),
        integrity_report=IntegrityReport(issues=issues),
        status=status,
        manifest_hash="abc123",
    )


def test_ensure_backtest_ready_passes_for_an_ok_dataset() -> None:
    """Un dataset `ok` ne lève pas — le backtest peut démarrer."""
    ensure_backtest_ready(_make_manifest(DatasetStatus.OK))


def test_ensure_backtest_ready_raises_for_a_quarantined_dataset() -> None:
    """Critère d'acceptation Phase 1 : le backtester refuse un dataset en quarantaine."""
    issue = IntegrityIssue(
        kind="session_gaps", severity=IntegritySeverity.CRITICAL, message="gap", count=3
    )

    with pytest.raises(QuarantinedDatasetError, match="ds1"):
        ensure_backtest_ready(_make_manifest(DatasetStatus.QUARANTINE, (issue,)))


def test_manifest_is_frozen() -> None:
    """Un `DatasetManifest` est immuable, comme un `Trial` (I1)."""
    manifest = _make_manifest(DatasetStatus.OK)

    with pytest.raises(ValidationError):
        manifest.status = DatasetStatus.QUARANTINE  # type: ignore[misc]
