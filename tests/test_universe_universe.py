"""Tests de edgelab.universe.instrument et edgelab.universe.universe."""

from datetime import UTC, datetime

import pytest
from edgelab.costs.models import OrderType
from edgelab.universe.instrument import AssetClass, Instrument
from edgelab.universe.universe import (
    BROAD_12,
    ENERGY_METALS,
    FX_MAJORS,
    INDEX_FUTURES,
    Universe,
    get_universe,
)


def test_instrument_rejects_non_positive_pip_size(eurusd: Instrument) -> None:
    """`pip_size` doit être strictement positif."""
    with pytest.raises(ValueError, match="pip_size"):
        Instrument(
            symbol="X",
            name="x",
            asset_class=AssetClass.FX,
            session_calendar=eurusd.session_calendar,
            cost_model=eurusd.cost_model,
            price_decimals=5,
            pip_size=0.0,
        )


def test_instrument_rejects_negative_price_decimals(eurusd: Instrument) -> None:
    """`price_decimals` doit être positif ou nul."""
    with pytest.raises(ValueError, match="price_decimals"):
        Instrument(
            symbol="X",
            name="x",
            asset_class=AssetClass.FX,
            session_calendar=eurusd.session_calendar,
            cost_model=eurusd.cost_model,
            price_decimals=-1,
            pip_size=0.0001,
        )


def test_universe_rejects_duplicate_symbols(eurusd: Instrument) -> None:
    """Un univers ne peut pas contenir deux instruments de même symbole."""
    with pytest.raises(ValueError, match="duplicate"):
        Universe("dup", (eurusd, eurusd))


def test_universe_symbols_preserve_definition_order() -> None:
    """`symbols` reflète l'ordre de définition des instruments."""
    assert FX_MAJORS.symbols == (
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCHF",
        "AUDUSD",
        "USDCAD",
    )


def test_universe_get_returns_the_matching_instrument() -> None:
    """`get` renvoie l'instrument portant le symbole demandé."""
    assert FX_MAJORS.get("EURUSD").symbol == "EURUSD"


def test_universe_get_raises_for_unknown_symbol() -> None:
    """`get` sur un symbole absent lève une `KeyError` explicite."""
    with pytest.raises(KeyError):
        FX_MAJORS.get("NOTASYMBOL")


def test_get_universe_returns_named_universe() -> None:
    """`get_universe` résout un univers par son nom."""
    assert get_universe("fx_majors") is FX_MAJORS


def test_get_universe_raises_for_unknown_name() -> None:
    """`get_universe` sur un nom inconnu lève une `KeyError` listant les univers disponibles."""
    with pytest.raises(KeyError, match="fx_majors"):
        get_universe("does-not-exist")


def test_broad_12_covers_exactly_the_three_named_universes() -> None:
    """`broad_12` est l'union de fx_majors, index_futures et energy_metals."""
    assert set(BROAD_12.symbols) == set(FX_MAJORS.symbols) | set(INDEX_FUTURES.symbols) | set(
        ENERGY_METALS.symbols
    )
    assert len(BROAD_12.instruments) == 12


@pytest.mark.parametrize(
    "universe", [FX_MAJORS, INDEX_FUTURES, ENERGY_METALS, BROAD_12], ids=lambda u: u.name
)
def test_every_named_universe_instrument_has_a_working_cost_model(universe: Universe) -> None:
    """Chaque instrument de chaque univers livré expose un coût aller-retour utilisable."""
    now = datetime(2024, 1, 8, 12, tzinfo=UTC)
    for instrument in universe.instruments:
        cost = instrument.cost_model.round_trip_cost(order_type=OrderType.MARKET, timestamp=now)
        assert cost.total >= 0
