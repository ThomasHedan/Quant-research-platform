"""Sélection des données pour la recherche et le backtest — I3 et la quarantaine par construction.

Avant ce module, `DatasetStore.load_bars` renvoyait le dataset entier, holdout
compris, et `BacktestEngine` acceptait n'importe quel DataFrame : le
partitionnement du manifeste et le compteur du lockbox existaient mais n'étaient
sur le chemin de personne. I3 (« le holdout est accessible via un chemin de code
distinct ») et le refus des datasets en quarantaine tenaient par discipline.

Le seul objet que le moteur de backtest accepte désormais est `DatasetSelection`,
et il ne peut pas exister sans que trois choses soient vraies :

1. son manifeste a passé `ensure_backtest_ready` (donc pas de quarantaine) ;
2. ses barres tombent effectivement dans les bornes du split annoncé ;
3. si le split est `holdout`, un `HoldoutAccessRecord` l'accompagne — et le seul
   constructeur qui en produit un est `load_holdout`, qui exige une raison
   écrite et incrémente le compteur permanent.

Ce que ce module ne prétend pas faire : rendre la fraude impossible. Python
laisse toujours fabriquer un objet à la main. Le point est qu'aucun chemin normal
ne produit du holdout sans le journaliser, et qu'y arriver demande d'écrire
explicitement du code dont l'intention est visible en relecture.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import polars as pl
from polars._typing import ClosedInterval

from edgelab.data.lockbox import HoldoutAccessDeniedError, HoldoutAccessRecord, HoldoutLockbox
from edgelab.data.manifest import DatasetManifest, ensure_backtest_ready

if TYPE_CHECKING:
    from edgelab.data.store import DatasetStore

logger = logging.getLogger(__name__)


class DataSplit(enum.StrEnum):
    """Les trois partitions d'un dataset. Le split est toujours nommé, jamais déduit."""

    RESEARCH = "research"
    VALIDATION = "validation"
    HOLDOUT = "holdout"


class UnknownDatasetError(LookupError):
    """Levée quand un `dataset_id` demandé n'existe pas dans le store."""


class EmptySplitError(RuntimeError):
    """Levée quand le split demandé ne contient aucune barre.

    C'est une erreur et non un DataFrame vide : un backtest sur zéro barre est
    un résultat qui ne veut rien dire, et le laisser passer silencieusement
    produirait une ligne de registre trompeuse.
    """


@dataclass(frozen=True)
class SplitBounds:
    """Bornes temporelles d'un split : `[start, end)`, sauf le holdout qui est fermé à droite."""

    split: DataSplit
    start: datetime
    end: datetime
    closed_right: bool

    def contains(self, moment: datetime) -> bool:
        """Vrai si `moment` tombe dans ces bornes."""
        if moment < self.start:
            return False
        return moment <= self.end if self.closed_right else moment < self.end


def split_bounds(manifest: DatasetManifest, split: DataSplit) -> SplitBounds:
    """Les bornes du split demandé, dérivées du manifeste — jamais d'un choix d'appelant."""
    partition = manifest.partition
    match split:
        case DataSplit.RESEARCH:
            return SplitBounds(split, manifest.start, partition.research_end, closed_right=False)
        case DataSplit.VALIDATION:
            return SplitBounds(
                split, partition.research_end, partition.validation_end, closed_right=False
            )
        case DataSplit.HOLDOUT:
            return SplitBounds(split, partition.validation_end, manifest.end, closed_right=True)


def _slice(bars: pl.DataFrame, bounds: SplitBounds) -> pl.DataFrame:
    closed: ClosedInterval = "both" if bounds.closed_right else "left"
    return bars.filter(pl.col("timestamp").is_between(bounds.start, bounds.end, closed=closed))


@dataclass(frozen=True)
class DatasetSelection:
    """Les barres d'un dataset non-quarantainé, restreintes à un split explicitement nommé.

    C'est le seul type de données que `BacktestEngine` accepte. Construire cet
    objet est ce qui prouve que la quarantaine a été vérifiée et que le holdout,
    s'il est utilisé, a été journalisé.
    """

    manifest: DatasetManifest
    split: DataSplit
    bars: pl.DataFrame
    holdout_access: HoldoutAccessRecord | None = None

    def __post_init__(self) -> None:
        """
        Raises:
            QuarantinedDatasetError: si le manifeste est en quarantaine.
            HoldoutAccessDeniedError: si le split est `holdout` sans accès journalisé.
            EmptySplitError: si les barres sont vides.
            ValueError: si une barre tombe hors des bornes du split annoncé.
        """
        ensure_backtest_ready(self.manifest)
        if self.split is DataSplit.HOLDOUT and self.holdout_access is None:
            raise HoldoutAccessDeniedError(
                f"sélection holdout du dataset '{self.manifest.dataset_id}' sans accès "
                "journalisé : passer par `load_holdout` (I3)"
            )
        if self.bars.is_empty():
            raise EmptySplitError(
                f"le split '{self.split}' du dataset '{self.manifest.dataset_id}' est vide"
            )
        bounds = split_bounds(self.manifest, self.split)
        first: datetime = self.bars["timestamp"].min()  # type: ignore[assignment]
        last: datetime = self.bars["timestamp"].max()  # type: ignore[assignment]
        if not (bounds.contains(first) and bounds.contains(last)):
            raise ValueError(
                f"barres hors des bornes du split '{self.split}' "
                f"({first} → {last} contre {bounds.start} → {bounds.end})"
            )

    @property
    def instrument_symbol(self) -> str:
        """Le symbole de l'instrument couvert par cette sélection."""
        return self.manifest.instrument_symbol

    @property
    def n_bars(self) -> int:
        """Le nombre de barres du split."""
        return self.bars.height


def load_split(store: DatasetStore, dataset_id: str, *, split: DataSplit) -> DatasetSelection:
    """Charge un split de recherche ou de validation. Refuse le holdout, sans exception.

    Raises:
        UnknownDatasetError: si `dataset_id` n'est pas dans le store.
        HoldoutAccessDeniedError: si `split` est `holdout` — c'est `load_holdout`
            qu'il faut appeler, et il exige une raison écrite (I3).
        QuarantinedDatasetError: si le dataset est en quarantaine.
        EmptySplitError: si le split ne contient aucune barre.
    """
    if split is DataSplit.HOLDOUT:
        raise HoldoutAccessDeniedError(
            "le holdout ne s'ouvre pas par `load_split` : utiliser `load_holdout`, "
            "qui exige une raison écrite et incrémente le compteur d'accès (I3)"
        )
    manifest = _require_manifest(store, dataset_id)
    bounds = split_bounds(manifest, split)
    return DatasetSelection(
        manifest=manifest, split=split, bars=_slice(store.load_bars(dataset_id), bounds)
    )


def load_holdout(
    store: DatasetStore,
    dataset_id: str,
    *,
    strategy_id: str,
    reason: str,
    lockbox: HoldoutLockbox,
) -> DatasetSelection:
    """Ouvre le holdout — chemin de code distinct, tracé, irréversible (I3).

    L'accès est journalisé *avant* que les barres soient lues : un appel qui
    échoue ensuite (dataset en quarantaine, split vide) a quand même consommé un
    accès. C'est délibéré — le compteur mesure les fois où l'utilisateur a
    *décidé* de regarder, pas les fois où ça a marché.

    Raises:
        UnknownDatasetError: si `dataset_id` n'est pas dans le store.
        HoldoutAccessDeniedError: si `reason` est vide.
        QuarantinedDatasetError: si le dataset est en quarantaine.
        EmptySplitError: si le holdout ne contient aucune barre.
    """
    manifest = _require_manifest(store, dataset_id)
    count = lockbox.access(strategy_id, reason)
    record = lockbox.access_log(strategy_id)[-1]
    logger.warning(
        "holdout selection strategy=%s dataset=%s access_count=%d", strategy_id, dataset_id, count
    )
    bounds = split_bounds(manifest, DataSplit.HOLDOUT)
    return DatasetSelection(
        manifest=manifest,
        split=DataSplit.HOLDOUT,
        bars=_slice(store.load_bars(dataset_id), bounds),
        holdout_access=record,
    )


def describe_splits(store: DatasetStore, dataset_id: str) -> dict[DataSplit, int]:
    """Nombre de barres par split, sans ouvrir le holdout ni consommer d'accès.

    Compter des barres n'est pas les regarder : cette fonction alimente la barre
    de partition de l'UI, qui doit pouvoir montrer que le holdout existe et
    quelle taille il fait sans que l'affichage coûte un accès au compteur.

    Raises:
        UnknownDatasetError: si `dataset_id` n'est pas dans le store.
    """
    manifest = _require_manifest(store, dataset_id)
    bars = store.load_bars(dataset_id)
    return {split: _slice(bars, split_bounds(manifest, split)).height for split in DataSplit}


def _require_manifest(store: DatasetStore, dataset_id: str) -> DatasetManifest:
    manifest = store.load_manifest(dataset_id)
    if manifest is None:
        raise UnknownDatasetError(f"dataset '{dataset_id}' introuvable dans le store")
    return manifest
