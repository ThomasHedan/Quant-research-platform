"""Modèles du simulateur de règles de prop firm (Phase 5, I5).

`PropFirmRuleset` est déclaratif : un fichier YAML décrit entièrement les
règles d'une firme, sans code. `is_verified` ne porte que sur les paramètres
qui alimentent la simulation (cibles de profit, pertes, drawdown, jours) —
le profit split et les restrictions sont informatifs et peuvent ne pas avoir
été vérifiés à la même date, voir `propsim/README.md`.
"""

from __future__ import annotations

import enum
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DrawdownBasis(enum.StrEnum):
    """Le drawdown est mesuré sur le solde (trades clôturés) ou sur l'equity (P&L flottant)."""

    BALANCE = "balance"
    EQUITY = "equity"


class DrawdownType(enum.StrEnum):
    """Statique (référence fixe au capital initial) ou trailing (référence au plus haut atteint)."""

    STATIC = "static"
    TRAILING = "trailing"


class Restrictions(BaseModel):
    """Restrictions de trading. `None` signifie « non confirmé sur une source officielle ».

    Deviner une règle de conformité serait pire que de l'afficher comme
    inconnue : aucune des quatre restrictions n'est donc renseignée par
    défaut dans les rulesets livrés tant qu'elle n'a pas été sourcée.
    """

    model_config = ConfigDict(frozen=True)

    news_trading_allowed: bool | None = None
    overnight_allowed: bool | None = None
    weekend_allowed: bool | None = None
    hedging_allowed: bool | None = None


class ProfitSplit(BaseModel):
    """Répartition du profit entre le trader et la firme, une fois financé. Purement informatif."""

    model_config = ConfigDict(frozen=True)

    trader_share: float | None = Field(default=None, ge=0.0, le=1.0)


class ChallengePhase(BaseModel):
    """Un palier de règles (challenge, vérification, financé...) au sein d'un ruleset."""

    model_config = ConfigDict(frozen=True)

    name: str
    profit_target_pct: float | None = Field(default=None, ge=0.0)
    max_daily_loss_pct: float = Field(gt=0.0, le=1.0)
    max_drawdown_pct: float = Field(gt=0.0, le=1.0)
    drawdown_type: DrawdownType
    drawdown_basis: DrawdownBasis
    min_trading_days: int = Field(ge=0)
    max_duration_days: int | None = Field(default=None, gt=0)


class PropFirmRuleset(BaseModel):
    """Règles déclaratives d'une firme, un ou plusieurs paliers (I5)."""

    model_config = ConfigDict(frozen=True)

    firm_name: str
    ruleset_name: str
    phases: tuple[ChallengePhase, ...] = Field(min_length=1)
    restrictions: Restrictions = Field(default_factory=Restrictions)
    profit_split: ProfitSplit = Field(default_factory=ProfitSplit)
    verified_at: date | None = None
    source_url: str | None = None
    note: str = ""

    @property
    def is_verified(self) -> bool:
        """Vrai seulement si les paramètres de simulation ont une date et une source."""
        return self.verified_at is not None and self.source_url is not None

    def phase(self, name: str) -> ChallengePhase:
        """Le palier nommé `name`.

        Raises:
            KeyError: si aucun palier ne porte ce nom.
        """
        for candidate in self.phases:
            if candidate.name == name:
                return candidate
        known = [p.name for p in self.phases]
        raise KeyError(f"Palier inconnu : {name!r} (disponibles : {known})")


class DailyLossGuard(BaseModel):
    """Arrêt volontaire du trading pour la journée avant le seuil dur de perte journalière.

    Coûte du rendement (des trades potentiellement gagnants ne sont jamais
    pris) mais achète de la probabilité de passage en évitant l'approche du
    seuil de breach — c'est le compromis que `propsim` doit rendre mesurable.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    threshold_pct: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_threshold(self) -> DailyLossGuard:
        if self.enabled and self.threshold_pct <= 0.0:
            raise ValueError("threshold_pct must be positive when the guard is enabled")
        return self


class PropSimResult(BaseModel):
    """Résultat d'une simulation Monte Carlo de challenge (I5)."""

    model_config = ConfigDict(frozen=True)

    firm_name: str
    phase_name: str
    risk_per_trade_pct: float
    n_paths: int
    p_pass: float
    p_breach_daily_loss: float
    p_breach_max_drawdown: float
    median_days_to_target: float | None
    worst_day_pct_p95: float


class PropSimComparison(BaseModel):
    """Résultat d'une stratégie face à sa baseline sans edge (I5) — jamais masquable."""

    model_config = ConfigDict(frozen=True)

    strategy: PropSimResult
    baseline: PropSimResult

    @property
    def edge_contribution_p_pass(self) -> float:
        """Différence de P(passage) attribuable à l'edge — le seul chiffre honnête ici."""
        return self.strategy.p_pass - self.baseline.p_pass


class RiskSurfacePoint(BaseModel):
    """Un point de la courbe P(passage) vs risque par trade."""

    model_config = ConfigDict(frozen=True)

    risk_per_trade_pct: float
    p_pass: float


class RiskSurfaceResult(BaseModel):
    """Surface de risque complète, avec la fraction de Kelly pour référence visuelle."""

    model_config = ConfigDict(frozen=True)

    points: tuple[RiskSurfacePoint, ...]
    kelly_fraction: float

    @property
    def best_point(self) -> RiskSurfacePoint:
        """Le point de risque par trade qui maximise P(passage) sur la surface balayée."""
        return max(self.points, key=lambda p: p.p_pass)
