"""Tests de edgelab.backtest.market_view (I4, Phase 3)."""

from collections.abc import Callable

import polars as pl
import pytest
from edgelab.backtest.market_view import LookAheadError, MarketView


def test_bar_at_positive_offset_raises_look_ahead_error(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """Critère d'acceptation Phase 3 (I4) : une barre future n'est jamais accessible."""
    view = MarketView({"a": make_bar_frame([100.0, 101.0, 102.0])})
    view.advance(0)

    with pytest.raises(LookAheadError):
        view.bar_at("a", offset=1)


def test_bar_at_zero_offset_returns_the_current_bar(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """Un décalage nul renvoie la barre courante."""
    bars = make_bar_frame([100.0, 101.0, 102.0])
    view = MarketView({"a": bars})
    view.advance(1)

    bar = view.bar_at("a", offset=0)

    assert bar.close == 101.0


def test_bar_at_negative_offset_returns_a_past_bar(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """Un décalage négatif renvoie une barre passée, relative à la courante."""
    bars = make_bar_frame([100.0, 101.0, 102.0])
    view = MarketView({"a": bars})
    view.advance(2)

    bar = view.bar_at("a", offset=-1)

    assert bar.close == 101.0


def test_bar_at_before_any_bar_is_known_raises_index_error(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """Avant la première barre, aucun décalage ne peut résoudre à un index valide."""
    view = MarketView({"a": make_bar_frame([100.0, 101.0])})
    view.advance(0)

    with pytest.raises(IndexError):
        view.bar_at("a", offset=-1)


def test_current_bar_is_equivalent_to_offset_zero(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """`current_bar` est un raccourci pour `bar_at(offset=0)`."""
    bars = make_bar_frame([100.0, 101.0])
    view = MarketView({"a": bars})
    view.advance(1)

    assert view.current_bar("a").close == view.bar_at("a", offset=0).close


def test_lookback_rejects_non_positive_n(make_bar_frame: Callable[..., pl.DataFrame]) -> None:
    """`n` doit être strictement positif : zéro barre n'a pas de sens."""
    view = MarketView({"a": make_bar_frame([100.0])})
    view.advance(0)

    with pytest.raises(ValueError, match="n must be positive"):
        view.lookback("a", 0)


def test_lookback_clamps_to_available_history(make_bar_frame: Callable[..., pl.DataFrame]) -> None:
    """Demander plus de barres que d'historique disponible ne lève pas, se borne silencieusement."""
    view = MarketView({"a": make_bar_frame([100.0, 101.0, 102.0])})
    view.advance(1)  # seulement 2 barres connues (index 0 et 1)

    window = view.lookback("a", 10)

    assert window.height == 2


def test_lookback_never_includes_a_bar_beyond_current_index(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """`lookback` ne renvoie jamais une barre postérieure à l'index courant (I4)."""
    view = MarketView({"a": make_bar_frame([100.0, 101.0, 102.0, 103.0])})
    view.advance(1)

    window = view.lookback("a", 2)

    assert window["close"].to_list() == [100.0, 101.0]


def test_current_index_reflects_the_last_advance(
    make_bar_frame: Callable[..., pl.DataFrame],
) -> None:
    """`current_index` reflète le dernier appel à `advance`."""
    view = MarketView({"a": make_bar_frame([100.0, 101.0])})

    view.advance(1)

    assert view.current_index == 1
