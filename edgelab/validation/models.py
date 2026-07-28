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


class WalkForwardWindow(BaseModel):
    """Une fenêtre glissante : paramètre choisi en échantillon, performance hors échantillon."""

    model_config = ConfigDict(frozen=True)

    window_index: int
    selected_param: str
    in_sample_score: float
    out_of_sample_return: float


class WalkForwardResult(BaseModel):
    """Résultat d'un walk-forward : la seule performance d'optimisation crédible.

    Chaque fenêtre choisit son paramètre sur l'échantillon d'entraînement
    seul, puis mesure sa performance sur l'échantillon suivant, jamais vu au
    moment du choix — contrairement à un backtest optimisé une fois sur
    toute la période, qui mélange sélection et évaluation.
    """

    model_config = ConfigDict(frozen=True)

    windows: tuple[WalkForwardWindow, ...]
    in_sample_size: int
    out_of_sample_size: int
    out_of_sample_mean_return: float
    out_of_sample_total_return: float

    @property
    def n_windows(self) -> int:
        """Nombre de fenêtres glissantes évaluées."""
        return len(self.windows)


class PBOResult(BaseModel):
    """Probability of Backtest Overfitting par CSCV (Bailey, Borwein, López de Prado & Zhu, 2015).

    `probability_of_overfitting` est la fraction des découpes symétriques où
    le paramètre gagnant en échantillon se classe sous la médiane hors
    échantillon — une sélection sans edge réel produit une valeur proche de
    0,5 (le gagnant en échantillon n'est pas meilleur qu'un tirage au sort
    hors échantillon), un edge réel et stable la ramène vers 0.
    """

    model_config = ConfigDict(frozen=True)

    n_partitions: int
    n_combinations: int
    probability_of_overfitting: float
    logits: tuple[float, ...]


class StartDateSensitivityResult(BaseModel):
    """Dispersion du résultat final selon la date de démarrage de la stratégie.

    Chaque `final_returns[i]` est le rendement cumulé d'une fenêtre de
    `window_length` rendements démarrant au décalage `i` — une fenêtre de
    longueur fixe pour que la dispersion mesure une vraie sensibilité à la
    date de départ, pas un artefact de taille d'échantillon variable.
    """

    model_config = ConfigDict(frozen=True)

    n_start_dates: int
    window_length: int
    final_returns: tuple[float, ...]
    mean_final_return: float
    std_final_return: float
    min_final_return: float
    max_final_return: float


class CostsStressResult(BaseModel):
    """Résultat du test de coûts x2 : l'edge survit-il à deux fois les coûts réalistes ?

    `survives_2x_costs` est un critère binaire simple (rendement moyen
    stressé encore positif) ; `p_value_stressed` reste affichée à côté pour
    juger de la significativité, mais ne remplace pas ce critère de survie.
    """

    model_config = ConfigDict(frozen=True)

    mean_return_net: float
    mean_return_stressed: float
    t_stat_net: float
    t_stat_stressed: float
    p_value_stressed: float
    survives_2x_costs: bool


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
