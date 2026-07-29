"""Tests de edgelab.data.selection (I3 et quarantaine par construction)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from edgelab.data.integrity import IntegrityIssue, IntegrityReport, IntegritySeverity
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
)
from edgelab.data.selection import (
    DatasetSelection,
    DataSplit,
    EmptySplitError,
    UnknownDatasetError,
    describe_splits,
    load_holdout,
    load_split,
    split_bounds,
)
from edgelab.data.store import DatasetStore

_START = datetime(2024, 1, 1, tzinfo=UTC)
_RESEARCH_END = datetime(2024, 1, 3, tzinfo=UTC)
_VALIDATION_END = datetime(2024, 1, 4, tzinfo=UTC)
_N_BARS = 120  # 5 jours de barres horaires


@pytest.fixture
def partitioned_bars() -> pl.DataFrame:
    """Cinq jours de barres horaires, à cheval sur les trois splits."""
    rows = [(_START + timedelta(hours=i), 100.0, 100.5, 99.5, 100.0, 10.0) for i in range(_N_BARS)]
    return pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )


@pytest.fixture
def make_stored_dataset(
    dataset_store: DatasetStore, partitioned_bars: pl.DataFrame
) -> Callable[..., str]:
    """Factory persistant un dataset partitionné dans le store et renvoyant son `dataset_id`."""

    def _make(
        *,
        dataset_id: str = "ds-1",
        status: DatasetStatus = DatasetStatus.OK,
        bars: pl.DataFrame | None = None,
    ) -> str:
        frame = partitioned_bars if bars is None else bars
        issues = (
            ()
            if status is DatasetStatus.OK
            else (
                IntegrityIssue(
                    kind="session_gap",
                    severity=IntegritySeverity.CRITICAL,
                    message="trou de session artificiel",
                    count=1,
                ),
            )
        )
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            instrument_symbol="EURUSD",
            source="test",
            start=frame["timestamp"].min(),  # type: ignore[arg-type]
            end=frame["timestamp"].max(),  # type: ignore[arg-type]
            timezone="UTC",
            roll_method=None,
            partition=DatasetPartition(research_end=_RESEARCH_END, validation_end=_VALIDATION_END),
            integrity_report=IntegrityReport(issues=issues),
            status=status,
            manifest_hash="0" * 64,
        )
        dataset_store.save(manifest, frame)
        return dataset_id

    return _make


# --- bornes de split ---------------------------------------------------------


def test_split_bounds_partition_the_dataset_without_overlap_or_gap(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Les trois splits se suivent bout à bout : la fin de l'un est le début du suivant."""
    dataset_id = make_stored_dataset()
    manifest = dataset_store.load_manifest(dataset_id)
    assert manifest is not None

    research = split_bounds(manifest, DataSplit.RESEARCH)
    validation = split_bounds(manifest, DataSplit.VALIDATION)
    holdout = split_bounds(manifest, DataSplit.HOLDOUT)

    assert research.end == validation.start
    assert validation.end == holdout.start
    assert holdout.closed_right is True


def test_describe_splits_counts_every_bar_exactly_once(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Compter les splits ne perd ni ne duplique de barre : la somme fait le dataset."""
    dataset_id = make_stored_dataset()

    counts = describe_splits(dataset_store, dataset_id)

    assert sum(counts.values()) == _N_BARS
    assert all(count > 0 for count in counts.values())


def test_describe_splits_does_not_consume_a_holdout_access(
    dataset_store: DatasetStore,
    make_stored_dataset: Callable[..., str],
    lockbox: HoldoutLockbox,
) -> None:
    """Voir la taille du holdout dans l'UI ne doit rien coûter : compter n'est pas regarder."""
    dataset_id = make_stored_dataset()

    describe_splits(dataset_store, dataset_id)

    assert lockbox.access_count("strategy-1") == 0


def test_describe_splits_rejects_an_unknown_dataset(dataset_store: DatasetStore) -> None:
    """Un `dataset_id` inconnu est une erreur nommée, pas un dictionnaire vide."""
    with pytest.raises(UnknownDatasetError, match="introuvable"):
        describe_splits(dataset_store, "n-existe-pas")


# --- load_split --------------------------------------------------------------


@pytest.mark.parametrize("split", [DataSplit.RESEARCH, DataSplit.VALIDATION])
def test_load_split_returns_only_the_bars_of_the_named_split(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str], split: DataSplit
) -> None:
    """Un split chargé ne contient aucune barre en dehors de ses bornes."""
    dataset_id = make_stored_dataset()

    selection = load_split(dataset_store, dataset_id, split=split)

    bounds = split_bounds(selection.manifest, split)
    assert selection.split is split
    assert bounds.contains(selection.bars["timestamp"].min())  # type: ignore[arg-type]
    assert bounds.contains(selection.bars["timestamp"].max())  # type: ignore[arg-type]
    assert selection.n_bars < _N_BARS


def test_load_split_never_leaks_a_holdout_bar(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Aucune barre postérieure à la fin de validation ne sort d'un chargement de recherche."""
    dataset_id = make_stored_dataset()

    selection = load_split(dataset_store, dataset_id, split=DataSplit.RESEARCH)

    assert selection.bars.filter(pl.col("timestamp") >= _VALIDATION_END).is_empty()


def test_load_split_refuses_the_holdout(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """I3 : le holdout n'est pas un split comme les autres, `load_split` le refuse."""
    dataset_id = make_stored_dataset()

    with pytest.raises(HoldoutAccessDeniedError, match="load_holdout"):
        load_split(dataset_store, dataset_id, split=DataSplit.HOLDOUT)


def test_load_split_refuses_a_quarantined_dataset(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Un dataset en quarantaine ne produit aucune sélection, donc aucun backtest."""
    dataset_id = make_stored_dataset(status=DatasetStatus.QUARANTINE)

    with pytest.raises(QuarantinedDatasetError, match="quarantined"):
        load_split(dataset_store, dataset_id, split=DataSplit.RESEARCH)


def test_load_split_rejects_an_unknown_dataset(dataset_store: DatasetStore) -> None:
    """Charger un dataset qui n'existe pas est une erreur nommée."""
    with pytest.raises(UnknownDatasetError, match="introuvable"):
        load_split(dataset_store, "n-existe-pas", split=DataSplit.RESEARCH)


def test_load_split_rejects_an_empty_split(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Un split vide lève : un backtest sur zéro barre écrirait une ligne de registre trompeuse."""
    only_holdout = pl.DataFrame(
        [
            (_VALIDATION_END + timedelta(hours=i), 100.0, 100.5, 99.5, 100.0, 10.0)
            for i in range(10)
        ],
        schema=["timestamp", "open", "high", "low", "close", "volume"],
        orient="row",
    )
    dataset_id = make_stored_dataset(dataset_id="ds-holdout-only", bars=only_holdout)

    with pytest.raises(EmptySplitError, match="est vide"):
        load_split(dataset_store, dataset_id, split=DataSplit.RESEARCH)


# --- load_holdout : I3 -------------------------------------------------------


def test_load_holdout_requires_a_written_reason(
    dataset_store: DatasetStore,
    make_stored_dataset: Callable[..., str],
    lockbox: HoldoutLockbox,
) -> None:
    """I3 : sans raison écrite, le holdout ne s'ouvre pas et rien n'est compté."""
    dataset_id = make_stored_dataset()

    with pytest.raises(HoldoutAccessDeniedError):
        load_holdout(
            dataset_store, dataset_id, strategy_id="strategy-1", reason="   ", lockbox=lockbox
        )

    assert lockbox.access_count("strategy-1") == 0


def test_load_holdout_increments_the_permanent_access_counter(
    dataset_store: DatasetStore,
    make_stored_dataset: Callable[..., str],
    lockbox: HoldoutLockbox,
) -> None:
    """Chaque ouverture du holdout est comptée, et la sélection porte l'accès qui l'autorise."""
    dataset_id = make_stored_dataset()

    selection = load_holdout(
        dataset_store,
        dataset_id,
        strategy_id="strategy-1",
        reason="validation finale avant propsim",
        lockbox=lockbox,
    )

    assert lockbox.access_count("strategy-1") == 1
    assert selection.split is DataSplit.HOLDOUT
    assert selection.holdout_access is not None
    assert selection.holdout_access.reason == "validation finale avant propsim"


def test_three_holdout_accesses_raise_the_red_flag(
    dataset_store: DatasetStore,
    make_stored_dataset: Callable[..., str],
    lockbox: HoldoutLockbox,
) -> None:
    """Le drapeau rouge de l'UI se déclenche au troisième accès, comme le veut I3."""
    dataset_id = make_stored_dataset()

    for i in range(RED_FLAG_THRESHOLD):
        load_holdout(
            dataset_store,
            dataset_id,
            strategy_id="strategy-1",
            reason=f"accès {i}",
            lockbox=lockbox,
        )

    assert lockbox.is_flagged("strategy-1") is True


def test_load_holdout_counts_the_access_even_when_the_dataset_is_unusable(
    dataset_store: DatasetStore,
    make_stored_dataset: Callable[..., str],
    lockbox: HoldoutLockbox,
) -> None:
    """Le compteur mesure la décision de regarder, pas le succès de la lecture."""
    dataset_id = make_stored_dataset(status=DatasetStatus.QUARANTINE)

    with pytest.raises(QuarantinedDatasetError):
        load_holdout(
            dataset_store,
            dataset_id,
            strategy_id="strategy-1",
            reason="curiosité",
            lockbox=lockbox,
        )

    assert lockbox.access_count("strategy-1") == 1


def test_load_holdout_rejects_an_unknown_dataset_before_counting(
    dataset_store: DatasetStore, lockbox: HoldoutLockbox
) -> None:
    """Un dataset inexistant n'est pas une décision de regarder : rien n'est compté."""
    with pytest.raises(UnknownDatasetError):
        load_holdout(dataset_store, "n-existe-pas", strategy_id="s", reason="test", lockbox=lockbox)

    assert lockbox.access_count("s") == 0


# --- DatasetSelection : garde-fous du constructeur ---------------------------


def test_selection_refuses_holdout_bars_without_a_logged_access(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Construire une sélection holdout à la main sans accès journalisé est refusé (I3)."""
    dataset_id = make_stored_dataset()
    manifest = dataset_store.load_manifest(dataset_id)
    assert manifest is not None
    holdout_bars = dataset_store.load_bars(dataset_id).filter(
        pl.col("timestamp") >= _VALIDATION_END
    )

    with pytest.raises(HoldoutAccessDeniedError, match="load_holdout"):
        DatasetSelection(manifest=manifest, split=DataSplit.HOLDOUT, bars=holdout_bars)


def test_selection_refuses_bars_that_fall_outside_the_declared_split(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Annoncer « research » en passant tout le dataset est détecté, pas cru sur parole."""
    dataset_id = make_stored_dataset()
    manifest = dataset_store.load_manifest(dataset_id)
    assert manifest is not None
    every_bar = dataset_store.load_bars(dataset_id)

    with pytest.raises(ValueError, match="hors des bornes"):
        DatasetSelection(manifest=manifest, split=DataSplit.RESEARCH, bars=every_bar)


def test_selection_of_a_quarantined_dataset_is_impossible(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """La quarantaine est vérifiée à la construction, pas seulement au démarrage du moteur."""
    dataset_id = make_stored_dataset(status=DatasetStatus.QUARANTINE)
    manifest = dataset_store.load_manifest(dataset_id)
    assert manifest is not None
    bars = dataset_store.load_bars(dataset_id).filter(pl.col("timestamp") < _RESEARCH_END)

    with pytest.raises(QuarantinedDatasetError):
        DatasetSelection(manifest=manifest, split=DataSplit.RESEARCH, bars=bars)


def test_a_holdout_selection_exposes_the_access_record(
    dataset_store: DatasetStore, make_stored_dataset: Callable[..., str]
) -> None:
    """Une sélection holdout porte l'accès qui l'a autorisée, lisible en aval."""
    dataset_id = make_stored_dataset()
    manifest = dataset_store.load_manifest(dataset_id)
    assert manifest is not None
    holdout_bars = dataset_store.load_bars(dataset_id).filter(
        pl.col("timestamp") >= _VALIDATION_END
    )
    record = HoldoutAccessRecord(strategy_id="s", reason="test", accessed_at=datetime.now(UTC))

    selection = DatasetSelection(
        manifest=manifest, split=DataSplit.HOLDOUT, bars=holdout_bars, holdout_access=record
    )

    assert selection.instrument_symbol == "EURUSD"
    assert selection.holdout_access is record
