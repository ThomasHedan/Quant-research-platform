"""Persistance des datasets ingérés : barres en Parquet, manifestes dans DuckDB.

Un manifeste déjà enregistré ne se réécrit pas : `DatasetStore.save` lève si
`dataset_id` existe déjà, dans le même esprit que le registre d'essais (I1)
— une ré-ingestion corrigée est un nouveau dataset, pas une mutation
silencieuse de l'ancien.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import polars as pl

from edgelab.data.manifest import DatasetManifest

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_manifests (
    dataset_id TEXT PRIMARY KEY,
    instrument_symbol TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    manifest_json TEXT NOT NULL
);
"""


class DatasetAlreadyExistsError(RuntimeError):
    """Levée quand un `dataset_id` déjà présent dans le store est réécrit."""


class DatasetStore:
    """Catalogue DuckDB des manifestes de dataset, barres persistées en Parquet."""

    def __init__(self, catalog_path: Path | str, bars_dir: Path | str) -> None:
        self._catalog_path = str(catalog_path)
        self._bars_dir = Path(bars_dir)
        self._bars_dir.mkdir(parents=True, exist_ok=True)
        if self._catalog_path != ":memory:":
            Path(self._catalog_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(self._catalog_path)
        self._conn.execute(_SCHEMA)

    def close(self) -> None:
        """Ferme la connexion DuckDB sous-jacente."""
        self._conn.close()

    def __enter__(self) -> DatasetStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _bars_path(self, dataset_id: str) -> Path:
        return self._bars_dir / f"{dataset_id}.parquet"

    def save(self, manifest: DatasetManifest, bars: pl.DataFrame) -> None:
        """Persiste les barres en Parquet et le manifeste dans le catalogue DuckDB.

        Raises:
            DatasetAlreadyExistsError: si `manifest.dataset_id` est déjà enregistré.
        """
        existing = self._conn.execute(
            "SELECT 1 FROM dataset_manifests WHERE dataset_id = ?", [manifest.dataset_id]
        ).fetchone()
        if existing is not None:
            raise DatasetAlreadyExistsError(f"dataset '{manifest.dataset_id}' already exists")

        bars.write_parquet(self._bars_path(manifest.dataset_id))
        self._conn.execute(
            "INSERT INTO dataset_manifests VALUES (?, ?, ?, ?, ?, ?)",
            [
                manifest.dataset_id,
                manifest.instrument_symbol,
                manifest.source,
                manifest.status.value,
                manifest.created_at.isoformat(),
                manifest.model_dump_json(),
            ],
        )
        logger.info(
            "dataset stored id=%s instrument=%s status=%s",
            manifest.dataset_id,
            manifest.instrument_symbol,
            manifest.status.value,
        )

    def load_manifest(self, dataset_id: str) -> DatasetManifest | None:
        """Renvoie le manifeste `dataset_id`, ou `None` s'il n'existe pas."""
        row = self._conn.execute(
            "SELECT manifest_json FROM dataset_manifests WHERE dataset_id = ?", [dataset_id]
        ).fetchone()
        return None if row is None else DatasetManifest.model_validate_json(row[0])

    def load_bars(self, dataset_id: str) -> pl.DataFrame:
        """Charge les barres du dataset `dataset_id` depuis le Parquet."""
        return pl.read_parquet(self._bars_path(dataset_id))

    def list_manifests(self, *, instrument_symbol: str | None = None) -> list[DatasetManifest]:
        """Liste les manifestes, du plus récent au plus ancien, filtrables par instrument."""
        if instrument_symbol is None:
            rows = self._conn.execute(
                "SELECT manifest_json FROM dataset_manifests ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT manifest_json FROM dataset_manifests "
                "WHERE instrument_symbol = ? ORDER BY created_at DESC",
                [instrument_symbol],
            ).fetchall()
        return [DatasetManifest.model_validate_json(row[0]) for row in rows]
