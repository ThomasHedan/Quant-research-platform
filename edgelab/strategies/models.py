"""Fiche d'hypothèse pré-enregistrée (I2).

Une hypothèse qui ne prédit son échec nulle part n'est pas falsifiable :
`HypothesisSheet` le refuse à la construction, pas seulement dans une
commande CLI qui pourrait être contournée — n'importe quel code qui
construit ce modèle hérite du refus.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyStatus(enum.StrEnum):
    """État du cycle de vie d'une stratégie.

    `DEAD` est un piège à sens unique (Phase 4) : aucune transition ne
    ramène une stratégie de `DEAD` vers `CANDIDATE`. Retester l'idée exige
    une nouvelle fiche d'hypothèse, avec un nouveau `strategy_id`.
    """

    CANDIDATE = "candidate"
    DEAD = "dead"
    VALIDATED = "validated"


class KillCriterion(BaseModel):
    """Un critère de mort daté : au-delà de quoi l'hypothèse est invalidée."""

    model_config = ConfigDict(frozen=True)

    name: str
    metric: str
    comparison: Literal["less_than", "greater_than"]
    threshold: float
    recorded_at: datetime


class HypothesisSheet(BaseModel):
    """Fiche d'hypothèse pré-enregistrée d'une stratégie (I2).

    `parent_strategy_id` trace la filiation quand cette fiche reteste une
    idée dont une version antérieure a été marquée `dead` — le lien de
    parenté doit rester visible (spec Phase 4), jamais recréé de zéro comme
    si l'essai précédent n'avait pas eu lieu.
    """

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    economic_hypothesis: str
    predicted_direction: Literal["long", "short", "both"]
    predicted_amplitude_atr: float
    predicted_hit_rate: float
    predicted_horizon_bars: int
    where_it_should_not_work: str
    kill_criteria: tuple[KillCriterion, ...]
    parent_strategy_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_falsifiability(self) -> HypothesisSheet:
        if not self.where_it_should_not_work.strip():
            raise ValueError(
                "where_it_should_not_work must not be empty: a hypothesis that predicts "
                "failure nowhere is not falsifiable (I2)"
            )
        if not self.economic_hypothesis.strip():
            raise ValueError("economic_hypothesis must not be empty (I2)")
        if not self.kill_criteria:
            raise ValueError("kill_criteria must not be empty (I2)")
        if not 0.0 <= self.predicted_hit_rate <= 1.0:
            raise ValueError("predicted_hit_rate must be in [0, 1]")
        if self.predicted_horizon_bars <= 0:
            raise ValueError("predicted_horizon_bars must be positive")
        return self
