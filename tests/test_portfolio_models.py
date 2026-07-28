"""Tests de edgelab.portfolio.models (Phase 6)."""

import pytest
from edgelab.portfolio.models import CorrelationMatrix, MarginalContribution


def test_correlation_matrix_looks_up_by_strategy_name() -> None:
    """`correlation()` retrouve la valeur à l'intersection des deux stratégies nommées."""
    matrix = CorrelationMatrix(strategy_ids=("a", "b"), matrix=((1.0, 0.3), (0.3, 1.0)))

    assert matrix.correlation("a", "b") == 0.3
    assert matrix.correlation("a", "a") == 1.0


def test_correlation_matrix_raises_for_unknown_strategy() -> None:
    """Demander une stratégie absente de la matrice lève une erreur explicite."""
    matrix = CorrelationMatrix(strategy_ids=("a", "b"), matrix=((1.0, 0.3), (0.3, 1.0)))

    with pytest.raises(KeyError):
        matrix.correlation("a", "does-not-exist")


def test_marginal_contribution_delta_can_be_negative() -> None:
    """Une contribution négative signale qu'ajouter cette stratégie dégrade le portefeuille."""
    contribution = MarginalContribution(strategy_id="weak", p_pass_with=0.4, p_pass_without=0.9)

    assert contribution.delta == pytest.approx(-0.5)


def test_marginal_contribution_delta_can_be_positive() -> None:
    """Une contribution positive signale l'apport réel de la stratégie au portefeuille."""
    contribution = MarginalContribution(strategy_id="strong", p_pass_with=0.9, p_pass_without=0.4)

    assert contribution.delta == pytest.approx(0.5)
