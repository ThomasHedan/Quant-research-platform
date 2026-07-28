"""Tests de edgelab.backtest.models (Phase 3)."""

from datetime import UTC, datetime

import pytest
from edgelab.backtest.models import BacktestResult, ExitReason, OrderSide, TradeRecord
from edgelab.costs.models import CostBreakdown

_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _make_trade(**overrides: object) -> TradeRecord:
    defaults: dict[str, object] = {
        "instrument_symbol": "EURUSD",
        "side": OrderSide.BUY,
        "quantity": 10.0,
        "entry_timestamp": _TS,
        "entry_price_theoretical": 100.0,
        "entry_price_filled": 100.0,
        "entry_cost": CostBreakdown(spread=0.01, commission=0.02, slippage=0.0),
        "exit_timestamp": _TS,
        "exit_price_theoretical": 105.0,
        "exit_price_filled": 105.0,
        "exit_cost": CostBreakdown(spread=0.01, commission=0.02, slippage=0.0),
        "exit_reason": ExitReason.SIGNAL,
        "mae": 0.0,
        "mfe": 5.0,
    }
    defaults.update(overrides)
    return TradeRecord(**defaults)


def test_gross_pnl_is_positive_for_a_winning_long() -> None:
    """Un long qui monte a un PnL brut positif."""
    trade = _make_trade(side=OrderSide.BUY, entry_price_filled=100.0, exit_price_filled=105.0)

    assert trade.gross_pnl == pytest.approx(50.0)  # 10 * (105 - 100)


def test_gross_pnl_is_negative_for_a_losing_short() -> None:
    """Un short qui monte a un PnL brut négatif."""
    trade = _make_trade(side=OrderSide.SELL, entry_price_filled=100.0, exit_price_filled=105.0)

    assert trade.gross_pnl == pytest.approx(-50.0)  # -10 * (105 - 100)


def test_total_cost_sums_entry_and_exit_cost_times_quantity() -> None:
    """Le coût total est le coût par unité de prix (entrée + sortie) multiplié par la quantité."""
    trade = _make_trade(
        quantity=10.0,
        entry_cost=CostBreakdown(spread=0.01, commission=0.02, slippage=0.0),
        exit_cost=CostBreakdown(spread=0.01, commission=0.02, slippage=0.0),
    )

    assert trade.total_cost == pytest.approx(0.6)  # 10 * (0.03 + 0.03)


def test_net_pnl_is_gross_pnl_minus_total_cost() -> None:
    """Le PnL net est simplement le PnL brut diminué du coût total."""
    trade = _make_trade()

    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.total_cost)


def test_backtest_result_net_pnl_is_final_minus_initial_equity() -> None:
    """Le PnL net du backtest est l'écart entre l'équité finale et le capital initial."""
    result = BacktestResult(
        trades=(),
        equity_curve=(100_000.0, 100_500.0),
        exposure_curve=(0.0, 0.0),
        initial_capital=100_000.0,
        final_equity=100_500.0,
    )

    assert result.net_pnl == pytest.approx(500.0)
