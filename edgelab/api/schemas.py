"""Schémas de réponse HTTP propres à l'API.

Chaque fois qu'un modèle du package couvre déjà un concept (`HypothesisSheet`,
`PropSimComparison`, `WalkForwardResult`, ...), l'API le réexpose tel quel —
elle ne réinvente jamais un schéma qui duplique un modèle de calcul existant.
Les modèles définis ici couvrent uniquement ce qui n'a pas de foyer naturel
dans `edgelab/{research,validation,propsim,portfolio}` : l'agrégation d'un
bundle de stratégie pour la fiche UI, et la ligne dense du leaderboard.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from edgelab.data.integrity import IntegrityReport
from edgelab.data.manifest import DatasetStatus, RollMethod
from edgelab.data.selection import DataSplit
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


class SplitSummary(BaseModel):
    """Un split d'un dataset : ses bornes et le nombre de barres qu'il contient."""

    split: DataSplit
    start: datetime
    end: datetime
    n_bars: int


class DatasetSummary(BaseModel):
    """Vue de liste d'un dataset ingéré. Le statut de quarantaine est de premier ordre."""

    dataset_id: str
    instrument_symbol: str
    source: str
    status: DatasetStatus
    start: datetime
    end: datetime
    timezone: str
    roll_method: RollMethod | None
    manifest_hash: str
    created_at: datetime
    n_bars: int
    splits: tuple[SplitSummary, ...]
    integrity_summary: str
    is_clean: bool


class DatasetDetail(BaseModel):
    """Vue détaillée d'un dataset : son résumé plus le rapport d'intégrité complet."""

    summary: DatasetSummary
    integrity_report: IntegrityReport


class ProviderInstrument(BaseModel):
    """Une ligne du catalogue London Strategic Edge.

    `first`/`last` sont laissés en chaîne : ce sont des valeurs du fournisseur,
    dont le format n'a pas été vérifié contre un serveur réel, et les afficher
    telles quelles vaut mieux que de les reformater sur une hypothèse.
    """

    symbol: str
    name: str
    category: str
    dataset: str
    first: str | None
    last: str | None
    ticks: int | None


class DownloadRequest(BaseModel):
    """Demande de téléchargement d'un instrument LSE vers le store local.

    Les bornes de partition n'ont pas de valeur par défaut côté modèle : l'UI
    en propose une, mais c'est l'utilisateur qui la confirme (I3).
    """

    provider_symbol: str
    instrument_symbol: str
    timeframe: str
    start: datetime
    end: datetime
    research_end: datetime
    validation_end: datetime
    bulk: bool = False


class DownloadResult(BaseModel):
    """Résultat d'un téléchargement : le dataset créé et son verdict d'intégrité."""

    dataset: DatasetSummary
    quarantined: bool


class HoldoutRequest(BaseModel):
    """Ouverture du holdout depuis l'UI. `reason` est obligatoire et non vide (I3)."""

    dataset_id: str
    strategy_id: str
    reason: str


class HoldoutResult(BaseModel):
    """Compte rendu d'une ouverture du holdout — le compteur est permanent."""

    dataset_id: str
    strategy_id: str
    n_bars: int
    access_count: int
    flagged: bool


class CredentialStatusResponse(BaseModel):
    """L'état d'un emplacement de clé. Ne porte jamais la valeur, par construction du schéma."""

    env_var: str
    label: str
    description: str
    docs_url: str
    wired: bool
    configured: bool
    source: str
    hint: str


class SettingsResponse(BaseModel):
    """Les réglages de la plateforme : emplacements de clés et où ils sont stockés."""

    credentials_file: str
    credentials: tuple[CredentialStatusResponse, ...]


class CredentialUpdate(BaseModel):
    """Écriture d'une clé. La valeur ne transite qu'en entrée, jamais en sortie."""

    value: str
