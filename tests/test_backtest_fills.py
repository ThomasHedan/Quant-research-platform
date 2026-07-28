"""Tests de edgelab.backtest.fills (Phase 3)."""

from datetime import UTC, datetime

from edgelab.backtest.fills import fill_limit_order, fill_market_order, fill_stop_order
from edgelab.backtest.models import BarView, OrderSide

_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(*, open_: float, high: float, low: float, close: float) -> BarView:
    return BarView(timestamp=_TS, open=open_, high=high, low=low, close=close, volume=100.0)


def test_fill_market_order_fills_at_the_open() -> None:
    """Un ordre marché se remplit à l'ouverture de la barre, jamais à sa clôture."""
    bar = _bar(open_=100.0, high=101.0, low=99.0, close=100.5)

    assert fill_market_order(bar) == 100.0


def test_fill_limit_order_buy_fills_at_limit_when_touched() -> None:
    """Un limit d'achat se remplit à son niveau quand le range de la barre le touche."""
    bar = _bar(open_=101.0, high=101.5, low=99.0, close=100.5)

    assert fill_limit_order(bar, side=OrderSide.BUY, limit_price=100.0) == 100.0


def test_fill_limit_order_buy_fills_at_open_when_gapped_through() -> None:
    """Un limit d'achat qui ouvre déjà sous son niveau se remplit à l'ouverture (prix meilleur)."""
    bar = _bar(open_=98.0, high=99.0, low=97.0, close=98.5)

    assert fill_limit_order(bar, side=OrderSide.BUY, limit_price=100.0) == 98.0


def test_fill_limit_order_buy_returns_none_when_never_touched() -> None:
    """Un limit d'achat dont le range ne descend jamais au niveau reste en attente."""
    bar = _bar(open_=105.0, high=106.0, low=104.0, close=105.5)

    assert fill_limit_order(bar, side=OrderSide.BUY, limit_price=100.0) is None


def test_fill_limit_order_sell_fills_at_limit_when_touched() -> None:
    """Un limit de vente (take-profit d'un long) se remplit à son niveau quand touché."""
    bar = _bar(open_=99.0, high=100.5, low=98.5, close=99.5)

    assert fill_limit_order(bar, side=OrderSide.SELL, limit_price=100.0) == 100.0


def test_fill_limit_order_sell_fills_at_open_when_gapped_through() -> None:
    """Un limit de vente qui ouvre déjà au-dessus de son niveau se remplit à l'ouverture."""
    bar = _bar(open_=102.0, high=103.0, low=101.5, close=102.5)

    assert fill_limit_order(bar, side=OrderSide.SELL, limit_price=100.0) == 102.0


def test_fill_limit_order_sell_returns_none_when_never_touched() -> None:
    """Un limit de vente dont le range ne monte jamais au niveau reste en attente."""
    bar = _bar(open_=95.0, high=96.0, low=94.0, close=95.5)

    assert fill_limit_order(bar, side=OrderSide.SELL, limit_price=100.0) is None


def test_fill_stop_order_buy_fills_at_stop_when_touched() -> None:
    """Un stop d'achat (breakout) se remplit à son niveau quand le range le franchit."""
    bar = _bar(open_=99.0, high=100.5, low=98.5, close=99.5)

    assert fill_stop_order(bar, side=OrderSide.BUY, stop_price=100.0) == 100.0


def test_fill_stop_order_buy_fills_at_open_when_gapped_through() -> None:
    """Un stop d'achat qui ouvre déjà au-dessus de son niveau se remplit à l'ouverture (gap)."""
    bar = _bar(open_=102.0, high=103.0, low=101.5, close=102.5)

    assert fill_stop_order(bar, side=OrderSide.BUY, stop_price=100.0) == 102.0


def test_fill_stop_order_buy_returns_none_when_never_touched() -> None:
    """Un stop d'achat dont le range ne monte jamais au niveau reste en attente."""
    bar = _bar(open_=95.0, high=96.0, low=94.0, close=95.5)

    assert fill_stop_order(bar, side=OrderSide.BUY, stop_price=100.0) is None


def test_fill_stop_order_sell_fills_at_stop_when_touched() -> None:
    """Un stop de vente (protection d'un long) se remplit à son niveau quand touché."""
    bar = _bar(open_=101.0, high=101.5, low=99.5, close=100.5)

    assert fill_stop_order(bar, side=OrderSide.SELL, stop_price=100.0) == 100.0


def test_fill_stop_order_sell_fills_at_open_when_gapped_through() -> None:
    """Un stop de vente qui ouvre déjà sous son niveau se remplit à l'ouverture (pire prix)."""
    bar = _bar(open_=98.0, high=99.0, low=97.0, close=98.5)

    assert fill_stop_order(bar, side=OrderSide.SELL, stop_price=100.0) == 98.0


def test_stop_order_never_fills_better_than_a_limit_order_on_the_same_gap() -> None:
    """Un stop ne se remplit jamais mieux qu'un ordre limite sur le même gap, à niveau égal."""
    bar = _bar(open_=102.0, high=103.0, low=101.5, close=102.5)

    stop_fill = fill_stop_order(bar, side=OrderSide.BUY, stop_price=100.0)
    limit_fill = fill_limit_order(bar, side=OrderSide.SELL, limit_price=100.0)

    assert stop_fill == limit_fill == bar.open  # les deux gapent au même prix ici, par construction
