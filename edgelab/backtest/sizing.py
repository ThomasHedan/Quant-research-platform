"""Dimensionnement des positions (Phase 3) : risque fixe en %, stop en multiple d'ATR.

La normalisation par la volatilité est le défaut : deux instruments à
volatilité différente reçoivent une taille de position différente pour un
même risque en capital, plutôt qu'une même quantité brute qui les exposerait
inégalement (CLAUDE.md §4, Phase 3).
"""

from __future__ import annotations

import polars as pl

_MIN_RISK_PCT = 0.0
_MAX_RISK_PCT = 1.0


def average_true_range(bars: pl.DataFrame, *, period: int) -> pl.Series:
    """ATR par moyenne mobile simple du vrai range (approximation de l'ATR de Wilder).

    Simplification assumée : une moyenne mobile simple sur `period` barres,
    pas le lissage récursif de Wilder — suffisant comme entrée de
    dimensionnement, documenté dans `backtest/README.md`.

    Raises:
        ValueError: si `period` n'est pas strictement positif.
    """
    if period <= 0:
        raise ValueError("period must be positive")

    prev_close = pl.col("close").shift(1)
    true_range = pl.max_horizontal(
        (pl.col("high") - pl.col("low")).abs(),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    return bars.select(true_range.rolling_mean(window_size=period).alias("atr"))["atr"]


def position_size_fixed_risk(*, capital: float, risk_pct: float, stop_distance: float) -> float:
    """Quantité dérivée d'un risque fixe en % du capital et d'une distance de stop en prix.

    Raises:
        ValueError: si `risk_pct` n'est pas dans (0, 1], si `stop_distance`
            n'est pas strictement positif, ou si `capital` n'est pas positif.
    """
    if not _MIN_RISK_PCT < risk_pct <= _MAX_RISK_PCT:
        raise ValueError("risk_pct must be in (0, 1]")
    if stop_distance <= 0.0:
        raise ValueError("stop_distance must be positive")
    if capital <= 0.0:
        raise ValueError("capital must be positive")
    return (capital * risk_pct) / stop_distance
