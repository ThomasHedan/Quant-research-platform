"""Combinaison de stratégies, corrélation, allocation sous contrainte de drawdown (Phase 6)."""

from edgelab.portfolio.combination import explore_combination, optimize_allocation
from edgelab.portfolio.correlation import (
    aggregate_to_daily_returns,
    correlation_matrix_by_day,
    correlation_matrix_by_trade,
)
from edgelab.portfolio.models import (
    AllocationSearchResult,
    CombinationResult,
    CorrelationMatrix,
    MarginalContribution,
)
from edgelab.portfolio.simulator import simulate_portfolio

__all__ = [
    "AllocationSearchResult",
    "CombinationResult",
    "CorrelationMatrix",
    "MarginalContribution",
    "aggregate_to_daily_returns",
    "correlation_matrix_by_day",
    "correlation_matrix_by_trade",
    "explore_combination",
    "optimize_allocation",
    "simulate_portfolio",
]
