"""Modèles du moteur de backtest (Phase 3) : barres, ordres, journal de trades."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from edgelab.costs.models import CostBreakdown


class OrderSide(enum.StrEnum):
    """Sens d'un ordre. Une sortie hérite du sens opposé à la position qu'elle clôture."""

    BUY = "buy"
    SELL = "sell"


class ExitReason(enum.StrEnum):
    """Raison de sortie d'une position, consignée dans chaque `TradeRecord`."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    SIGNAL = "signal"
    END_OF_DATA = "end_of_data"


class BarView(BaseModel):
    """Une barre OHLCV, telle qu'exposée par `MarketView` (I4)."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OpenPosition:
    """Position ouverte : état mutable suivi par le moteur entre l'entrée et la sortie.

    MAE/MFE sont mis à jour barre par barre par le moteur tant que la
    position est ouverte ; ils ne comptabilisent pas le mouvement de la
    barre d'entrée elle-même (limite documentée, voir `backtest/README.md`).
    """

    instrument_symbol: str
    side: OrderSide
    quantity: float
    entry_timestamp: datetime
    entry_price_theoretical: float
    entry_price_filled: float
    entry_cost: CostBreakdown
    stop_loss_price: float | None
    take_profit_price: float | None
    mae: float = 0.0
    mfe: float = 0.0


class TradeRecord(BaseModel):
    """Une ligne du journal de trades : de quoi auditer un fill après coup, jamais reconstruire."""

    model_config = ConfigDict(frozen=True)

    instrument_symbol: str
    side: OrderSide
    quantity: float
    entry_timestamp: datetime
    entry_price_theoretical: float
    entry_price_filled: float
    entry_cost: CostBreakdown
    exit_timestamp: datetime
    exit_price_theoretical: float
    exit_price_filled: float
    exit_cost: CostBreakdown
    exit_reason: ExitReason
    mae: float
    mfe: float

    @property
    def gross_pnl(self) -> float:
        """PnL avant coûts, au prix rempli."""
        direction = 1.0 if self.side is OrderSide.BUY else -1.0
        return direction * self.quantity * (self.exit_price_filled - self.entry_price_filled)

    @property
    def total_cost(self) -> float:
        """Coût total de l'aller-retour (coût par unité de prix x quantité, entrée + sortie)."""
        return self.quantity * (self.entry_cost.total + self.exit_cost.total)

    @property
    def net_pnl(self) -> float:
        """PnL net de coûts."""
        return self.gross_pnl - self.total_cost


class BacktestResult(BaseModel):
    """Résultat complet d'un backtest : journal de trades, courbes d'equity et d'exposition."""

    model_config = ConfigDict(frozen=True)

    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[float, ...]
    exposure_curve: tuple[float, ...]
    initial_capital: float
    final_equity: float

    @property
    def net_pnl(self) -> float:
        """PnL net de coûts sur l'ensemble du backtest."""
        return self.final_equity - self.initial_capital
