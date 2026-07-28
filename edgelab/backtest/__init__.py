"""Moteur event-driven barre par barre, garantissant l'absence de
look-ahead par construction (I4)."""

from edgelab.backtest.engine import BacktestEngine, Strategy
from edgelab.backtest.fills import fill_limit_order, fill_market_order, fill_stop_order
from edgelab.backtest.market_view import LookAheadError, MarketView
from edgelab.backtest.models import (
    BacktestResult,
    BarView,
    ExitReason,
    OpenPosition,
    OrderSide,
    TradeRecord,
)
from edgelab.backtest.sizing import average_true_range, position_size_fixed_risk

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BarView",
    "ExitReason",
    "LookAheadError",
    "MarketView",
    "OpenPosition",
    "OrderSide",
    "Strategy",
    "TradeRecord",
    "average_true_range",
    "fill_limit_order",
    "fill_market_order",
    "fill_stop_order",
    "position_size_fixed_risk",
]
