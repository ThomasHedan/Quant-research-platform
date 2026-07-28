"""Tests de edgelab.validation.costs_stress (test de coûts x2, Phase 4)."""

import numpy as np
import pytest
from edgelab.validation.costs_stress import costs_stress_test


def test_costs_stress_test_rejects_too_few_observations() -> None:
    """Une seule observation ne permet aucun test statistique."""
    with pytest.raises(ValueError, match="returns"):
        costs_stress_test(np.array([1.0]), cost_per_trade=0.01)


def test_costs_stress_test_subtracts_the_cost_a_second_time() -> None:
    """Le rendement stressé est le rendement net moins une nouvelle fois le coût déjà appliqué."""
    returns = np.array([0.01, 0.02, 0.015, 0.012, 0.018])

    result = costs_stress_test(returns, cost_per_trade=0.005)

    assert result.mean_return_stressed == pytest.approx(result.mean_return_net - 0.005)


def test_costs_stress_test_accepts_a_per_trade_cost_array() -> None:
    """Le coût peut varier par trade plutôt qu'être un scalaire uniforme."""
    returns = np.array([0.01, 0.02, 0.015, 0.012, 0.018])
    costs = np.array([0.005, 0.006, 0.004, 0.005, 0.007])

    result = costs_stress_test(returns, cost_per_trade=costs)

    assert result.mean_return_stressed == pytest.approx(np.mean(returns - costs))


def test_a_robust_edge_survives_doubled_costs() -> None:
    """Critère de propriété connue : un edge large devant le coût survit à son doublement."""
    rng = np.random.default_rng(42)
    robust_edge = np.full(50, 0.003) + rng.normal(0, 0.0005, 50)

    result = costs_stress_test(robust_edge, cost_per_trade=0.001)

    assert result.survives_2x_costs is True
    assert result.mean_return_stressed > 0.0


def test_a_thin_edge_does_not_survive_doubled_costs() -> None:
    """Critère de propriété connue : un edge à peine au-dessus du coût ne survit pas au x2."""
    rng = np.random.default_rng(42)
    thin_edge = np.full(50, 0.0008) + rng.normal(0, 0.0002, 50)

    result = costs_stress_test(thin_edge, cost_per_trade=0.001)

    assert result.survives_2x_costs is False
    assert result.mean_return_stressed < 0.0
