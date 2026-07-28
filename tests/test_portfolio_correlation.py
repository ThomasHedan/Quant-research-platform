"""Tests de edgelab.portfolio.correlation (Phase 6)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.portfolio.correlation import (
    aggregate_to_daily_returns,
    correlation_matrix_by_day,
    correlation_matrix_by_trade,
)


def test_correlation_matrix_by_trade_rejects_fewer_than_two_strategies() -> None:
    """Une corrélation n'a pas de sens avec une seule stratégie."""
    with pytest.raises(ValueError, match="2 strategies"):
        correlation_matrix_by_trade({"a": np.zeros(10)})


def test_correlation_matrix_by_trade_rejects_mismatched_lengths() -> None:
    """Toutes les stratégies doivent couvrir la même période."""
    with pytest.raises(ValueError, match="same length"):
        correlation_matrix_by_trade({"a": np.zeros(10), "b": np.zeros(20)})


def test_correlation_matrix_by_trade_is_close_to_one_for_identical_series(
    positive_edge_trades: np.ndarray,
) -> None:
    """Critère de propriété connue : deux séries identiques sont parfaitement corrélées."""
    matrix = correlation_matrix_by_trade({"a": positive_edge_trades, "b": positive_edge_trades})

    assert matrix.correlation("a", "b") == pytest.approx(1.0, abs=1e-9)


def test_correlation_matrix_by_trade_is_near_zero_for_independent_series(
    make_edge_trades: Callable[[int], np.ndarray],
) -> None:
    """Critère de propriété connue : deux mélanges indépendants du même edge sont décorrélés."""
    matrix = correlation_matrix_by_trade({"a": make_edge_trades(1), "b": make_edge_trades(2)})

    assert abs(matrix.correlation("a", "b")) < 0.2


def test_aggregate_to_daily_returns_rejects_non_positive_trades_per_day() -> None:
    """`trades_per_day` doit être strictement positif pour former des jours."""
    with pytest.raises(ValueError, match="trades_per_day"):
        aggregate_to_daily_returns(np.zeros(10), trades_per_day=0)


def test_aggregate_to_daily_returns_sums_consecutive_blocks() -> None:
    """Chaque jour est la somme de `trades_per_day` trades consécutifs."""
    returns = np.array([1.0, 2.0, 3.0, 4.0])

    daily = aggregate_to_daily_returns(returns, trades_per_day=2)

    assert daily.tolist() == [3.0, 7.0]


def test_aggregate_to_daily_returns_truncates_incomplete_trailing_day() -> None:
    """Un reliquat de trades qui ne forme pas un jour complet est tronqué, pas agrégé à part."""
    returns = np.array([1.0, 2.0, 3.0])

    daily = aggregate_to_daily_returns(returns, trades_per_day=2)

    assert daily.tolist() == [3.0]


def test_correlation_matrix_by_day_aggregates_before_correlating(
    positive_edge_trades: np.ndarray,
) -> None:
    """La corrélation par jour opère sur les rendements agrégés, pas sur les trades bruts."""
    matrix = correlation_matrix_by_day(
        {"a": positive_edge_trades, "b": positive_edge_trades}, trades_per_day=5
    )

    assert matrix.correlation("a", "b") == pytest.approx(1.0, abs=1e-9)
