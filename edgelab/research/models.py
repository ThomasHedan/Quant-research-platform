"""Modèles du module event study (Phase 2) : configuration et résultats."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

CONCENTRATION_MIN_T = 1.0
"""Seuil |t| en dessous duquel la métrique de concentration est tue (spec Phase 2)."""

_MIN_VOL_WINDOW = 2
_MIN_SUBPERIODS = 2
_MAX_TOP_PCT_EXCLUDE = 0.5


class EventStudyConfig(BaseModel):
    """Paramètres d'un event study, partagés par tous les instruments de l'univers."""

    model_config = ConfigDict(frozen=True)

    horizons: tuple[int, ...] = (1, 5, 10, 20)
    primary_horizon: int = 10
    lag_bars: tuple[int, ...] = (1, 2, 5, 10)
    vol_window: int = 20
    n_subperiods: int = 4
    top_pct_exclude: float = 0.05
    significance_t: float = 1.96

    @model_validator(mode="after")
    def _validate(self) -> EventStudyConfig:
        if not self.horizons or any(h <= 0 for h in self.horizons):
            raise ValueError("horizons must be non-empty and strictly positive")
        if self.primary_horizon not in self.horizons:
            raise ValueError("primary_horizon must be one of horizons")
        if any(lag <= 0 for lag in self.lag_bars):
            raise ValueError("lag_bars must be strictly positive")
        if self.vol_window < _MIN_VOL_WINDOW:
            raise ValueError("vol_window must be >= 2")
        if self.n_subperiods < _MIN_SUBPERIODS:
            raise ValueError("n_subperiods must be >= 2")
        if not 0 < self.top_pct_exclude < _MAX_TOP_PCT_EXCLUDE:
            raise ValueError("top_pct_exclude must be in (0, 0.5)")
        if self.significance_t <= 0:
            raise ValueError("significance_t must be positive")
        return self


class HorizonStats(BaseModel):
    """Statistiques de rendement forward net de coûts, à un horizon donné."""

    model_config = ConfigDict(frozen=True)

    horizon: int
    n: int
    mean_return: float
    median_return: float
    std_return: float
    t_stat: float
    p_value: float
    hit_rate: float


class HorizonComparison(BaseModel):
    """Le déclencheur, comparé côte à côte à sa règle naïve de contrôle, à un horizon donné."""

    model_config = ConfigDict(frozen=True)

    horizon: int
    triggered: HorizonStats
    naive: HorizonStats
    mean_diff: float
    comparison_p_value: float
    improves_on_naive: bool


class MaeMfeStats(BaseModel):
    """Excursion adverse/favorable maximale, moyenne et médiane, à un horizon donné."""

    model_config = ConfigDict(frozen=True)

    horizon: int
    n: int
    mean_mae: float
    median_mae: float
    mean_mfe: float
    median_mfe: float


class SubperiodStats(BaseModel):
    """Stabilité du rendement forward par sous-période chronologique (horizon primaire)."""

    model_config = ConfigDict(frozen=True)

    period_index: int
    start: datetime
    end: datetime
    n: int
    mean_return: float
    t_stat: float


class VolTercile(BaseModel):
    """Un tercile de volatilité réalisée au moment du signal (horizon primaire)."""

    model_config = ConfigDict(frozen=True)

    tercile: str
    n: int
    mean_return: float
    t_stat: float


class LagStats(BaseModel):
    """Espérance à l'horizon primaire si l'entrée est décalée de `lag_bars` barres."""

    model_config = ConfigDict(frozen=True)

    lag_bars: int
    n: int
    mean_return: float
    t_stat: float


class ConcentrationStats(BaseModel):
    """Espérance hors le `top_pct_exclude` des meilleurs trades, à l'horizon primaire.

    Absent (`None` sur `InstrumentEventStudyResult.concentration`) quand
    `|t| < CONCENTRATION_MIN_T` : le dénominateur d'un ratio exploserait, et
    la métrique n'a rien à dire tant que l'edge de base est indiscernable de
    zéro (spec Phase 2).
    """

    model_config = ConfigDict(frozen=True)

    n_excluded: int
    mean_return_excluding_top: float


class InstrumentEventStudyResult(BaseModel):
    """Résultat complet de l'event study pour un instrument de l'univers."""

    model_config = ConfigDict(frozen=True)

    instrument_symbol: str
    n_signals: int
    horizon_comparisons: tuple[HorizonComparison, ...]
    mae_mfe_stats: tuple[MaeMfeStats, ...]
    subperiod_stats: tuple[SubperiodStats, ...]
    vol_tercile_stats: tuple[VolTercile, ...]
    lag_stats: tuple[LagStats, ...]
    concentration: ConcentrationStats | None

    def horizon_stats(self, horizon: int) -> HorizonStats:
        """Statistiques déclenchées à `horizon`.

        Raises:
            KeyError: si `horizon` n'a pas été calculé.
        """
        for comparison in self.horizon_comparisons:
            if comparison.horizon == horizon:
                return comparison.triggered
        raise KeyError(f"no stats computed for horizon={horizon}")


class AggregateHorizonStats(BaseModel):
    """Statistiques agrégées sur l'univers, à un horizon donné (IR ~ IC x sqrt(N), Grinold).

    `aggregate_t_stat` combine les t-stats *par instrument* — pas les trades
    bruts regroupés dans un seul test — pour refléter le gain de puissance
    d'un edge présent sur plusieurs marchés décorrélés.
    """

    model_config = ConfigDict(frozen=True)

    horizon: int
    n_instruments: int
    mean_t_stat_per_instrument: float
    aggregate_t_stat: float
    pooled_mean_return: float
    is_significant: bool


class EventStudyReport(BaseModel):
    """Rapport d'event study complet sur un univers d'instruments (ou un sous-ensemble)."""

    model_config = ConfigDict(frozen=True)

    config: EventStudyConfig
    aggregate_horizon_stats: tuple[AggregateHorizonStats, ...]
    per_instrument: dict[str, InstrumentEventStudyResult]
    is_mono_instrument: bool
    width_warning: str | None

    def aggregate_stats(self, horizon: int) -> AggregateHorizonStats:
        """Statistiques agrégées à `horizon`.

        Raises:
            KeyError: si `horizon` n'a pas été calculé.
        """
        for stats in self.aggregate_horizon_stats:
            if stats.horizon == horizon:
                return stats
        raise KeyError(f"no aggregate stats computed for horizon={horizon}")
