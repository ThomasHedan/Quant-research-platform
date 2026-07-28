"""Tests de edgelab.research.event_study (Phase 2)."""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy as np
import polars as pl
import pytest
from edgelab.research import EventStudyConfig, run_event_study
from edgelab.universe.instrument import Instrument

HORIZON = 10
CONFIG = EventStudyConfig(
    horizons=(1, 5, 10, 20), primary_horizon=10, lag_bars=(1, 2, 5, 10), vol_window=20
)


def _make_bars(
    n: int, *, seed: int, log_returns_override: np.ndarray | None = None
) -> tuple[pl.DataFrame, list[datetime], np.ndarray]:
    rng = np.random.default_rng(seed)
    timestamps = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(n)]
    log_returns = (
        log_returns_override if log_returns_override is not None else rng.normal(0.0, 0.0004, n)
    )
    log_prices = np.cumsum(log_returns) + math.log(1.10)
    prices = np.exp(log_prices)
    bars = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": prices * 1.0001,
            "low": prices * 0.9999,
            "close": prices,
            "volume": 100.0,
        }
    )
    return bars, timestamps, log_returns


def _random_signal(n: int, timestamps: list[datetime], *, seed: int, rate: float) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    values = np.where(rng.random(n) < rate, 1.0, 0.0)
    return pl.DataFrame({"timestamp": timestamps, "value": values})


def test_run_event_study_rejects_empty_instrument_list(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Un event study sans instrument n'a rien à mesurer."""
    with pytest.raises(ValueError, match="empty"):
        run_event_study([], {}, {}, CONFIG)


def test_run_event_study_rejects_an_instrument_missing_signal_or_bars(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Un instrument sans signal ou barres fournis est refusé explicitement."""
    instrument = make_research_instrument("EURUSD")

    with pytest.raises(ValueError, match="EURUSD"):
        run_event_study([instrument], {}, {}, CONFIG)


def test_pure_random_signal_is_not_significant(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Critère d'acceptation Phase 2 : signal aléatoire pur -> t-stat non significatif."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(3000, seed=1)
    signal = _random_signal(3000, timestamps, seed=2, rate=0.03)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    agg = report.aggregate_stats(HORIZON)
    assert agg.is_significant is False
    assert abs(agg.aggregate_t_stat) < CONFIG.significance_t


def test_injected_edge_is_recovered_within_ten_percent(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Critère d'acceptation Phase 2 : un edge injecté connu est retrouvé à moins de 10%."""
    injected_edge = 0.004  # 40 bps cumulés sur l'horizon
    n = 4000
    rng = np.random.default_rng(7)
    log_returns = rng.normal(0.0, 0.0004, n)
    values = np.zeros(n)

    # Signaux espacés d'au moins 2x l'horizon : aucun chevauchement de fenêtre forward.
    i = 50
    while i < n - 2 * HORIZON:
        values[i] = 1.0
        log_returns[i + 1 : i + 1 + HORIZON] += injected_edge / HORIZON
        i += 2 * HORIZON

    bars, timestamps, _ = _make_bars(n, seed=8, log_returns_override=log_returns)
    signal = pl.DataFrame({"timestamp": timestamps, "value": values})
    instrument = make_research_instrument("TEST")  # coût nul : isole la mesure du signal

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    recovered = report.per_instrument["TEST"].horizon_stats(HORIZON).mean_return
    assert recovered == pytest.approx(injected_edge, rel=0.10)


def test_mono_instrument_report_carries_a_width_warning(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Critère d'acceptation Phase 2 : un rapport mono-instrument porte un avertissement."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(500, seed=3)
    signal = _random_signal(500, timestamps, seed=4, rate=0.05)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    assert report.is_mono_instrument is True
    assert report.width_warning is not None
    assert "instrument" in report.width_warning.lower()


def test_multi_instrument_report_has_no_width_warning(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Un rapport sur plusieurs instruments ne porte pas l'avertissement de largeur."""
    instruments = [make_research_instrument(f"SYM{k}") for k in range(3)]
    signals = {}
    bars_by_symbol = {}
    for k, instrument in enumerate(instruments):
        bars, timestamps, _ = _make_bars(500, seed=10 + k)
        signals[instrument.symbol] = _random_signal(500, timestamps, seed=20 + k, rate=0.05)
        bars_by_symbol[instrument.symbol] = bars

    report = run_event_study(instruments, signals, bars_by_symbol, CONFIG)

    assert report.is_mono_instrument is False
    assert report.width_warning is None


def test_aggregate_t_stat_matches_the_ic_times_sqrt_n_formula(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """L'agrégation suit IR ~ IC x sqrt(N) : elle égale mean(t_i) x sqrt(n_instruments)."""
    instruments = [make_research_instrument(f"SYM{k}") for k in range(4)]
    signals = {}
    bars_by_symbol = {}
    for k, instrument in enumerate(instruments):
        bars, timestamps, _ = _make_bars(800, seed=30 + k)
        signals[instrument.symbol] = _random_signal(800, timestamps, seed=40 + k, rate=0.05)
        bars_by_symbol[instrument.symbol] = bars

    report = run_event_study(instruments, signals, bars_by_symbol, CONFIG)

    agg = report.aggregate_stats(HORIZON)
    per_instrument_t = [
        report.per_instrument[i.symbol].horizon_stats(HORIZON).t_stat for i in instruments
    ]
    expected = float(np.mean(per_instrument_t)) * math.sqrt(len(instruments))
    assert agg.aggregate_t_stat == pytest.approx(expected)


def test_horizon_comparison_reports_both_triggered_and_naive_side_by_side(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Règle naïve de contrôle obligatoire : les deux jeux de stats sont toujours présents."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(1000, seed=5)
    signal = _random_signal(1000, timestamps, seed=6, rate=0.05)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    comparison = report.per_instrument["TEST"].horizon_comparisons[0]
    assert comparison.triggered.n > 0
    assert comparison.naive.n > comparison.triggered.n  # la naïve tourne sur toutes les barres


def test_concentration_is_silenced_when_t_stat_is_below_one(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Diagnostic de concentration tu quand |t| < 1 à l'horizon primaire (spec Phase 2)."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(2000, seed=11)
    signal = _random_signal(2000, timestamps, seed=12, rate=0.03)  # pas d'edge injecté

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    result = report.per_instrument["TEST"]
    if abs(result.horizon_stats(HORIZON).t_stat) < 1.0:
        assert result.concentration is None


def test_concentration_is_reported_when_edge_is_strong(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Un edge fort à l'horizon primaire fait apparaître la métrique de concentration."""
    n = 4000
    rng = np.random.default_rng(21)
    log_returns = rng.normal(0.0, 0.0002, n)
    values = np.zeros(n)
    i = 50
    while i < n - 2 * HORIZON:
        values[i] = 1.0
        log_returns[i + 1 : i + 1 + HORIZON] += 0.01 / HORIZON
        i += 2 * HORIZON

    bars, timestamps, _ = _make_bars(n, seed=22, log_returns_override=log_returns)
    signal = pl.DataFrame({"timestamp": timestamps, "value": values})
    instrument = make_research_instrument("TEST")

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    result = report.per_instrument["TEST"]
    assert abs(result.horizon_stats(HORIZON).t_stat) >= 1.0
    assert result.concentration is not None
    assert result.concentration.n_excluded > 0


def test_mae_mfe_are_computed_for_every_horizon(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Une distribution MAE/MFE est calculée pour chaque horizon configuré."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(1000, seed=13)
    signal = _random_signal(1000, timestamps, seed=14, rate=0.05)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    mae_mfe_horizons = {m.horizon for m in report.per_instrument["TEST"].mae_mfe_stats}
    assert mae_mfe_horizons == set(CONFIG.horizons)
    for stats in report.per_instrument["TEST"].mae_mfe_stats:
        if stats.n > 0:
            assert stats.mean_mae <= 0  # une excursion adverse est, par construction, <= 0
            assert stats.mean_mfe >= 0


def test_subperiod_stats_partition_signals_chronologically(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Les sous-périodes couvrent l'ensemble des signaux déclenchés, dans l'ordre chronologique."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(2000, seed=15)
    signal = _random_signal(2000, timestamps, seed=16, rate=0.05)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    subperiods = report.per_instrument["TEST"].subperiod_stats
    assert len(subperiods) <= CONFIG.n_subperiods
    assert [p.period_index for p in subperiods] == sorted(p.period_index for p in subperiods)
    for earlier, later in pairwise(subperiods):
        assert earlier.end <= later.start


def test_lag_stats_are_computed_for_every_configured_lag(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Une statistique de décroissance au décalage existe pour chaque lag configuré."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(1500, seed=17)
    signal = _random_signal(1500, timestamps, seed=18, rate=0.05)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    lag_values = {ls.lag_bars for ls in report.per_instrument["TEST"].lag_stats}
    assert lag_values == set(CONFIG.lag_bars)


def test_vol_tercile_stats_split_into_at_most_three_buckets(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """La volatilité réalisée au signal se répartit en au plus trois terciles."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(2000, seed=19)
    signal = _random_signal(2000, timestamps, seed=20, rate=0.05)

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    tercile_names = {v.tercile for v in report.per_instrument["TEST"].vol_tercile_stats}
    assert tercile_names <= {"low", "mid", "high"}


def test_short_direction_signal_is_measured_correctly(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Un signal court (valeur négative) mesure un rendement inversé, pas un rendement long."""
    n = 500
    timestamps = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(n)]
    # Prix strictement croissant : une position longue gagnerait, une position courte perd.
    prices = np.linspace(1.10, 1.20, n)
    bars = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": prices * 1.0001,
            "low": prices * 0.9999,
            "close": prices,
            "volume": 100.0,
        }
    )
    values = np.zeros(n)
    values[10] = -1.0  # signal court unique
    signal = pl.DataFrame({"timestamp": timestamps, "value": values})
    instrument = make_research_instrument("TEST")

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    mean_return = report.per_instrument["TEST"].horizon_stats(HORIZON).mean_return
    assert mean_return < 0  # prix monte, position courte : rendement négatif


def test_a_signal_that_never_fires_produces_empty_but_valid_stats(
    make_research_instrument: Callable[..., Instrument],
) -> None:
    """Un signal qui ne se déclenche jamais ne fait planter aucun diagnostic."""
    instrument = make_research_instrument("TEST")
    bars, timestamps, _ = _make_bars(500, seed=23)
    signal = pl.DataFrame({"timestamp": timestamps, "value": np.zeros(500)})

    report = run_event_study([instrument], {"TEST": signal}, {"TEST": bars}, CONFIG)

    result = report.per_instrument["TEST"]
    assert result.n_signals == 0
    assert all(c.triggered.n == 0 for c in result.horizon_comparisons)
    assert all(m.n == 0 for m in result.mae_mfe_stats)
    assert result.subperiod_stats == ()
    assert result.vol_tercile_stats == ()
    assert result.concentration is None
