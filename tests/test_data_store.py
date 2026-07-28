"""Tests de edgelab.data.store."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from edgelab.data.integrity import IntegrityReport
from edgelab.data.manifest import DatasetManifest, DatasetPartition, DatasetStatus
from edgelab.data.store import DatasetAlreadyExistsError, DatasetStore


def _make_manifest(dataset_id: str, *, instrument_symbol: str = "EURUSD") -> DatasetManifest:
    return DatasetManifest(
        dataset_id=dataset_id,
        instrument_symbol=instrument_symbol,
        source="csv",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
        timezone="UTC",
        roll_method=None,
        partition=DatasetPartition(
            research_end=datetime(2024, 1, 1, 12, tzinfo=UTC),
            validation_end=datetime(2024, 1, 1, 18, tzinfo=UTC),
        ),
        integrity_report=IntegrityReport(issues=()),
        status=DatasetStatus.OK,
        manifest_hash="abc123",
    )


def _bars() -> pl.DataFrame:
    return pl.DataFrame({"timestamp": [datetime(2024, 1, 1, tzinfo=UTC)], "close": [1.1]})


def test_save_then_load_manifest_roundtrips(dataset_store: DatasetStore) -> None:
    """Un manifeste sauvegardé est relisible tel quel."""
    manifest = _make_manifest("ds1")

    dataset_store.save(manifest, _bars())
    loaded = dataset_store.load_manifest("ds1")

    assert loaded == manifest


def test_load_manifest_returns_none_for_unknown_id(dataset_store: DatasetStore) -> None:
    """`load_manifest` sur un id inconnu renvoie `None`, pas une exception."""
    assert dataset_store.load_manifest("does-not-exist") is None


def test_save_then_load_bars_roundtrips(dataset_store: DatasetStore) -> None:
    """Les barres sauvegardées en Parquet sont relisibles telles quelles."""
    manifest = _make_manifest("ds1")
    bars = _bars()

    dataset_store.save(manifest, bars)
    loaded_bars = dataset_store.load_bars("ds1")

    assert loaded_bars.equals(bars)


def test_save_rejects_a_duplicate_dataset_id(dataset_store: DatasetStore) -> None:
    """Un `dataset_id` déjà enregistré ne peut pas être réécrit silencieusement."""
    manifest = _make_manifest("ds1")
    dataset_store.save(manifest, _bars())

    with pytest.raises(DatasetAlreadyExistsError, match="ds1"):
        dataset_store.save(manifest, _bars())


def test_list_manifests_orders_most_recent_first(dataset_store: DatasetStore) -> None:
    """`list_manifests` trie du plus récent au plus ancien."""
    older = _make_manifest("older")  # construit (et donc horodaté) en premier
    newer = _make_manifest("newer")
    dataset_store.save(older, _bars())
    dataset_store.save(newer, _bars())

    manifests = dataset_store.list_manifests()

    assert [m.dataset_id for m in manifests] == ["newer", "older"]


def test_list_manifests_filters_by_instrument_symbol(dataset_store: DatasetStore) -> None:
    """`list_manifests` filtre par instrument quand `instrument_symbol` est fourni."""
    dataset_store.save(_make_manifest("eur", instrument_symbol="EURUSD"), _bars())
    dataset_store.save(_make_manifest("gbp", instrument_symbol="GBPUSD"), _bars())

    manifests = dataset_store.list_manifests(instrument_symbol="GBPUSD")

    assert [m.dataset_id for m in manifests] == ["gbp"]


def test_store_creates_catalog_and_bars_directories(tmp_path: Path) -> None:
    """Le store crée son catalogue DuckDB et son répertoire de barres s'ils n'existent pas."""
    catalog_path = tmp_path / "nested" / "catalog.duckdb"
    bars_dir = tmp_path / "nested" / "bars"

    with DatasetStore(catalog_path, bars_dir) as store:
        store.save(_make_manifest("ds1"), _bars())

    assert catalog_path.exists()
    assert (bars_dir / "ds1.parquet").exists()
