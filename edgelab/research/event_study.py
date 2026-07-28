"""Event study (Phase 2) : mesurer un signal sans aucune gestion de position.

Sortie à horizon fixe, jamais de SL/TP — c'est l'étape qui sépare la qualité
du signal de la qualité de la gestion du risque (CLAUDE.md §4 Phase 2). Le
mode multi-instruments est le défaut : le t-stat agrégé combine les t-stats
*par instrument* via IR ~ IC x sqrt(N) (Grinold), pas en regroupant tous les
trades de l'univers dans un seul test — un edge qui n'existe que sur un seul
marché est du bruit sélectionné, et `width_warning` le rappelle.

Limite connue : la jointure signal/barres et le coût par instance utilisent
une boucle Python, pas une opération Polars vectorisée. Correct et
suffisant pour la taille d'un event study de recherche ; pas dimensionné
pour rejouer un signal sur plusieurs Go de M1 en un seul appel — voir
`edgelab/research/README.md`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

import numpy as np
import polars as pl
from numpy.typing import NDArray

from edgelab.costs.models import OrderType
from edgelab.research.models import (
    CONCENTRATION_MIN_T,
    AggregateHorizonStats,
    ConcentrationStats,
    EventStudyConfig,
    EventStudyReport,
    HorizonComparison,
    HorizonStats,
    InstrumentEventStudyResult,
    LagStats,
    MaeMfeStats,
    SubperiodStats,
    VolTercile,
)
from edgelab.research.stats import (
    hit_rate,
    mean_excluding_top,
    one_sample_t_test,
    tercile_labels,
    two_sample_t_test,
)
from edgelab.universe.instrument import Instrument

MONO_INSTRUMENT_WARNING = (
    "Event study sur un seul instrument : IR ~ IC x sqrt(N) ne joue pas, ceci est un "
    "signal de largeur 1. Un edge qui n'existe que sur un seul marché de l'univers est "
    "du bruit sélectionné, pas une conclusion robuste."
)


class _PriceSeries:
    """Vue en lecture d'une série de barres, indexée par position pour l'event study."""

    def __init__(self, bars: pl.DataFrame) -> None:
        sorted_bars = bars.sort("timestamp")
        self.timestamps: list[datetime] = sorted_bars["timestamp"].to_list()
        self.closes: NDArray[np.float64] = sorted_bars["close"].to_numpy()
        self.highs: NDArray[np.float64] = sorted_bars["high"].to_numpy()
        self.lows: NDArray[np.float64] = sorted_bars["low"].to_numpy()
        self.n_bars = len(sorted_bars)
        self._index_by_ts = {ts: i for i, ts in enumerate(self.timestamps)}

    def index_of(self, timestamp: datetime) -> int | None:
        """Position de la barre à `timestamp`, ou `None` si absente."""
        return self._index_by_ts.get(timestamp)

    def compute_realized_vol(self, window: int) -> NDArray[np.float64]:
        """Écart-type glissant des rendements log, `NaN` tant que l'historique est insuffisant."""
        log_returns = pl.Series("_r", np.diff(np.log(self.closes), prepend=np.nan))
        return log_returns.rolling_std(window_size=window).to_numpy()


def run_event_study(
    instruments: Sequence[Instrument],
    signals: dict[str, pl.DataFrame],
    bars: dict[str, pl.DataFrame],
    config: EventStudyConfig,
) -> EventStudyReport:
    """Lance l'event study sur `instruments` (l'univers, ou un sous-ensemble explicite).

    `signals[symbol]` : colonnes `timestamp`, `value` (non nul = signal actif,
    signe = direction longue/courte). `bars[symbol]` : colonnes `timestamp`,
    `open`, `high`, `low`, `close`.

    Raises:
        ValueError: si `instruments` est vide, ou si un instrument n'a pas de
            signal ou de barres fournis.
    """
    if not instruments:
        raise ValueError("instruments must not be empty")

    per_instrument: dict[str, InstrumentEventStudyResult] = {}
    for instrument in instruments:
        symbol = instrument.symbol
        if symbol not in signals or symbol not in bars:
            raise ValueError(f"missing signals or bars for instrument '{symbol}'")
        per_instrument[symbol] = _run_single_instrument(
            instrument, signals[symbol], bars[symbol], config
        )

    aggregate_stats = tuple(
        _aggregate_horizon(horizon, per_instrument, config) for horizon in config.horizons
    )
    is_mono = len(instruments) == 1
    return EventStudyReport(
        config=config,
        aggregate_horizon_stats=aggregate_stats,
        per_instrument=per_instrument,
        is_mono_instrument=is_mono,
        width_warning=MONO_INSTRUMENT_WARNING if is_mono else None,
    )


def _aggregate_horizon(
    horizon: int,
    per_instrument: dict[str, InstrumentEventStudyResult],
    config: EventStudyConfig,
) -> AggregateHorizonStats:
    horizon_stats = [result.horizon_stats(horizon) for result in per_instrument.values()]
    n_instruments = len(horizon_stats)
    t_stats = np.array([s.t_stat for s in horizon_stats])
    means = np.array([s.mean_return for s in horizon_stats])
    mean_t = float(np.mean(t_stats)) if n_instruments else 0.0
    aggregate_t = mean_t * math.sqrt(n_instruments) if n_instruments else 0.0
    return AggregateHorizonStats(
        horizon=horizon,
        n_instruments=n_instruments,
        mean_t_stat_per_instrument=mean_t,
        aggregate_t_stat=aggregate_t,
        pooled_mean_return=float(np.mean(means)) if n_instruments else 0.0,
        is_significant=abs(aggregate_t) >= config.significance_t,
    )


def _run_single_instrument(
    instrument: Instrument,
    signal: pl.DataFrame,
    bars: pl.DataFrame,
    config: EventStudyConfig,
) -> InstrumentEventStudyResult:
    prices = _PriceSeries(bars)
    entry_idx, directions = _resolve_signal_entries(signal, prices)
    n_signals = entry_idx.size

    horizon_comparisons = tuple(
        _horizon_comparison(instrument, prices, entry_idx, directions, horizon)
        for horizon in config.horizons
    )
    mae_mfe_stats = tuple(
        _mae_mfe_stats(prices, entry_idx, directions, horizon) for horizon in config.horizons
    )

    primary_returns, primary_entry_idx = _forward_returns(
        instrument, prices, entry_idx, directions, config.primary_horizon
    )
    subperiod_stats = _subperiod_stats(prices, primary_entry_idx, primary_returns, config)
    vol_tercile_stats = _vol_tercile_stats(prices, primary_entry_idx, primary_returns, config)
    lag_stats = tuple(
        _lag_stats(instrument, prices, entry_idx, directions, lag, config.primary_horizon)
        for lag in config.lag_bars
    )
    concentration = _concentration_stats(primary_returns, config)

    return InstrumentEventStudyResult(
        instrument_symbol=instrument.symbol,
        n_signals=n_signals,
        horizon_comparisons=horizon_comparisons,
        mae_mfe_stats=mae_mfe_stats,
        subperiod_stats=subperiod_stats,
        vol_tercile_stats=vol_tercile_stats,
        lag_stats=lag_stats,
        concentration=concentration,
    )


def _resolve_signal_entries(
    signal: pl.DataFrame, prices: _PriceSeries
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Résout les timestamps de signal en positions de barre + direction (+1/-1)."""
    active = signal.sort("timestamp").filter(pl.col("value") != 0)
    indices: list[int] = []
    directions: list[float] = []
    for row in active.iter_rows(named=True):
        idx = prices.index_of(row["timestamp"])
        if idx is not None:
            indices.append(idx)
            directions.append(1.0 if row["value"] > 0 else -1.0)
    return np.array(indices, dtype=np.int64), np.array(directions, dtype=np.float64)


def _round_trip_cost_as_return(
    instrument: Instrument, entry_timestamps: list[datetime], entry_prices: NDArray[np.float64]
) -> NDArray[np.float64]:
    costs = [
        instrument.cost_model.round_trip_cost(order_type=OrderType.MARKET, timestamp=ts).total
        for ts in entry_timestamps
    ]
    return np.array(costs, dtype=np.float64) / entry_prices


def _forward_returns(
    instrument: Instrument,
    prices: _PriceSeries,
    entry_idx: NDArray[np.int64],
    directions: NDArray[np.float64],
    horizon: int,
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Rendements forward net de coûts à `horizon`, et les positions d'entrée retenues."""
    valid = entry_idx + horizon < prices.n_bars
    valid_idx = entry_idx[valid]
    valid_directions = directions[valid]
    if valid_idx.size == 0:
        return np.array([], dtype=np.float64), valid_idx

    entry_prices = prices.closes[valid_idx]
    exit_prices = prices.closes[valid_idx + horizon]
    raw_returns = valid_directions * np.log(exit_prices / entry_prices)
    entry_timestamps = [prices.timestamps[i] for i in valid_idx]
    costs = _round_trip_cost_as_return(instrument, entry_timestamps, entry_prices)
    return raw_returns - costs, valid_idx


def _to_horizon_stats(horizon: int, returns: NDArray[np.float64]) -> HorizonStats:
    t_stat, p_value = one_sample_t_test(returns)
    return HorizonStats(
        horizon=horizon,
        n=returns.size,
        mean_return=float(np.mean(returns)) if returns.size else 0.0,
        median_return=float(np.median(returns)) if returns.size else 0.0,
        std_return=float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0,
        t_stat=t_stat,
        p_value=p_value,
        hit_rate=hit_rate(returns),
    )


def _horizon_comparison(
    instrument: Instrument,
    prices: _PriceSeries,
    entry_idx: NDArray[np.int64],
    directions: NDArray[np.float64],
    horizon: int,
) -> HorizonComparison:
    triggered_returns, _ = _forward_returns(instrument, prices, entry_idx, directions, horizon)

    naive_idx = np.arange(prices.n_bars, dtype=np.int64)
    naive_directions = np.ones_like(naive_idx, dtype=np.float64)
    naive_returns, _ = _forward_returns(instrument, prices, naive_idx, naive_directions, horizon)

    triggered_stats = _to_horizon_stats(horizon, triggered_returns)
    naive_stats = _to_horizon_stats(horizon, naive_returns)
    _, comparison_p = two_sample_t_test(triggered_returns, naive_returns)
    mean_diff = triggered_stats.mean_return - naive_stats.mean_return
    return HorizonComparison(
        horizon=horizon,
        triggered=triggered_stats,
        naive=naive_stats,
        mean_diff=mean_diff,
        comparison_p_value=comparison_p,
        improves_on_naive=bool(mean_diff > 0 and comparison_p < 0.05),  # noqa: PLR2004
    )


def _mae_mfe_stats(
    prices: _PriceSeries,
    entry_idx: NDArray[np.int64],
    directions: NDArray[np.float64],
    horizon: int,
) -> MaeMfeStats:
    valid = entry_idx + horizon < prices.n_bars
    valid_idx = entry_idx[valid]
    valid_directions = directions[valid]
    if valid_idx.size == 0:
        return MaeMfeStats(
            horizon=horizon, n=0, mean_mae=0.0, median_mae=0.0, mean_mfe=0.0, median_mfe=0.0
        )

    entry_prices = prices.closes[valid_idx]
    maes = np.empty(valid_idx.size, dtype=np.float64)
    mfes = np.empty(valid_idx.size, dtype=np.float64)
    for pos, (i, direction, entry_price) in enumerate(
        zip(valid_idx, valid_directions, entry_prices, strict=True)
    ):
        window = slice(i, i + horizon + 1)
        adverse_prices = prices.lows[window] if direction > 0 else prices.highs[window]
        favorable_prices = prices.highs[window] if direction > 0 else prices.lows[window]
        adverse_excursions = direction * (adverse_prices - entry_price) / entry_price
        favorable_excursions = direction * (favorable_prices - entry_price) / entry_price
        maes[pos] = float(np.min(adverse_excursions))
        mfes[pos] = float(np.max(favorable_excursions))

    return MaeMfeStats(
        horizon=horizon,
        n=valid_idx.size,
        mean_mae=float(np.mean(maes)),
        median_mae=float(np.median(maes)),
        mean_mfe=float(np.mean(mfes)),
        median_mfe=float(np.median(mfes)),
    )


def _subperiod_stats(
    prices: _PriceSeries,
    entry_idx: NDArray[np.int64],
    returns: NDArray[np.float64],
    config: EventStudyConfig,
) -> tuple[SubperiodStats, ...]:
    if entry_idx.size == 0:
        return ()
    order = np.argsort(entry_idx)
    ordered_idx = entry_idx[order]
    ordered_returns = returns[order]
    buckets = np.array_split(np.arange(ordered_idx.size), config.n_subperiods)

    stats: list[SubperiodStats] = []
    for period_index, bucket in enumerate(buckets):
        if bucket.size == 0:
            continue
        bucket_idx = ordered_idx[bucket]
        bucket_returns = ordered_returns[bucket]
        t_stat, _ = one_sample_t_test(bucket_returns)
        stats.append(
            SubperiodStats(
                period_index=period_index,
                start=prices.timestamps[int(bucket_idx.min())],
                end=prices.timestamps[int(bucket_idx.max())],
                n=bucket_returns.size,
                mean_return=float(np.mean(bucket_returns)),
                t_stat=t_stat,
            )
        )
    return tuple(stats)


def _vol_tercile_stats(
    prices: _PriceSeries,
    entry_idx: NDArray[np.int64],
    returns: NDArray[np.float64],
    config: EventStudyConfig,
) -> tuple[VolTercile, ...]:
    if entry_idx.size == 0:
        return ()
    realized_vol = prices.compute_realized_vol(config.vol_window)
    vol_at_entry = realized_vol[entry_idx]
    has_vol = ~np.isnan(vol_at_entry)
    if has_vol.sum() < 3:  # noqa: PLR2004 — il faut au moins un point par tercile
        return ()

    labels = tercile_labels(vol_at_entry[has_vol])
    filtered_returns = returns[has_vol]
    stats: list[VolTercile] = []
    for tercile in ("low", "mid", "high"):
        mask = labels == tercile
        if not mask.any():
            continue
        bucket_returns = filtered_returns[mask]
        t_stat, _ = one_sample_t_test(bucket_returns)
        stats.append(
            VolTercile(
                tercile=tercile,
                n=bucket_returns.size,
                mean_return=float(np.mean(bucket_returns)),
                t_stat=t_stat,
            )
        )
    return tuple(stats)


def _lag_stats(  # noqa: PLR0913, PLR0917 — chaque paramètre est nécessaire au calcul
    instrument: Instrument,
    prices: _PriceSeries,
    entry_idx: NDArray[np.int64],
    directions: NDArray[np.float64],
    lag: int,
    primary_horizon: int,
) -> LagStats:
    shifted_idx = entry_idx + lag
    in_range = shifted_idx < prices.n_bars
    returns, _ = _forward_returns(
        instrument, prices, shifted_idx[in_range], directions[in_range], primary_horizon
    )
    t_stat, _ = one_sample_t_test(returns)
    return LagStats(
        lag_bars=lag,
        n=returns.size,
        mean_return=float(np.mean(returns)) if returns.size else 0.0,
        t_stat=t_stat,
    )


def _concentration_stats(
    primary_returns: NDArray[np.float64], config: EventStudyConfig
) -> ConcentrationStats | None:
    t_stat, _ = one_sample_t_test(primary_returns)
    if abs(t_stat) < CONCENTRATION_MIN_T:
        return None
    mean_excl, n_excluded = mean_excluding_top(primary_returns, config.top_pct_exclude)
    return ConcentrationStats(n_excluded=n_excluded, mean_return_excluding_top=mean_excl)
