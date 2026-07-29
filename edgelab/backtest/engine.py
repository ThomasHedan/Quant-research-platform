"""Moteur de backtest event-driven, barre par barre (Phase 3).

I4 est garanti par construction : la seule vue des barres exposée aux
stratégies est `MarketView`, qui ne peut structurellement pas renvoyer une
barre postérieure à l'index courant du moteur (`market_view.py`).

Séquence par barre `t` (jamais réordonnée) :
1. `market.advance(t)` — la barre `t` devient la barre courante.
2. Mise à jour du MAE/MFE des positions déjà ouvertes, sur le range de `t`.
3. Sorties bracket (stop/take-profit) des positions déjà ouvertes, sur `t`
   — politique déclarée : le stop touche en premier en cas d'ambiguïté.
4. Sorties signal en attente (demandées à une barre antérieure), remplies à
   l'ouverture de `t`.
5. Entrées en attente (demandées à une barre antérieure), remplies selon la
   règle de fill de leur type d'ordre sur `t`.
6. `strategy.on_bar(self)` — la stratégie voit la barre `t` en entier et
   peut soumettre de nouveaux ordres, remplis au plus tôt à la barre `t+1`.

Une seule position ouverte par instrument à la fois, et tous les
instruments partagent le même calendrier de barres (même nombre de barres,
mêmes timestamps) — limites documentées, voir `backtest/README.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from edgelab.backtest.fills import fill_limit_order, fill_market_order, fill_stop_order
from edgelab.backtest.market_view import MarketView
from edgelab.backtest.models import (
    BacktestResult,
    BarView,
    ExitReason,
    OpenPosition,
    OrderSide,
    TradeRecord,
)
from edgelab.backtest.sizing import position_size_fixed_risk
from edgelab.costs.models import OrderType
from edgelab.data.selection import DatasetSelection
from edgelab.universe.instrument import Instrument

_EXIT_ORDER_TYPE_BY_REASON = {
    ExitReason.STOP_LOSS: OrderType.STOP,
    ExitReason.TAKE_PROFIT: OrderType.LIMIT,
    ExitReason.SIGNAL: OrderType.MARKET,
    ExitReason.END_OF_DATA: OrderType.MARKET,
}


class Strategy(Protocol):
    """Une stratégie exécutable : reçoit le moteur à chaque barre et soumet des ordres."""

    def on_bar(self, engine: BacktestEngine) -> None:
        """Appelé une fois par barre, la barre courante déjà visible via `engine.market`."""


@dataclass
class _PendingOrder:
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None
    stop_price: float | None
    stop_loss_price: float | None
    take_profit_price: float | None
    theoretical_price: float


class BacktestEngine:
    """Moteur de backtest multi-instruments à capital partagé."""

    def __init__(
        self,
        selections: Mapping[str, DatasetSelection],
        instruments: Mapping[str, Instrument],
        *,
        initial_capital: float,
    ) -> None:
        """
        `selections` et non des DataFrames nus : c'est ce qui rend I3 et le refus
        des datasets en quarantaine structurels plutôt que disciplinaires. Une
        `DatasetSelection` ne peut pas exister sans avoir passé
        `ensure_backtest_ready`, et sa variante holdout ne peut pas exister sans
        un accès journalisé (voir `edgelab.data.selection`).

        Raises:
            ValueError: si `selections` est vide, si ses clés ne correspondent
                pas exactement à celles de `instruments`, si toutes les
                sélections ne portent pas le même split, si les séries de barres
                n'ont pas toutes la même longueur (calendrier aligné requis),
                ou si `initial_capital` n'est pas positif.
        """
        if not selections:
            raise ValueError("selections must not be empty")
        if set(selections) != set(instruments):
            raise ValueError("selections and instruments must cover the same symbols")
        splits = {selection.split for selection in selections.values()}
        if len(splits) != 1:
            raise ValueError(
                f"all selections must share one split, got {sorted(s.value for s in splits)} — "
                "mixing research and holdout bars in one backtest is never intended"
            )
        bars_by_instrument = {symbol: sel.bars for symbol, sel in selections.items()}
        lengths = {df.height for df in bars_by_instrument.values()}
        if len(lengths) != 1:
            raise ValueError(
                "all instruments must share the same number of bars (aligned timeline)"
            )
        if initial_capital <= 0.0:
            raise ValueError("initial_capital must be positive")

        self._instruments = dict(instruments)
        self._selections = dict(selections)
        self.split = splits.pop()
        self.market = MarketView(bars_by_instrument)
        self.initial_capital = initial_capital
        self._n_bars = lengths.pop()
        self._realized_pnl = 0.0
        self._pending_entries: dict[str, _PendingOrder] = {}
        self._pending_exits: dict[str, float] = {}
        self._open_positions: dict[str, OpenPosition] = {}
        self._trades: list[TradeRecord] = []

    @property
    def dataset_ids(self) -> dict[str, str]:
        """Le `dataset_id` utilisé par instrument — la lignée à écrire au registre (I1)."""
        return {symbol: sel.manifest.dataset_id for symbol, sel in self._selections.items()}

    @property
    def dataset_hashes(self) -> dict[str, str]:
        """Le `manifest_hash` utilisé par instrument, pour le hash de lignée d'un essai (I1)."""
        return {symbol: sel.manifest.manifest_hash for symbol, sel in self._selections.items()}

    # --- API consommée par les stratégies -----------------------------------

    def position(self, instrument_symbol: str) -> OpenPosition | None:
        """La position ouverte sur cet instrument, ou `None`."""
        return self._open_positions.get(instrument_symbol)

    def enter(  # noqa: PLR0913 — paramètres d'ordre, transmis tels quels
        self,
        instrument_symbol: str,
        *,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        quantity: float | None = None,
        risk_pct: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
    ) -> None:
        """Soumet un ordre d'entrée, rempli au plus tôt à la barre suivante.

        Fournir soit `quantity`, soit `risk_pct` avec `stop_loss_price` (la
        quantité est alors dérivée du risque fixe sur le solde courant, voir
        `sizing.py`) — jamais les deux à la fois. Un instrument avec une
        position déjà ouverte ou un ordre déjà en attente ignore
        silencieusement une nouvelle demande d'entrée : une seule position à
        la fois par instrument.

        Raises:
            ValueError: si ni `quantity` ni (`risk_pct` et `stop_loss_price`)
                ne sont fournis, si les deux le sont à la fois, si `quantity`
                n'est pas strictement positif, ou si un ordre limite/stop est
                soumis sans son prix de déclenchement.
        """
        if instrument_symbol in self._open_positions or instrument_symbol in self._pending_entries:
            return
        if (quantity is None) == (risk_pct is None):
            raise ValueError("provide exactly one of quantity or risk_pct")
        if order_type is OrderType.LIMIT and limit_price is None:
            raise ValueError("limit orders require limit_price")
        if order_type is OrderType.STOP and stop_price is None:
            raise ValueError("stop orders require stop_price")

        reference_price = self.market.current_bar(instrument_symbol).close
        if quantity is None:
            if stop_loss_price is None:
                raise ValueError("risk_pct sizing requires stop_loss_price")
            assert risk_pct is not None  # narrowing pour mypy : exclusif avec quantity ci-dessus
            stop_distance = abs(reference_price - stop_loss_price)
            quantity = position_size_fixed_risk(
                capital=self.equity, risk_pct=risk_pct, stop_distance=stop_distance
            )
        elif quantity <= 0.0:
            raise ValueError("quantity must be positive")

        self._pending_entries[instrument_symbol] = _PendingOrder(
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            theoretical_price=reference_price,
        )

    def exit(self, instrument_symbol: str) -> None:
        """Demande la clôture par signal, remplie au plus tôt à la barre suivante.

        Sans effet si aucune position n'est ouverte sur cet instrument.
        """
        if instrument_symbol in self._open_positions:
            self._pending_exits[instrument_symbol] = self.market.current_bar(
                instrument_symbol
            ).close

    @property
    def equity(self) -> float:
        """Capital courant : capital initial + PnL réalisé + PnL latent des positions ouvertes."""
        return self.initial_capital + self._realized_pnl + self._unrealized_pnl()

    @property
    def exposure(self) -> float:
        """Exposition agrégée : somme des valeurs notionnelles absolues des positions ouvertes."""
        total = 0.0
        for symbol, pos in self._open_positions.items():
            current_price = self.market.current_bar(symbol).close
            total += abs(pos.quantity * current_price)
        return total

    # --- boucle principale ----------------------------------------------------

    def run(self, strategy: Strategy) -> BacktestResult:
        """Rejoue la stratégie barre par barre, clôture de force ce qui reste ouvert à la fin."""
        equity_curve: list[float] = []
        exposure_curve: list[float] = []

        for index in range(self._n_bars):
            self.market.advance(index)
            self._update_excursions()
            self._process_bracket_exits()
            self._process_pending_exits()
            self._process_pending_entries()
            strategy.on_bar(self)
            equity_curve.append(self.equity)
            exposure_curve.append(self.exposure)

        self._force_close_all()
        equity_curve[-1] = self.equity
        exposure_curve[-1] = self.exposure

        return BacktestResult(
            trades=tuple(self._trades),
            equity_curve=tuple(equity_curve),
            exposure_curve=tuple(exposure_curve),
            initial_capital=self.initial_capital,
            final_equity=self.equity,
        )

    # --- mécanique interne ----------------------------------------------------

    def _unrealized_pnl(self) -> float:
        total = 0.0
        for symbol, pos in self._open_positions.items():
            direction = 1.0 if pos.side is OrderSide.BUY else -1.0
            current_price = self.market.current_bar(symbol).close
            total += direction * pos.quantity * (current_price - pos.entry_price_filled)
            total -= pos.quantity * pos.entry_cost.total
        return total

    def _update_excursions(self) -> None:
        for symbol, pos in self._open_positions.items():
            bar = self.market.current_bar(symbol)
            if pos.side is OrderSide.BUY:
                adverse = pos.entry_price_filled - bar.low
                favorable = bar.high - pos.entry_price_filled
            else:
                adverse = bar.high - pos.entry_price_filled
                favorable = pos.entry_price_filled - bar.low
            pos.mae = max(pos.mae, adverse, 0.0)
            pos.mfe = max(pos.mfe, favorable, 0.0)

    def _process_bracket_exits(self) -> None:
        to_close: list[tuple[str, float, float, ExitReason]] = []
        for symbol, pos in self._open_positions.items():
            bar = self.market.current_bar(symbol)
            exit_side = OrderSide.SELL if pos.side is OrderSide.BUY else OrderSide.BUY

            stop_loss_price = pos.stop_loss_price
            if stop_loss_price is not None:
                stop_fill = fill_stop_order(bar, side=exit_side, stop_price=stop_loss_price)
                if stop_fill is not None:
                    # Politique déclarée (CLAUDE.md §7) : le stop touche en premier si ambigu.
                    to_close.append((symbol, stop_loss_price, stop_fill, ExitReason.STOP_LOSS))
                    continue

            take_profit_price = pos.take_profit_price
            if take_profit_price is not None:
                tp_fill = fill_limit_order(bar, side=exit_side, limit_price=take_profit_price)
                if tp_fill is not None:
                    to_close.append((symbol, take_profit_price, tp_fill, ExitReason.TAKE_PROFIT))

        for symbol, theoretical, filled, reason in to_close:
            self._close_position(
                symbol, theoretical_price=theoretical, filled_price=filled, reason=reason
            )

    def _process_pending_exits(self) -> None:
        for symbol, theoretical_price in list(self._pending_exits.items()):
            del self._pending_exits[symbol]
            if symbol not in self._open_positions:
                continue  # déjà clôturée par un bracket cette même barre
            bar = self.market.current_bar(symbol)
            filled_price = fill_market_order(bar)
            self._close_position(
                symbol,
                theoretical_price=theoretical_price,
                filled_price=filled_price,
                reason=ExitReason.SIGNAL,
            )

    def _process_pending_entries(self) -> None:
        filled_symbols = []
        for symbol, pending in self._pending_entries.items():
            bar = self.market.current_bar(symbol)
            fill_price = self._resolve_entry_fill(bar, pending)
            if fill_price is None:
                continue  # limite/stop pas encore touché, reste en attente
            cost = self._instruments[symbol].cost_model.entry_cost(
                order_type=pending.order_type, timestamp=bar.timestamp
            )
            self._open_positions[symbol] = OpenPosition(
                instrument_symbol=symbol,
                side=pending.side,
                quantity=pending.quantity,
                entry_timestamp=bar.timestamp,
                entry_price_theoretical=pending.theoretical_price,
                entry_price_filled=fill_price,
                entry_cost=cost,
                stop_loss_price=pending.stop_loss_price,
                take_profit_price=pending.take_profit_price,
            )
            filled_symbols.append(symbol)
        for symbol in filled_symbols:
            del self._pending_entries[symbol]

    def _resolve_entry_fill(self, bar: BarView, pending: _PendingOrder) -> float | None:
        if pending.order_type is OrderType.MARKET:
            return fill_market_order(bar)
        if pending.order_type is OrderType.LIMIT:
            assert pending.limit_price is not None  # validé à la soumission (`enter`)
            return fill_limit_order(bar, side=pending.side, limit_price=pending.limit_price)
        assert pending.stop_price is not None  # validé à la soumission (`enter`)
        return fill_stop_order(bar, side=pending.side, stop_price=pending.stop_price)

    def _force_close_all(self) -> None:
        for symbol in list(self._open_positions):
            bar = self.market.current_bar(symbol)
            self._close_position(
                symbol,
                theoretical_price=bar.close,
                filled_price=bar.close,
                reason=ExitReason.END_OF_DATA,
            )

    def _close_position(
        self, symbol: str, *, theoretical_price: float, filled_price: float, reason: ExitReason
    ) -> None:
        pos = self._open_positions.pop(symbol)
        bar = self.market.current_bar(symbol)
        cost = self._instruments[symbol].cost_model.entry_cost(
            order_type=_EXIT_ORDER_TYPE_BY_REASON[reason], timestamp=bar.timestamp
        )
        trade = TradeRecord(
            instrument_symbol=symbol,
            side=pos.side,
            quantity=pos.quantity,
            entry_timestamp=pos.entry_timestamp,
            entry_price_theoretical=pos.entry_price_theoretical,
            entry_price_filled=pos.entry_price_filled,
            entry_cost=pos.entry_cost,
            exit_timestamp=bar.timestamp,
            exit_price_theoretical=theoretical_price,
            exit_price_filled=filled_price,
            exit_cost=cost,
            exit_reason=reason,
            mae=pos.mae,
            mfe=pos.mfe,
        )
        self._trades.append(trade)
        self._realized_pnl += trade.net_pnl
