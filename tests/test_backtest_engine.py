"""Tests de edgelab.backtest.engine (Phase 3, I4)."""

from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest
from edgelab.backtest.engine import BacktestEngine
from edgelab.backtest.market_view import LookAheadError
from edgelab.backtest.models import ExitReason, OrderSide
from edgelab.costs.models import CostModel, FixedSpreadCost, OrderType, SlippageByOrderType
from edgelab.data.selection import DatasetSelection, DataSplit
from edgelab.universe import Instrument


class BuyAndHold:
    """Déploie tout le capital en un seul achat marché à la première barre, puis ne fait rien."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._done = False

    def on_bar(self, engine: BacktestEngine) -> None:
        if not self._done:
            quantity = engine.equity / engine.market.current_bar(self.symbol).close
            engine.enter(self.symbol, side=OrderSide.BUY, quantity=quantity)
            self._done = True


class AlwaysFlip:
    """Ouvre une position marché de taille fixe dès que possible, la clôture par signal aussitôt."""

    def __init__(self, symbol: str, quantity: float) -> None:
        self.symbol = symbol
        self.quantity = quantity

    def on_bar(self, engine: BacktestEngine) -> None:
        if engine.position(self.symbol) is None:
            engine.enter(self.symbol, side=OrderSide.BUY, quantity=self.quantity)
        else:
            engine.exit(self.symbol)


class CheatingStrategy:
    """Stratégie malveillante : tente de lire une barre future (I4)."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def on_bar(self, engine: BacktestEngine) -> None:
        engine.market.bar_at(self.symbol, offset=1)


class EnterOnceWithBracket:
    """Ouvre une position à la première barre avec stop-loss et take-profit attachés."""

    def __init__(
        self,
        symbol: str,
        *,
        stop_loss_price: float,
        take_profit_price: float,
        quantity: float = 100.0,
    ) -> None:
        self.symbol = symbol
        self.stop_loss_price = stop_loss_price
        self.take_profit_price = take_profit_price
        self.quantity = quantity
        self._done = False

    def on_bar(self, engine: BacktestEngine) -> None:
        if not self._done:
            engine.enter(
                self.symbol,
                side=OrderSide.BUY,
                quantity=self.quantity,
                stop_loss_price=self.stop_loss_price,
                take_profit_price=self.take_profit_price,
            )
            self._done = True


class DoNothing:
    """Ne soumet jamais d'ordre."""

    def on_bar(self, engine: BacktestEngine) -> None:
        return


@pytest.fixture
def zero_commission_instrument(
    make_research_instrument: Callable[..., Instrument],
) -> Instrument:
    """Un instrument à coûts nuls, pour isoler la mécanique de fill du coût."""
    return make_research_instrument("EURUSD")


@pytest.fixture
def commission_cost_model() -> CostModel:
    """Un coût déterministe (0,02 par fill, ni spread ni slippage) pour vérifier au centime."""
    return FixedSpreadCost(spread=0.0, commission=0.02, slippage=SlippageByOrderType())


@pytest.fixture
def commission_instrument(
    make_research_instrument: Callable[..., Instrument], commission_cost_model: CostModel
) -> Instrument:
    return make_research_instrument("EURUSD", commission_cost_model)


# --- Constructeur -----------------------------------------------------------


def test_engine_rejects_empty_bars(zero_commission_instrument: Instrument) -> None:
    """Un backtest sans aucune sélection n'a rien à rejouer."""
    with pytest.raises(ValueError, match="selections must not be empty"):
        BacktestEngine({}, {}, initial_capital=100_000.0)


def test_engine_rejects_symbol_mismatch(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Les instruments fournis doivent couvrir exactement les mêmes symboles que les barres."""
    with pytest.raises(ValueError, match="same symbols"):
        BacktestEngine(
            {"EURUSD": make_selection([100.0, 101.0])},
            {"GBPUSD": zero_commission_instrument},
            initial_capital=100_000.0,
        )


def test_engine_rejects_misaligned_bar_counts(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Tous les instruments doivent partager le même calendrier de barres (même longueur)."""
    with pytest.raises(ValueError, match="aligned timeline"):
        BacktestEngine(
            {
                "EURUSD": make_selection([100.0, 101.0, 102.0]),
                "GBPUSD": make_selection([100.0, 101.0]),
            },
            {"EURUSD": zero_commission_instrument, "GBPUSD": zero_commission_instrument},
            initial_capital=100_000.0,
        )


def test_engine_rejects_non_positive_initial_capital(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Un capital initial nul ou négatif n'a pas de sens."""
    with pytest.raises(ValueError, match="initial_capital"):
        BacktestEngine(
            {"EURUSD": make_selection([100.0])},
            {"EURUSD": zero_commission_instrument},
            initial_capital=0.0,
        )


def test_engine_rejects_mixed_splits(
    zero_commission_instrument: Instrument,
    make_selection: Callable[..., DatasetSelection],
) -> None:
    """Mélanger research et holdout dans un même backtest n'est jamais une intention réelle."""
    with pytest.raises(ValueError, match="must share one split"):
        BacktestEngine(
            {
                "EURUSD": make_selection([100.0, 101.0], split=DataSplit.RESEARCH),
                "GBPUSD": make_selection(
                    [100.0, 101.0], split=DataSplit.HOLDOUT, instrument_symbol="GBPUSD"
                ),
            },
            {"EURUSD": zero_commission_instrument, "GBPUSD": zero_commission_instrument},
            initial_capital=100_000.0,
        )


# --- enter() / exit() : validation et garde-fous -----------------------------


def test_enter_rejects_neither_quantity_nor_risk_pct(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Il faut fournir un mode de dimensionnement, l'un ou l'autre."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    with pytest.raises(ValueError, match="exactly one"):
        engine.enter("EURUSD", side=OrderSide.BUY)


def test_enter_rejects_both_quantity_and_risk_pct(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Fournir les deux modes de dimensionnement à la fois est ambigu."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    with pytest.raises(ValueError, match="exactly one"):
        engine.enter("EURUSD", side=OrderSide.BUY, quantity=10.0, risk_pct=0.01)


def test_enter_risk_pct_requires_stop_loss_price(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Le dimensionnement par risque a besoin d'une distance de stop pour se calculer."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    with pytest.raises(ValueError, match="stop_loss_price"):
        engine.enter("EURUSD", side=OrderSide.BUY, risk_pct=0.01)


def test_enter_rejects_non_positive_quantity(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Une quantité nulle ou négative n'a pas de sens."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    with pytest.raises(ValueError, match="quantity"):
        engine.enter("EURUSD", side=OrderSide.BUY, quantity=0.0)


def test_enter_limit_order_requires_limit_price(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Un ordre limite sans prix limite ne peut pas se remplir."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    with pytest.raises(ValueError, match="limit_price"):
        engine.enter("EURUSD", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10.0)


def test_enter_stop_order_requires_stop_price(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Un ordre stop sans prix de déclenchement ne peut pas se remplir."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    with pytest.raises(ValueError, match="stop_price"):
        engine.enter("EURUSD", side=OrderSide.BUY, order_type=OrderType.STOP, quantity=10.0)


def test_enter_is_a_no_op_when_a_position_is_already_open(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Une seule position à la fois par instrument : une seconde demande d'entrée est ignorée."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 100.0, 100.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.run(BuyAndHold("EURUSD"))
    # BuyAndHold n'entre qu'une fois par construction ; ce test vérifie l'appel direct idempotent
    engine2 = BacktestEngine(
        {"EURUSD": make_selection([100.0, 100.0, 100.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine2.market.advance(0)
    engine2.enter("EURUSD", side=OrderSide.BUY, quantity=10.0)
    engine2.enter("EURUSD", side=OrderSide.BUY, quantity=999.0)  # doit être ignoré
    engine2.market.advance(1)
    engine2._process_pending_entries()

    assert engine2.position("EURUSD") is not None
    assert engine2.position("EURUSD").quantity == 10.0  # type: ignore[union-attr]


def test_exit_is_a_no_op_without_an_open_position(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Demander la clôture d'un instrument sans position ouverte ne fait rien."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    engine.exit("EURUSD")  # ne doit pas lever

    assert engine.position("EURUSD") is None


def test_enter_with_risk_pct_derives_quantity_from_stop_distance(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Le dimensionnement par risque dérive la quantité de la distance au stop."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 100.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    engine.market.advance(0)

    engine.enter("EURUSD", side=OrderSide.BUY, risk_pct=0.01, stop_loss_price=99.0)
    engine.market.advance(1)
    engine._process_pending_entries()

    position = engine.position("EURUSD")
    assert position is not None
    expected_quantity = (100_000.0 * 0.01) / 1.0  # stop_distance = |100 - 99|
    assert position.quantity == pytest.approx(expected_quantity)


def test_limit_entry_stays_pending_until_touched(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Un ordre limite qui n'est jamais touché reste en attente, sans jamais se remplir."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # décision
        (
            datetime(2024, 1, 1, 1, tzinfo=UTC),
            100.0,
            101.0,
            99.0,
            100.0,
            100.0,
        ),  # limite (95) pas touchée
        (datetime(2024, 1, 1, 2, tzinfo=UTC), 100.0, 100.0, 94.0, 96.0, 100.0),  # limite touchée
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )

    class LimitBuyer:
        def __init__(self) -> None:
            self._done = False

        def on_bar(self, engine: BacktestEngine) -> None:
            if not self._done:
                engine.enter(
                    "EURUSD",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=10.0,
                    limit_price=95.0,
                )
                self._done = True

    engine = BacktestEngine(
        {"EURUSD": wrap_selection(bars)},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    result = engine.run(LimitBuyer())

    assert len(result.trades) == 1
    assert result.trades[0].entry_price_filled == 95.0


def test_stop_entry_order_fills_when_triggered(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Un ordre stop d'entrée se remplit dès que le range de la barre atteint son niveau."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # décision
        (
            datetime(2024, 1, 1, 1, tzinfo=UTC),
            100.0,
            101.0,
            99.0,
            100.0,
            100.0,
        ),  # stop (105) pas touché
        (datetime(2024, 1, 1, 2, tzinfo=UTC), 100.0, 106.0, 100.0, 105.0, 100.0),  # stop touché
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )

    class StopBuyer:
        def __init__(self) -> None:
            self._done = False

        def on_bar(self, engine: BacktestEngine) -> None:
            if not self._done:
                engine.enter(
                    "EURUSD",
                    side=OrderSide.BUY,
                    order_type=OrderType.STOP,
                    quantity=10.0,
                    stop_price=105.0,
                )
                self._done = True

    engine = BacktestEngine(
        {"EURUSD": wrap_selection(bars)},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    result = engine.run(StopBuyer())

    assert len(result.trades) == 1
    assert result.trades[0].entry_price_filled == 105.0


# --- Critère d'acceptation Phase 3 : I4 --------------------------------------


def test_a_cheating_strategy_that_reads_a_future_bar_raises_look_ahead_error(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Critère d'acceptation (I4) : le moteur propage l'erreur d'une stratégie qui triche."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0, 102.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )

    with pytest.raises(LookAheadError):
        engine.run(CheatingStrategy("EURUSD"))


# --- Critère d'acceptation Phase 3 : buy and hold ----------------------------


def test_buy_and_hold_reproduces_instrument_return_minus_costs_to_the_cent(
    commission_instrument: Instrument,
    commission_cost_model: CostModel,
    make_selection: Callable[..., DatasetSelection],
) -> None:
    """Critère d'acceptation Phase 3 : buy-and-hold == rendement de l'instrument moins les coûts.

    Le calcul attendu est indépendant du moteur : il lit directement les
    barres de test et le modèle de coût, exactement comme un humain
    vérifierait le résultat à la main.
    """
    rng = np.random.default_rng(1)
    closes = [100.0]
    for r in rng.normal(0.0002, 0.001, 60):
        closes.append(closes[-1] * (1 + r))
    selection = make_selection(closes)
    bars = selection.bars
    capital = 100_000.0

    engine = BacktestEngine(
        {"EURUSD": selection}, {"EURUSD": commission_instrument}, initial_capital=capital
    )
    result = engine.run(BuyAndHold("EURUSD"))

    entry_price = bars["close"][0]  # == bars["open"][1], la barre de fill (série continue)
    exit_price = bars["close"][-1]
    quantity = capital / entry_price
    per_fill_cost = commission_cost_model.entry_cost(
        order_type=OrderType.MARKET, timestamp=bars["timestamp"][0]
    ).total
    expected_final_equity = quantity * exit_price - quantity * (2 * per_fill_cost)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason is ExitReason.END_OF_DATA
    assert result.final_equity == pytest.approx(expected_final_equity, abs=0.01)


# --- Critère d'acceptation Phase 3 : espérance nulle -------------------------


def test_zero_edge_strategy_produces_a_net_pnl_exactly_equal_to_cumulative_costs(
    commission_instrument: Instrument,
    make_selection: Callable[..., DatasetSelection],
) -> None:
    """Critère d'acceptation Phase 3 : PnL net strictement négatif, égal aux coûts cumulés.

    Un prix strictement plat rend le PnL brut de chaque aller-retour nul par
    construction : la seule dégradation possible est le coût.
    """
    flat_bars = make_selection([100.0] * 30)
    engine = BacktestEngine(
        {"FLAT": flat_bars},
        {"FLAT": commission_instrument},
        initial_capital=100_000.0,
    )

    result = engine.run(AlwaysFlip("FLAT", 1_000.0))

    assert len(result.trades) > 0
    assert all(trade.gross_pnl == 0.0 for trade in result.trades)
    total_costs = sum(trade.total_cost for trade in result.trades)
    assert total_costs > 0.0
    assert result.net_pnl == pytest.approx(-total_costs, abs=1e-9)
    assert result.net_pnl < 0.0


# --- Politique de barre ambiguë ----------------------------------------------


def test_ambiguous_bar_resolves_to_stop_loss_first(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Politique déclarée (CLAUDE.md §7) : si le stop et le take-profit sont tous deux touchés,
    le stop l'emporte — jamais un choix implicite favorable au trade."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # décision
        (datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # fill d'entrée
        (
            datetime(2024, 1, 1, 2, tzinfo=UTC),
            100.0,
            106.0,
            94.0,
            100.0,
            100.0,
        ),  # stop(95) et tp(105)
        (datetime(2024, 1, 1, 3, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )
    engine = BacktestEngine(
        {"AMB": wrap_selection(bars)},
        {"AMB": zero_commission_instrument},
        initial_capital=100_000.0,
    )

    result = engine.run(EnterOnceWithBracket("AMB", stop_loss_price=95.0, take_profit_price=105.0))

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason is ExitReason.STOP_LOSS
    assert result.trades[0].exit_price_filled == 95.0


def test_take_profit_alone_closes_the_position(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Sans ambiguïté, un take-profit seul touché clôture bien la position en take-profit."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),
        (datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),
        (
            datetime(2024, 1, 1, 2, tzinfo=UTC),
            100.0,
            106.0,
            100.0,
            100.0,
            100.0,
        ),  # tp(105) touché seul
        (datetime(2024, 1, 1, 3, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )
    engine = BacktestEngine(
        {"TP": wrap_selection(bars)}, {"TP": zero_commission_instrument}, initial_capital=100_000.0
    )

    result = engine.run(EnterOnceWithBracket("TP", stop_loss_price=95.0, take_profit_price=105.0))

    assert result.trades[0].exit_reason is ExitReason.TAKE_PROFIT
    assert result.trades[0].exit_price_filled == 105.0


def test_a_quiet_bar_between_entry_and_trigger_leaves_the_bracket_open(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Une barre qui ne touche ni le stop ni le take-profit laisse la position ouverte."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # décision
        (datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # fill d'entrée
        (datetime(2024, 1, 1, 2, tzinfo=UTC), 100.0, 101.0, 99.0, 100.0, 100.0),  # calme
        (datetime(2024, 1, 1, 3, tzinfo=UTC), 100.0, 106.0, 100.0, 105.0, 100.0),  # tp(105) touché
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )
    engine = BacktestEngine(
        {"QUIET": wrap_selection(bars)},
        {"QUIET": zero_commission_instrument},
        initial_capital=100_000.0,
    )

    result = engine.run(
        EnterOnceWithBracket("QUIET", stop_loss_price=95.0, take_profit_price=105.0)
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason is ExitReason.TAKE_PROFIT


def test_bracket_exit_takes_precedence_over_a_pending_signal_exit(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Un stop déclenché la même barre l'emporte sur une sortie signal demandée plus tôt."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # décision d'entrée
        (datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # fill d'entrée
        (
            datetime(2024, 1, 1, 2, tzinfo=UTC),
            100.0,
            100.0,
            100.0,
            100.0,
            100.0,
        ),  # demande de sortie signal
        (datetime(2024, 1, 1, 3, tzinfo=UTC), 100.0, 100.0, 90.0, 92.0, 100.0),  # stop(95) touché
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )

    class EnterThenSignalExitOnBar2(EnterOnceWithBracket):
        def on_bar(self, engine: BacktestEngine) -> None:
            super().on_bar(engine)
            if engine.market.current_index == 2 and engine.position(self.symbol) is not None:
                engine.exit(self.symbol)

    engine = BacktestEngine(
        {"PRIO": wrap_selection(bars)},
        {"PRIO": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    result = engine.run(
        EnterThenSignalExitOnBar2("PRIO", stop_loss_price=95.0, take_profit_price=200.0)
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason is ExitReason.STOP_LOSS


# --- MAE / MFE ----------------------------------------------------------------


def test_mae_and_mfe_track_the_worst_and_best_excursion_after_entry(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """MAE/MFE capturent la pire perte latente et le meilleur gain latent, barre par barre.

    Entrée à 100 (barre 1). Barre 2 descend à 97 (MAE = 3) et monte à 101
    (MFE = 1) ; barre 3 descend encore à 96 (MAE = 4) mais ne dépasse pas le
    haut précédent. Sortie par signal à la barre 4.
    """
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),
        (datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # fill à 100
        (datetime(2024, 1, 1, 2, tzinfo=UTC), 100.0, 101.0, 97.0, 99.0, 100.0),
        (datetime(2024, 1, 1, 3, tzinfo=UTC), 99.0, 100.0, 96.0, 98.0, 100.0),
        (datetime(2024, 1, 1, 4, tzinfo=UTC), 98.0, 98.0, 98.0, 98.0, 100.0),
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )

    class EnterThenExitOnBar3(BuyAndHold):
        def on_bar(self, engine: BacktestEngine) -> None:
            super().on_bar(engine)
            if engine.market.current_index == 3 and engine.position(self.symbol) is not None:
                engine.exit(self.symbol)

    engine = BacktestEngine(
        {"MAE": wrap_selection(bars)},
        {"MAE": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    result = engine.run(EnterThenExitOnBar3("MAE"))

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.mae == pytest.approx(4.0)
    assert trade.mfe == pytest.approx(1.0)


def test_mae_and_mfe_are_mirrored_for_a_short_position(
    zero_commission_instrument: Instrument,
    wrap_selection: Callable[..., DatasetSelection],
) -> None:
    """Pour un short, l'excursion défavorable est une hausse du prix, la favorable une baisse."""
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),
        (datetime(2024, 1, 1, 1, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0, 100.0),  # fill à 100
        (datetime(2024, 1, 1, 2, tzinfo=UTC), 100.0, 103.0, 99.0, 101.0, 100.0),
        (datetime(2024, 1, 1, 3, tzinfo=UTC), 101.0, 101.0, 95.0, 96.0, 100.0),
    ]
    bars = pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )

    class EnterShortThenExitOnBar3:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            self._done = False

        def on_bar(self, engine: BacktestEngine) -> None:
            if not self._done:
                engine.enter(self.symbol, side=OrderSide.SELL, quantity=10.0)
                self._done = True
            elif engine.market.current_index == 3 and engine.position(self.symbol) is not None:
                engine.exit(self.symbol)

    engine = BacktestEngine(
        {"SHORT": wrap_selection(bars)},
        {"SHORT": zero_commission_instrument},
        initial_capital=100_000.0,
    )
    result = engine.run(EnterShortThenExitOnBar3("SHORT"))

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.mae == pytest.approx(3.0)  # high(103) - entry(100)
    assert trade.mfe == pytest.approx(5.0)  # entry(100) - low(95)


# --- Multi-instruments, capital partagé, exposition --------------------------


def test_multi_instrument_backtest_shares_a_single_capital_pool(
    zero_commission_instrument: Instrument,
    make_selection: Callable[..., DatasetSelection],
) -> None:
    """Deux instruments simultanés puisent dans le même capital, sans compartimentage."""
    bars_a = make_selection([100.0] * 10)
    bars_b = make_selection([50.0] * 10, instrument_symbol="B")
    instrument_b = Instrument(
        symbol="B",
        name="B",
        asset_class=zero_commission_instrument.asset_class,
        session_calendar=zero_commission_instrument.session_calendar,
        cost_model=zero_commission_instrument.cost_model,
        price_decimals=5,
        pip_size=0.0001,
    )

    class EnterBoth:
        def __init__(self) -> None:
            self._done = False

        def on_bar(self, engine: BacktestEngine) -> None:
            if not self._done:
                engine.enter("A", side=OrderSide.BUY, quantity=100.0)
                engine.enter("B", side=OrderSide.BUY, quantity=200.0)
                self._done = True

    engine = BacktestEngine(
        {"A": bars_a, "B": bars_b},
        {"A": zero_commission_instrument, "B": instrument_b},
        initial_capital=100_000.0,
    )
    result = engine.run(EnterBoth())

    assert {t.instrument_symbol for t in result.trades} == {"A", "B"}


def test_exposure_reflects_both_open_positions_notional_value(
    zero_commission_instrument: Instrument,
    make_selection: Callable[..., DatasetSelection],
) -> None:
    """L'exposition agrégée est la somme des valeurs notionnelles des positions ouvertes."""
    bars_a = make_selection([100.0] * 5)
    bars_b = make_selection([50.0] * 5, instrument_symbol="B")
    instrument_b = Instrument(
        symbol="B",
        name="B",
        asset_class=zero_commission_instrument.asset_class,
        session_calendar=zero_commission_instrument.session_calendar,
        cost_model=zero_commission_instrument.cost_model,
        price_decimals=5,
        pip_size=0.0001,
    )

    class EnterBothThenHold:
        def __init__(self) -> None:
            self._done = False

        def on_bar(self, engine: BacktestEngine) -> None:
            if not self._done:
                engine.enter("A", side=OrderSide.BUY, quantity=100.0)
                engine.enter("B", side=OrderSide.BUY, quantity=200.0)
                self._done = True

    engine = BacktestEngine(
        {"A": bars_a, "B": bars_b},
        {"A": zero_commission_instrument, "B": instrument_b},
        initial_capital=100_000.0,
    )
    result = engine.run(EnterBothThenHold())

    # Après le fill, avant la clôture forcée : exposition = 100*100 + 200*50 = 20000
    mid_exposure = max(result.exposure_curve[:-1])
    assert mid_exposure == pytest.approx(20_000.0)


# --- equity / position() -----------------------------------------------------


def test_position_returns_none_before_any_entry(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """Sans ordre soumis, aucune position n'est ouverte."""
    engine = BacktestEngine(
        {"EURUSD": make_selection([100.0, 101.0])},
        {"EURUSD": zero_commission_instrument},
        initial_capital=100_000.0,
    )

    engine.run(DoNothing())

    assert engine.position("EURUSD") is None


def test_equity_curve_has_one_point_per_bar(
    zero_commission_instrument: Instrument, make_selection: Callable[..., DatasetSelection]
) -> None:
    """La courbe d'équité a exactement une valeur par barre traitée."""
    selection = make_selection([100.0, 101.0, 102.0, 103.0])
    engine = BacktestEngine(
        {"EURUSD": selection}, {"EURUSD": zero_commission_instrument}, initial_capital=100_000.0
    )

    result = engine.run(DoNothing())

    assert len(result.equity_curve) == selection.n_bars
