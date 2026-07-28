"""Tests de edgelab.costs.models."""

from datetime import UTC, datetime

import pytest
from edgelab.costs.models import (
    CostBreakdown,
    FixedSpreadCost,
    OrderType,
    SessionSpreadCost,
    SlippageByOrderType,
    StressedCost,
)

NOW = datetime(2024, 1, 8, 12, tzinfo=UTC)


def test_cost_breakdown_total_sums_all_components() -> None:
    """`total` est la somme de spread, commission et slippage."""
    breakdown = CostBreakdown(spread=0.1, commission=0.2, slippage=0.3)

    assert breakdown.total == pytest.approx(0.6)


def test_slippage_by_order_type_dispatches_on_order_type() -> None:
    """`for_order_type` renvoie le slippage propre à chaque type d'ordre."""
    slippage = SlippageByOrderType(market=0.0, limit=0.1, stop=0.2)

    assert slippage.for_order_type(OrderType.MARKET) == 0.0
    assert slippage.for_order_type(OrderType.LIMIT) == 0.1
    assert slippage.for_order_type(OrderType.STOP) == 0.2


def test_fixed_spread_cost_round_trip_charges_full_spread_once() -> None:
    """Le coût aller-retour facture le spread complet (2x demi-spread)."""
    model = FixedSpreadCost(spread=0.0002, commission=0.0, slippage=SlippageByOrderType())

    round_trip = model.round_trip_cost(order_type=OrderType.MARKET, timestamp=NOW)

    assert round_trip.spread == pytest.approx(0.0002)


def test_stop_order_round_trip_cost_exceeds_market_close_cost() -> None:
    """Critère d'acceptation Phase 1 : un ordre stop coûte plus cher qu'un ordre à la clôture."""
    model = FixedSpreadCost(
        spread=0.0002,
        commission=0.0,
        slippage=SlippageByOrderType(market=0.0, stop=0.0001),
    )

    stop_cost = model.round_trip_cost(order_type=OrderType.STOP, timestamp=NOW)
    market_cost = model.round_trip_cost(order_type=OrderType.MARKET, timestamp=NOW)

    assert stop_cost.total > market_cost.total


def test_fixed_spread_cost_rejects_negative_spread() -> None:
    """Un spread négatif n'a pas de sens économique et lève."""
    with pytest.raises(ValueError, match="non-negative"):
        FixedSpreadCost(spread=-0.0001, commission=0.0, slippage=SlippageByOrderType())


def test_session_spread_cost_varies_by_hour() -> None:
    """Le spread appliqué dépend de l'heure UTC de l'horodatage."""
    spread_by_hour = dict.fromkeys(range(24), 0.0001)
    spread_by_hour[22] = 0.0005  # rollover asiatique : spread élargi
    model = SessionSpreadCost(
        spread_by_hour=spread_by_hour, commission=0.0, slippage=SlippageByOrderType()
    )

    quiet_hour_cost = model.entry_cost(order_type=OrderType.MARKET, timestamp=NOW)
    rollover_cost = model.entry_cost(order_type=OrderType.MARKET, timestamp=NOW.replace(hour=22))

    assert rollover_cost.spread > quiet_hour_cost.spread


def test_session_spread_cost_requires_all_24_hours() -> None:
    """Une heure manquante dans `spread_by_hour` lève plutôt que de retomber sur un défaut."""
    incomplete = dict.fromkeys(range(23), 0.0001)  # heure 23 manquante

    with pytest.raises(ValueError, match="23"):
        SessionSpreadCost(spread_by_hour=incomplete, commission=0.0, slippage=SlippageByOrderType())


def test_stressed_cost_multiplies_every_component_by_default_factor_two() -> None:
    """`StressedCost` sans `multiplier` explicite double chaque composante (x2 par défaut)."""
    base = FixedSpreadCost(
        spread=0.0002, commission=0.00001, slippage=SlippageByOrderType(stop=0.0001)
    )
    stressed = StressedCost(base)

    base_cost = base.round_trip_cost(order_type=OrderType.STOP, timestamp=NOW)
    stressed_cost = stressed.round_trip_cost(order_type=OrderType.STOP, timestamp=NOW)

    assert stressed_cost.total == pytest.approx(base_cost.total * 2)


def test_stressed_cost_accepts_a_custom_multiplier() -> None:
    """Un multiplicateur explicite remplace le x2 par défaut."""
    base = FixedSpreadCost(spread=0.0002, commission=0.0, slippage=SlippageByOrderType())
    stressed = StressedCost(base, multiplier=3.0)

    base_cost = base.round_trip_cost(order_type=OrderType.MARKET, timestamp=NOW)
    stressed_cost = stressed.round_trip_cost(order_type=OrderType.MARKET, timestamp=NOW)

    assert stressed_cost.total == pytest.approx(base_cost.total * 3)


def test_stressed_cost_rejects_a_multiplier_below_one() -> None:
    """Un multiplicateur < 1 atténuerait le coût : ce n'est pas un test de stress."""
    base = FixedSpreadCost(spread=0.0002, commission=0.0, slippage=SlippageByOrderType())

    with pytest.raises(ValueError, match="multiplier"):
        StressedCost(base, multiplier=0.5)
