"""Schémas de réponse HTTP propres à l'API.

Chaque fois qu'un modèle du package couvre déjà un concept (`HypothesisSheet`,
`PropSimComparison`, `WalkForwardResult`, ...), l'API le réexpose tel quel —
elle ne réinvente jamais un schéma qui duplique un modèle de calcul existant.
Les modèles définis ici couvrent uniquement ce qui n'a pas de foyer naturel
dans `edgelab/{research,validation,propsim,portfolio}` : l'agrégation d'un
bundle de stratégie pour la fiche UI, et la ligne dense du leaderboard.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from edgelab.propsim.models import PropSimComparison, RiskSurfaceResult
from edgelab.strategies.models import HypothesisSheet, StrategyStatus
from edgelab.validation.models import (
    BootstrapComparison,
    CostsStressResult,
    DeflatedSharpeResult,
    KillCriteriaVerdict,
    PBOResult,
    PermutationTestResult,
    StartDateSensitivityResult,
    WalkForwardResult,
)


class ConfidenceInterval(BaseModel):
    """Intervalle de confiance à 95 % affiché à côté de toute moyenne (spec Phase 8)."""

    model_config = ConfigDict(frozen=True)

    mean: float
    ci_low: float
    ci_high: float
    n: int


class SubperiodPoint(BaseModel):
    """Stabilité de l'espérance par sous-période chronologique."""

    model_config = ConfigDict(frozen=True)

    label: str
    stats: ConfidenceInterval
    t_stat: float


class VolRegimePoint(BaseModel):
    """Espérance par tercile de volatilité réalisée — pour comprendre, pas pour filtrer."""

    model_config = ConfigDict(frozen=True)

    tercile: str
    stats: ConfidenceInterval
    t_stat: float


class InstrumentBreakdown(BaseModel):
    """Décomposition par instrument de l'univers (mode multi-instruments par défaut)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    stats: ConfidenceInterval
    t_stat: float
    hit_rate: float


class NaiveComparison(BaseModel):
    """Règle naïve de contrôle : le déclencheur bat-il une variante sans lui ?"""

    model_config = ConfigDict(frozen=True)

    triggered: ConfidenceInterval
    naive: ConfidenceInterval
    mean_diff: float
    p_value: float
    improves_on_naive: bool


class MonteCarloFan(BaseModel):
    """Fan chart Monte Carlo : percentiles de trajectoire d'équité simulée (propsim)."""

    model_config = ConfigDict(frozen=True)

    trade_index: tuple[int, ...]
    p10: tuple[float, ...]
    p50: tuple[float, ...]
    p90: tuple[float, ...]


class TrialLink(BaseModel):
    """Référence légère vers un essai du registre, pour le lier depuis une fiche stratégie."""

    model_config = ConfigDict(frozen=True)

    id: str
    trial_type: str
    created_at: str
    lineage_hash: str


class LeaderboardRow(BaseModel):
    """Une ligne de la grille dense du leaderboard. Tri par défaut : `p_pass` (I5)."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    family: str
    universe: str
    status: StrategyStatus
    n_trades: int
    net_expectancy_bps: float
    t_stat: float
    dsr: float
    pbo: float
    p_pass: float
    delta_vs_baseline_p_pass: float
    max_dd_p95: float
    worst_day_p95: float
    worst_streak_p95: float
    win_rate: float
    holdout_access_count: int
    holdout_flagged: bool


class StrategyBundle(BaseModel):
    """Bundle complet d'une stratégie : ce que lit la fiche stratégie (vue 2)."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    family: str
    universe: str
    status: StrategyStatus
    lineage: tuple[str, ...]
    hypothesis: HypothesisSheet
    kill_criteria_verdict: KillCriteriaVerdict
    trade_r_multiples: tuple[float, ...]
    equity_curve: tuple[float, ...]
    mae_mfe_mean_mae: float
    mae_mfe_mean_mfe: float
    subperiod_stats: tuple[SubperiodPoint, ...]
    vol_regime_stats: tuple[VolRegimePoint, ...]
    naive_comparison: NaiveComparison
    instrument_breakdown: tuple[InstrumentBreakdown, ...]
    monte_carlo_fan: MonteCarloFan
    bootstrap_comparison: BootstrapComparison
    permutation: PermutationTestResult
    walk_forward: WalkForwardResult
    dsr: DeflatedSharpeResult
    pbo: PBOResult
    start_date_sensitivity: StartDateSensitivityResult
    costs_stress: CostsStressResult
    propsim: PropSimComparison
    risk_surface: RiskSurfaceResult
    ruleset_name: str
    holdout_access_count: int
    holdout_flagged: bool
