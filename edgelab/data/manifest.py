"""Manifeste de dataset versionné et garde-fou de quarantaine.

Un `DatasetManifest` est le seul objet que le reste de la plateforme doit
consulter pour savoir si un dataset est utilisable. `ensure_backtest_ready`
est le chemin que le moteur de backtest (Phase 3) appellera avant de
démarrer ; il n'existe aucun moyen de contourner un statut `quarantine`
autrement qu'en corrigeant les données et en ré-ingérant.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from edgelab.data.integrity import IntegrityReport


class RollMethod(enum.StrEnum):
    """Méthode de raccord d'un future continu — doit toujours être choisie explicitement.

    `NONE` est un choix explicite (« pas de raccord »), pas un défaut caché :
    les fonctions d'ingestion de futures continus n'ont pas de valeur par
    défaut pour ce paramètre.
    """

    RATIO = "ratio"
    DIFFERENCE = "difference"
    NONE = "none"


class DatasetStatus(enum.StrEnum):
    """Statut d'un dataset à l'issue du contrôle d'intégrité."""

    OK = "ok"
    QUARANTINE = "quarantine"


class DatasetPartition(BaseModel):
    """Bornes du partitionnement research / validation / holdout d'un dataset.

    `research` va du début du dataset à `research_end` (exclu), `validation`
    de `research_end` à `validation_end` (exclu), `holdout` de
    `validation_end` à la fin du dataset.
    """

    model_config = ConfigDict(frozen=True)

    research_end: datetime
    validation_end: datetime

    @model_validator(mode="after")
    def _check_order(self) -> DatasetPartition:
        if self.research_end >= self.validation_end:
            raise ValueError("research_end must be strictly before validation_end")
        return self


class DatasetManifest(BaseModel):
    """Manifeste versionné d'un dataset ingéré."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    instrument_symbol: str
    source: str
    start: datetime
    end: datetime
    timezone: str
    roll_method: RollMethod | None
    partition: DatasetPartition
    integrity_report: IntegrityReport
    status: DatasetStatus
    manifest_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QuarantinedDatasetError(RuntimeError):
    """Levée quand du code tente d'utiliser un dataset en quarantaine pour un backtest."""


def ensure_backtest_ready(manifest: DatasetManifest) -> None:
    """Garde-fou : refuse tout usage en backtest d'un dataset en quarantaine.

    C'est l'appel que le moteur de backtest (Phase 3) fera avant de démarrer.

    Raises:
        QuarantinedDatasetError: si `manifest.status` est `quarantine`.
    """
    if manifest.status is DatasetStatus.QUARANTINE:
        raise QuarantinedDatasetError(
            f"dataset '{manifest.dataset_id}' ({manifest.instrument_symbol}) is quarantined: "
            f"{manifest.integrity_report.summary()}"
        )
