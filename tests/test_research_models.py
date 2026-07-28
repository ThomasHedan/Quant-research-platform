"""Tests de edgelab.research.models (Phase 2)."""

import pytest
from edgelab.research.models import (
    AggregateHorizonStats,
    EventStudyConfig,
    EventStudyReport,
    HorizonComparison,
    HorizonStats,
    InstrumentEventStudyResult,
)


def _make_horizon_stats(horizon: int) -> HorizonStats:
    return HorizonStats(
        horizon=horizon,
        n=10,
        mean_return=0.001,
        median_return=0.001,
        std_return=0.01,
        t_stat=1.0,
        p_value=0.3,
        hit_rate=0.5,
    )


def test_event_study_config_defaults_are_valid() -> None:
    """La configuration par défaut passe sa propre validation."""
    EventStudyConfig()


def test_event_study_config_rejects_empty_horizons() -> None:
    """Au moins un horizon est requis."""
    with pytest.raises(ValueError, match="horizons"):
        EventStudyConfig(horizons=())


def test_event_study_config_rejects_non_positive_horizon() -> None:
    """Un horizon nul ou négatif n'a pas de sens."""
    with pytest.raises(ValueError, match="horizons"):
        EventStudyConfig(horizons=(0, 5))


def test_event_study_config_rejects_primary_horizon_not_in_horizons() -> None:
    """L'horizon primaire doit faire partie des horizons calculés."""
    with pytest.raises(ValueError, match="primary_horizon"):
        EventStudyConfig(horizons=(1, 5), primary_horizon=10)


def test_event_study_config_rejects_non_positive_lag() -> None:
    """Un décalage nul ou négatif n'a pas de sens (0 est déjà le cas de base)."""
    with pytest.raises(ValueError, match="lag_bars"):
        EventStudyConfig(lag_bars=(0, 1))


def test_event_study_config_rejects_top_pct_exclude_out_of_range() -> None:
    """`top_pct_exclude` doit rester dans (0, 0.5)."""
    with pytest.raises(ValueError, match="top_pct_exclude"):
        EventStudyConfig(top_pct_exclude=0.5)


def test_instrument_result_horizon_stats_finds_the_matching_comparison() -> None:
    """`horizon_stats` renvoie les stats déclenchées de la bonne comparaison."""
    stats_10 = _make_horizon_stats(10)
    comparison = HorizonComparison(
        horizon=10,
        triggered=stats_10,
        naive=_make_horizon_stats(10),
        mean_diff=0.0,
        comparison_p_value=1.0,
        improves_on_naive=False,
    )
    result = InstrumentEventStudyResult(
        instrument_symbol="EURUSD",
        n_signals=10,
        horizon_comparisons=(comparison,),
        mae_mfe_stats=(),
        subperiod_stats=(),
        vol_tercile_stats=(),
        lag_stats=(),
        concentration=None,
    )

    assert result.horizon_stats(10) == stats_10


def test_instrument_result_horizon_stats_raises_for_unknown_horizon() -> None:
    """Demander un horizon jamais calculé lève une `KeyError` explicite."""
    result = InstrumentEventStudyResult(
        instrument_symbol="EURUSD",
        n_signals=0,
        horizon_comparisons=(),
        mae_mfe_stats=(),
        subperiod_stats=(),
        vol_tercile_stats=(),
        lag_stats=(),
        concentration=None,
    )

    with pytest.raises(KeyError):
        result.horizon_stats(10)


def test_report_aggregate_stats_finds_the_matching_horizon() -> None:
    """`aggregate_stats` renvoie les statistiques agrégées du bon horizon."""
    agg_10 = AggregateHorizonStats(
        horizon=10,
        n_instruments=1,
        mean_t_stat_per_instrument=1.0,
        aggregate_t_stat=1.0,
        pooled_mean_return=0.001,
        is_significant=False,
    )
    report = EventStudyReport(
        config=EventStudyConfig(),
        aggregate_horizon_stats=(agg_10,),
        per_instrument={},
        is_mono_instrument=True,
        width_warning="warning",
    )

    assert report.aggregate_stats(10) == agg_10


def test_report_aggregate_stats_raises_for_unknown_horizon() -> None:
    """Demander un horizon jamais agrégé lève une `KeyError` explicite."""
    report = EventStudyReport(
        config=EventStudyConfig(),
        aggregate_horizon_stats=(),
        per_instrument={},
        is_mono_instrument=True,
        width_warning=None,
    )

    with pytest.raises(KeyError):
        report.aggregate_stats(10)
