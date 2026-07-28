"""Modèles de résultats du module de validation statistique (Phase 4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from edgelab.strategies.models import KillCriterion


class BootstrapComparison(BaseModel):
    """Bootstrap par blocs vs iid, à taille de bloc donnée.

    L'écart entre les deux est l'information utile : le bootstrap iid casse
    la dépendance sérielle des trades et sous-estime les métriques de queue
    (drawdown, séries de pertes) — exactement ce qui fait échouer un
    challenge prop firm. `underestimation_ratio` (block / iid) est toujours
    affiché, jamais masqué même quand il est proche de 1.
    """

    model_config = ConfigDict(frozen=True)

    block_size: int
    n_resamples: int
    block_max_drawdown_p95: float
    iid_max_drawdown_p95: float
    drawdown_underestimation_ratio: float
    block_worst_streak_p95: float
    iid_worst_streak_p95: float
    streak_underestimation_ratio: float


class PermutationTestResult(BaseModel):
    """Résultat d'un test de permutation par retournement de signe sur des rendements de trades."""

    model_config = ConfigDict(frozen=True)

    observed_mean: float
    n_permutations: int
    p_value: float


class DeflatedSharpeResult(BaseModel):
    """Deflated Sharpe Ratio (Bailey & López de Prado), alimenté par le registre.

    `n_trials` doit provenir d'un comptage réel du registre d'essais (I1) —
    jamais d'une valeur saisie à la main, sous peine de statistiques de
    significativité mensongères sur toute la plateforme.
    """

    model_config = ConfigDict(frozen=True)

    observed_sharpe: float
    n_observations: int
    skewness: float
    kurtosis: float
    n_trials: int
    expected_max_sharpe_under_null: float
    sharpe_std_error: float
    deflated_sharpe_ratio: float


class KillCriterionVerdict(BaseModel):
    """Verdict d'un critère de mort individuel, évalué contre une métrique mesurée."""

    model_config = ConfigDict(frozen=True)

    criterion: KillCriterion
    measured_value: float | None
    triggered: bool


class KillCriteriaVerdict(BaseModel):
    """Verdict global de l'évaluation des critères de mort d'une stratégie."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    criteria: tuple[KillCriterionVerdict, ...]

    @property
    def any_triggered(self) -> bool:
        """Vrai si au moins un critère de mort est déclenché — la stratégie doit mourir."""
        return any(c.triggered for c in self.criteria)
