"""Ingestion, contrôle d'intégrité, store des données de marché et lockbox du holdout (I3)."""

from edgelab.data.dukascopy import (
    Fetcher,
    aggregate_ticks_to_bars,
    build_tick_url,
    fetch_day_ticks,
    fetch_ticks,
    http_fetcher,
    parse_bi5,
)
from edgelab.data.futures import FuturesContract, splice_continuous_future
from edgelab.data.ingest import (
    ingest_bars,
    ingest_csv,
    ingest_dukascopy_day,
    ingest_futures_continuous,
    ingest_parquet,
)
from edgelab.data.integrity import (
    IntegrityIssue,
    IntegrityReport,
    IntegritySeverity,
    run_integrity_checks,
)
from edgelab.data.lockbox import (
    RED_FLAG_THRESHOLD,
    HoldoutAccessDeniedError,
    HoldoutAccessRecord,
    HoldoutLockbox,
)
from edgelab.data.manifest import (
    DatasetManifest,
    DatasetPartition,
    DatasetStatus,
    QuarantinedDatasetError,
    RollMethod,
    ensure_backtest_ready,
)
from edgelab.data.store import DatasetAlreadyExistsError, DatasetStore

__all__ = [
    "RED_FLAG_THRESHOLD",
    "DatasetAlreadyExistsError",
    "DatasetManifest",
    "DatasetPartition",
    "DatasetStatus",
    "DatasetStore",
    "Fetcher",
    "FuturesContract",
    "HoldoutAccessDeniedError",
    "HoldoutAccessRecord",
    "HoldoutLockbox",
    "IntegrityIssue",
    "IntegrityReport",
    "IntegritySeverity",
    "QuarantinedDatasetError",
    "RollMethod",
    "aggregate_ticks_to_bars",
    "build_tick_url",
    "ensure_backtest_ready",
    "fetch_day_ticks",
    "fetch_ticks",
    "http_fetcher",
    "ingest_bars",
    "ingest_csv",
    "ingest_dukascopy_day",
    "ingest_futures_continuous",
    "ingest_parquet",
    "parse_bi5",
    "run_integrity_checks",
    "splice_continuous_future",
]
