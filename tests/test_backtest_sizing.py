"""Tests de edgelab.backtest.sizing (Phase 3)."""

import polars as pl
import pytest
from edgelab.backtest.sizing import average_true_range, position_size_fixed_risk


def test_average_true_range_rejects_non_positive_period() -> None:
    """`period` doit être strictement positif."""
    bars = pl.DataFrame({"high": [1.0, 2.0], "low": [0.5, 1.5], "close": [0.8, 1.8]})

    with pytest.raises(ValueError, match="period"):
        average_true_range(bars, period=0)


def test_average_true_range_matches_hand_computed_values_on_a_simple_series() -> None:
    """Critère de propriété connue : l'ATR reproduit un calcul de vrai range fait à la main.

    Barres : (H, L, C) = (10, 8, 9), (11, 9, 10), (12, 9, 11).
    Vrai range : barre 0 = 10-8 = 2 (pas de clôture précédente, high-low).
    Barre 1 = max(11-9, |11-9|, |9-9|) = 2. Barre 2 = max(12-9, |12-10|, |9-10|) = 3.
    ATR(period=2) = moyenne mobile du vrai range : [NaN, 2.0, 2.5].
    """
    bars = pl.DataFrame(
        {"high": [10.0, 11.0, 12.0], "low": [8.0, 9.0, 9.0], "close": [9.0, 10.0, 11.0]}
    )

    atr = average_true_range(bars, period=2)

    assert atr[1] == pytest.approx(2.0)
    assert atr[2] == pytest.approx(2.5)


def test_average_true_range_true_range_widens_around_a_gap() -> None:
    """Un gap de clôture élargit le vrai range au-delà du simple high-low de la barre.

    Barre 1 : high-low = 0.5 seulement, mais la clôture précédente (9.0) est
    loin sous le low de cette barre (10.0) : le vrai range capture ce gap,
    max(0.5, |10.5-9|=1.5, |10-9|=1.0) = 1.5, bien au-delà du simple 0.5.
    """
    bars = pl.DataFrame({"high": [10.0, 10.5], "low": [8.0, 10.0], "close": [9.0, 10.2]})

    atr = average_true_range(bars, period=1)

    assert atr[1] == pytest.approx(1.5)


def test_position_size_fixed_risk_matches_hand_computed_formula() -> None:
    """Quantité = (capital x risque) / distance de stop, exactement."""
    quantity = position_size_fixed_risk(capital=100_000.0, risk_pct=0.01, stop_distance=0.005)

    assert quantity == pytest.approx(200_000.0)  # (100000 * 0.01) / 0.005


def test_position_size_fixed_risk_rejects_risk_pct_out_of_range() -> None:
    """`risk_pct` doit être dans (0, 1]."""
    with pytest.raises(ValueError, match="risk_pct"):
        position_size_fixed_risk(capital=100_000.0, risk_pct=1.5, stop_distance=0.01)


def test_position_size_fixed_risk_rejects_non_positive_stop_distance() -> None:
    """Une distance de stop nulle ou négative rendrait le risque indéfini."""
    with pytest.raises(ValueError, match="stop_distance"):
        position_size_fixed_risk(capital=100_000.0, risk_pct=0.01, stop_distance=0.0)


def test_position_size_fixed_risk_rejects_non_positive_capital() -> None:
    """Un capital nul ou négatif ne peut supporter aucun risque."""
    with pytest.raises(ValueError, match="capital"):
        position_size_fixed_risk(capital=0.0, risk_pct=0.01, stop_distance=0.01)


def test_position_size_scales_inversely_with_volatility() -> None:
    """Critère de propriété connue : plus de risque de prix -> moins d'unités, à risque $ fixe."""
    low_vol_quantity = position_size_fixed_risk(
        capital=100_000.0, risk_pct=0.01, stop_distance=0.001
    )
    high_vol_quantity = position_size_fixed_risk(
        capital=100_000.0, risk_pct=0.01, stop_distance=0.01
    )

    assert high_vol_quantity < low_vol_quantity
