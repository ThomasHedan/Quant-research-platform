"""Pipeline d'ingestion générique : barres -> contrôle d'intégrité -> manifeste -> store.

`ingest_bars` est le cœur partagé par toutes les sources (CSV, Parquet,
Dukascopy, futures continus) : il ne fait *jamais* le choix à la place de
l'appelant de considérer un dataset en échec comme utilisable. Le contrôle
d'intégrité tourne toujours, son verdict fixe `status`, et un dataset
`quarantine` est stocké (il reste consultable pour diagnostic) mais
`ensure_backtest_ready` le refusera.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, cast

import polars as pl

from edgelab.data.dukascopy import Fetcher, aggregate_ticks_to_bars, fetch_day_ticks
from edgelab.data.futures import FuturesContract, splice_continuous_future
from edgelab.data.integrity import run_integrity_checks
from edgelab.data.manifest import (
    DatasetManifest,
    DatasetPartition,
    DatasetStatus,
    RollMethod,
)
from edgelab.data.store import DatasetStore
from edgelab.registry.hashing import hash_bytes
from edgelab.universe.instrument import Instrument

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

REQUIRED_BAR_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def ingest_bars(  # noqa: PLR0913 — chaque paramètre est une décision explicite requise (I3/Phase 1)
    bars: pl.DataFrame,
    *,
    instrument: Instrument,
    source: str,
    frequency: timedelta,
    partition: DatasetPartition,
    store: DatasetStore,
    roll_method: RollMethod | None = None,
) -> DatasetManifest:
    """Ingère des barres déjà chargées : contrôle, manifeste, persistance.

    `bars` doit contenir les colonnes `REQUIRED_BAR_COLUMNS`, triées par
    `timestamp` croissant, en UTC.

    Raises:
        ValueError: si `bars` est vide ou manque une colonne requise.
    """
    if bars.is_empty():
        raise ValueError("cannot ingest an empty dataset")
    missing = set(REQUIRED_BAR_COLUMNS) - set(bars.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")

    bars = bars.sort("timestamp")
    start = cast(datetime, bars["timestamp"].min())
    end = cast(datetime, bars["timestamp"].max())

    report = run_integrity_checks(bars, instrument.session_calendar, frequency=frequency)
    status = DatasetStatus.OK if report.is_clean else DatasetStatus.QUARANTINE
    if status is DatasetStatus.QUARANTINE:
        logger.warning(
            "dataset quarantined instrument=%s source=%s: %s",
            instrument.symbol,
            source,
            report.summary(),
        )

    dataset_id = uuid.uuid4().hex
    manifest_hash = hash_bytes(
        f"{instrument.symbol}:{source}:{start}:{end}:{instrument.session_calendar.timezone}:"
        f"{roll_method}:{partition.research_end}:{partition.validation_end}".encode()
    )
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        instrument_symbol=instrument.symbol,
        source=source,
        start=start,
        end=end,
        timezone=instrument.session_calendar.timezone,
        roll_method=roll_method,
        partition=partition,
        integrity_report=report,
        status=status,
        manifest_hash=manifest_hash,
    )
    store.save(manifest, bars)
    return manifest


def ingest_csv(  # noqa: PLR0913 — chaque paramètre est une décision explicite requise
    path: Path,
    *,
    instrument: Instrument,
    frequency: timedelta,
    partition: DatasetPartition,
    store: DatasetStore,
    timestamp_column: str = "timestamp",
) -> DatasetManifest:
    """Ingère un CSV générique (colonnes `REQUIRED_BAR_COLUMNS`) pour un instrument.

    Le CSV n'est jamais un future continu : `roll_method` n'est pas
    applicable ici (voir `ingest_futures_continuous`).
    """
    bars = pl.read_csv(path, try_parse_dates=True)
    if timestamp_column != "timestamp":
        bars = bars.rename({timestamp_column: "timestamp"})
    return ingest_bars(
        bars,
        instrument=instrument,
        source="csv",
        frequency=frequency,
        partition=partition,
        store=store,
        roll_method=None,
    )


def ingest_parquet(
    path: Path,
    *,
    instrument: Instrument,
    frequency: timedelta,
    partition: DatasetPartition,
    store: DatasetStore,
) -> DatasetManifest:
    """Ingère un Parquet générique (colonnes `REQUIRED_BAR_COLUMNS`) pour un instrument."""
    bars = pl.read_parquet(path)
    return ingest_bars(
        bars,
        instrument=instrument,
        source="parquet",
        frequency=frequency,
        partition=partition,
        store=store,
        roll_method=None,
    )


def ingest_futures_continuous(  # noqa: PLR0913 — chaque paramètre est une décision explicite requise
    contracts: list[FuturesContract],
    *,
    instrument: Instrument,
    frequency: timedelta,
    partition: DatasetPartition,
    store: DatasetStore,
    roll_method: RollMethod,
) -> DatasetManifest:
    """Raccorde des contrats futures puis ingère la série continue résultante.

    `roll_method` n'a volontairement pas de valeur par défaut : voir
    `edgelab.data.futures`.
    """
    bars = splice_continuous_future(contracts, roll_method=roll_method)
    return ingest_bars(
        bars,
        instrument=instrument,
        source="futures_continuous",
        frequency=frequency,
        partition=partition,
        store=store,
        roll_method=roll_method,
    )


def ingest_dukascopy_day(  # noqa: PLR0913 — chaque paramètre est une décision explicite requise
    symbol: str,
    day: date,
    *,
    instrument: Instrument,
    frequency: timedelta,
    partition: DatasetPartition,
    store: DatasetStore,
    fetcher: Fetcher,
) -> DatasetManifest:
    """Récupère un jour de ticks Dukascopy, les agrège en barres, et les ingère.

    `point_value` (conversion prix entier -> prix réel) est dérivé de
    `instrument.price_decimals` (`10 ** price_decimals`), pas d'un défaut
    arbitraire : c'est la convention Dukascopy pour tout instrument FX.
    """
    point_value = 10.0**instrument.price_decimals
    ticks = fetch_day_ticks(symbol, day, point_value=point_value, fetcher=fetcher)
    bars = aggregate_ticks_to_bars(ticks, frequency)
    return ingest_bars(
        bars,
        instrument=instrument,
        source="dukascopy",
        frequency=frequency,
        partition=partition,
        store=store,
        roll_method=None,
    )
