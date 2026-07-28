"""Tests de edgelab.data.ingest (pipeline d'ingestion, Phase 1)."""

import lzma
import struct
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from edgelab.data.futures import FuturesContract
from edgelab.data.ingest import (
    REQUIRED_BAR_COLUMNS,
    ingest_bars,
    ingest_csv,
    ingest_dukascopy_day,
    ingest_futures_continuous,
    ingest_parquet,
)
from edgelab.data.manifest import DatasetPartition, DatasetStatus, RollMethod, ensure_backtest_ready
from edgelab.data.store import DatasetStore
from edgelab.universe.instrument import Instrument

FREQUENCY = timedelta(minutes=1)
START = datetime(2024, 1, 8, 0, 0, tzinfo=UTC)  # lundi
END = datetime(2024, 1, 9, 0, 0, tzinfo=UTC)


def test_ingest_bars_rejects_an_empty_dataframe(
    eurusd: Instrument, dataset_store: DatasetStore, make_partition: Callable[..., DatasetPartition]
) -> None:
    """Un dataset vide n'a rien à ingérer."""
    empty = pl.DataFrame(schema=dict.fromkeys(REQUIRED_BAR_COLUMNS, pl.Float64))
    partition = make_partition(START, START + timedelta(hours=1))

    with pytest.raises(ValueError, match="empty"):
        ingest_bars(
            empty,
            instrument=eurusd,
            source="csv",
            frequency=FREQUENCY,
            partition=partition,
            store=dataset_store,
        )


def test_ingest_bars_rejects_missing_columns(
    eurusd: Instrument, dataset_store: DatasetStore, make_partition: Callable[..., DatasetPartition]
) -> None:
    """Des colonnes manquantes sont refusées explicitement, pas silencieusement ignorées."""
    incomplete = pl.DataFrame({"timestamp": [START], "close": [1.1]})
    partition = make_partition(START, START + timedelta(hours=1))

    with pytest.raises(ValueError, match="missing required columns"):
        ingest_bars(
            incomplete,
            instrument=eurusd,
            source="csv",
            frequency=FREQUENCY,
            partition=partition,
            store=dataset_store,
        )


def test_ingest_bars_marks_a_clean_dataset_ok_and_lets_it_through(
    eurusd: Instrument,
    dataset_store: DatasetStore,
    make_clean_bars: Callable[..., pl.DataFrame],
    make_partition: Callable[..., DatasetPartition],
) -> None:
    """Critère d'acceptation Phase 1 : un dataset propre passe le garde-fou de backtest."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    partition = make_partition(START + timedelta(hours=12), START + timedelta(hours=18))

    manifest = ingest_bars(
        bars,
        instrument=eurusd,
        source="csv",
        frequency=FREQUENCY,
        partition=partition,
        store=dataset_store,
    )

    assert manifest.status is DatasetStatus.OK
    ensure_backtest_ready(manifest)  # ne doit pas lever


def test_ingest_bars_quarantines_a_dataset_with_a_session_gap(
    eurusd: Instrument,
    dataset_store: DatasetStore,
    make_clean_bars: Callable[..., pl.DataFrame],
    make_partition: Callable[..., DatasetPartition],
) -> None:
    """Critère d'acceptation Phase 1 : un trou de session artificiel met en quarantaine."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    gapped = bars.filter(
        ~pl.col("timestamp").is_between(
            datetime(2024, 1, 8, 10, 0, tzinfo=UTC),
            datetime(2024, 1, 8, 10, 30, tzinfo=UTC),
            closed="left",
        )
    )
    partition = make_partition(START + timedelta(hours=12), START + timedelta(hours=18))

    manifest = ingest_bars(
        gapped,
        instrument=eurusd,
        source="csv",
        frequency=FREQUENCY,
        partition=partition,
        store=dataset_store,
    )

    assert manifest.status is DatasetStatus.QUARANTINE


def test_identical_ingestion_inputs_produce_the_same_manifest_hash(
    eurusd: Instrument,
    dataset_store: DatasetStore,
    make_clean_bars: Callable[..., pl.DataFrame],
    make_partition: Callable[..., DatasetPartition],
) -> None:
    """Deux ingestions aux mêmes source/instrument/période/partition ont le même manifest_hash."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    partition = make_partition(START + timedelta(hours=12), START + timedelta(hours=18))

    first = ingest_bars(
        bars.clone(),
        instrument=eurusd,
        source="csv",
        frequency=FREQUENCY,
        partition=partition,
        store=dataset_store,
    )
    second = ingest_bars(
        bars.clone(),
        instrument=eurusd,
        source="csv",
        frequency=FREQUENCY,
        partition=partition,
        store=dataset_store,
    )

    assert first.manifest_hash == second.manifest_hash
    assert first.dataset_id != second.dataset_id  # deux essais distincts, jamais fusionnés


def test_ingest_csv_reads_and_ingests_a_generic_csv(
    eurusd: Instrument,
    dataset_store: DatasetStore,
    make_clean_bars: Callable[..., pl.DataFrame],
    make_partition: Callable[..., DatasetPartition],
    tmp_path: Path,
) -> None:
    """`ingest_csv` lit un CSV générique et l'ingère comme n'importe quelle source."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    csv_path = tmp_path / "eurusd.csv"
    bars.write_csv(csv_path)
    partition = make_partition(START + timedelta(hours=12), START + timedelta(hours=18))

    manifest = ingest_csv(
        csv_path,
        instrument=eurusd,
        frequency=FREQUENCY,
        partition=partition,
        store=dataset_store,
    )

    assert manifest.source == "csv"
    assert manifest.roll_method is None
    assert manifest.status is DatasetStatus.OK


def test_ingest_parquet_reads_and_ingests_a_generic_parquet(
    eurusd: Instrument,
    dataset_store: DatasetStore,
    make_clean_bars: Callable[..., pl.DataFrame],
    make_partition: Callable[..., DatasetPartition],
    tmp_path: Path,
) -> None:
    """`ingest_parquet` lit un Parquet générique et l'ingère comme n'importe quelle source."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    parquet_path = tmp_path / "eurusd.parquet"
    bars.write_parquet(parquet_path)
    partition = make_partition(START + timedelta(hours=12), START + timedelta(hours=18))

    manifest = ingest_parquet(
        parquet_path,
        instrument=eurusd,
        frequency=FREQUENCY,
        partition=partition,
        store=dataset_store,
    )

    assert manifest.source == "parquet"
    assert manifest.status is DatasetStatus.OK


def test_ingest_futures_continuous_threads_roll_method_into_the_manifest(
    es_future: Instrument,
    dataset_store: DatasetStore,
    make_partition: Callable[..., DatasetPartition],
) -> None:
    """`ingest_futures_continuous` raccorde puis ingère, en conservant `roll_method`."""
    frequency = timedelta(days=1)
    calendar = es_future.session_calendar
    timestamps_a = calendar.expected_bar_starts(
        datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC), frequency
    )
    timestamps_b = calendar.expected_bar_starts(
        datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 9, tzinfo=UTC), frequency
    )
    bars_a = pl.DataFrame(
        [(ts, 4700.0, 4701.0, 4699.0, 4700.0, 1000.0) for ts in timestamps_a],
        schema=list(REQUIRED_BAR_COLUMNS),
        orient="row",
    )
    bars_b = pl.DataFrame(
        [(ts, 4703.0, 4704.0, 4702.0, 4703.0, 1000.0) for ts in timestamps_b],
        schema=list(REQUIRED_BAR_COLUMNS),
        orient="row",
    )
    roll_date = timestamps_a[-1].date()
    contracts = [
        FuturesContract(expiry=date(2024, 3, 15), roll_date=roll_date, bars=bars_a),
        FuturesContract(expiry=date(2024, 6, 21), roll_date=timestamps_b[-1].date(), bars=bars_b),
    ]
    partition = make_partition(datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC))

    manifest = ingest_futures_continuous(
        contracts,
        instrument=es_future,
        frequency=frequency,
        partition=partition,
        store=dataset_store,
        roll_method=RollMethod.RATIO,
    )

    assert manifest.roll_method is RollMethod.RATIO
    assert manifest.source == "futures_continuous"


def test_ingest_dukascopy_day_fetches_aggregates_and_ingests(
    eurusd: Instrument,
    dataset_store: DatasetStore,
    make_partition: Callable[..., DatasetPartition],
) -> None:
    """`ingest_dukascopy_day` enchaîne fetch, agrégation en barres, puis ingestion."""
    tick_struct = struct.Struct(">IIIff")
    one_tick = tick_struct.pack(0, 108500, 108480, 1.0, 1.0)
    compressed = lzma.compress(one_tick, format=lzma.FORMAT_ALONE)

    def fake_fetcher(url: str) -> bytes:
        return compressed

    day = date(2024, 1, 8)
    partition = make_partition(
        datetime(2024, 1, 8, 12, tzinfo=UTC), datetime(2024, 1, 8, 18, tzinfo=UTC)
    )

    manifest = ingest_dukascopy_day(
        "EURUSD",
        day,
        instrument=eurusd,
        frequency=timedelta(hours=1),
        partition=partition,
        store=dataset_store,
        fetcher=fake_fetcher,
    )

    assert manifest.source == "dukascopy"
    assert manifest.status is DatasetStatus.OK
