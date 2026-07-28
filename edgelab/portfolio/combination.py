"""Explorateur de combinaisons et allocation optimale sous contrainte de drawdown (Phase 6).

L'allocation ne maximise jamais le Sharpe ni le rendement espéré : c'est
P(passage) du portefeuille combiné qui pilote la recherche, conformément à
I5. La recherche procède par tirage aléatoire sur le simplexe des poids
(distribution de Dirichlet) — P(passage) est une fonction bruitée (Monte
Carlo) et sans gradient exploitable, un problème pour lequel une recherche
aléatoire structurée est le choix standard, pas une optimisation exacte.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from edgelab.portfolio.correlation import correlation_matrix_by_trade
from edgelab.portfolio.models import (
    AllocationSearchResult,
    CombinationResult,
    MarginalContribution,
)
from edgelab.portfolio.simulator import simulate_portfolio
from edgelab.propsim.models import DailyLossGuard, PropFirmRuleset, PropSimResult
from edgelab.propsim.simulator import DEFAULT_BLOCK_SIZE, DEFAULT_INITIAL_BALANCE

_MIN_STRATEGIES_FOR_COMBINATION = 2


def explore_combination(  # noqa: PLR0913 — paramètres de simulation, transmis tels quels
    returns_by_strategy: Mapping[str, NDArray[np.float64]],
    *,
    weights: Mapping[str, float],
    ruleset: PropFirmRuleset,
    phase_name: str,
    risk_per_trade_pct: float,
    trades_per_day: int,
    max_days: int,
    n_paths: int,
    rng: np.random.Generator,
    block_size: int = DEFAULT_BLOCK_SIZE,
    initial_balance: float = DEFAULT_INITIAL_BALANCE,
    daily_loss_guard: DailyLossGuard | None = None,
) -> CombinationResult:
    """P(passage) du portefeuille, sa corrélation croisée, et la contribution marginale de chacune.

    La contribution marginale d'une stratégie est la différence entre
    P(passage) du portefeuille complet et P(passage) du même portefeuille
    sans elle (poids restants renormalisés proportionnellement) — elle peut
    être négative : ajouter une stratégie corrélée et à faible edge doit
    pouvoir dégrader le portefeuille plutôt que l'améliorer.

    Raises:
        ValueError: si moins de deux stratégies sont fournies.
    """
    if len(returns_by_strategy) < _MIN_STRATEGIES_FOR_COMBINATION:
        raise ValueError("explore_combination requires at least 2 strategies")

    def _simulate(
        weights_subset: Mapping[str, float],
        strategies_subset: Mapping[str, NDArray[np.float64]],
    ) -> PropSimResult:
        seed = int(rng.integers(0, 2**63 - 1))
        return simulate_portfolio(
            strategies_subset,
            weights=weights_subset,
            ruleset=ruleset,
            phase_name=phase_name,
            risk_per_trade_pct=risk_per_trade_pct,
            trades_per_day=trades_per_day,
            max_days=max_days,
            n_paths=n_paths,
            rng=np.random.default_rng(seed),
            block_size=block_size,
            initial_balance=initial_balance,
            daily_loss_guard=daily_loss_guard,
        )

    correlation = correlation_matrix_by_trade(returns_by_strategy)
    portfolio = _simulate(weights, returns_by_strategy)

    marginal_contributions = []
    for strategy_id in returns_by_strategy:
        remaining = {k: v for k, v in returns_by_strategy.items() if k != strategy_id}
        remaining_weight_total = sum(w for k, w in weights.items() if k != strategy_id)
        if remaining_weight_total <= 0.0:
            p_pass_without = 0.0  # aucun budget de risque restant à simuler sans cette stratégie
        else:
            renormalized = {k: weights[k] / remaining_weight_total for k in remaining}
            p_pass_without = _simulate(renormalized, remaining).p_pass
        marginal_contributions.append(
            MarginalContribution(
                strategy_id=strategy_id,
                p_pass_with=portfolio.p_pass,
                p_pass_without=p_pass_without,
            )
        )

    return CombinationResult(
        strategy_ids=tuple(returns_by_strategy),
        weights=dict(weights),
        portfolio=portfolio,
        correlation=correlation,
        marginal_contributions=tuple(marginal_contributions),
    )


def optimize_allocation(  # noqa: PLR0913 — paramètres de simulation, transmis tels quels
    returns_by_strategy: Mapping[str, NDArray[np.float64]],
    *,
    ruleset: PropFirmRuleset,
    phase_name: str,
    risk_per_trade_pct: float,
    trades_per_day: int,
    max_days: int,
    n_paths: int,
    rng: np.random.Generator,
    n_candidates: int = 30,
    block_size: int = DEFAULT_BLOCK_SIZE,
    initial_balance: float = DEFAULT_INITIAL_BALANCE,
    daily_loss_guard: DailyLossGuard | None = None,
) -> AllocationSearchResult:
    """Cherche les poids qui maximisent P(passage) — jamais le Sharpe ni le rendement espéré (I5).

    Recherche aléatoire sur le simplexe des poids (tirages de Dirichlet), le
    portefeuille équipondéré étant toujours l'un des candidats évalués pour
    servir de référence. `n_candidates` contrôle le compromis coût/qualité de
    la recherche — ce n'est pas une optimisation exacte : P(passage) est une
    sortie Monte Carlo bruitée, sans gradient exploitable.

    Raises:
        ValueError: si `returns_by_strategy` est vide, ou si `n_candidates`
            n'est pas strictement positif.
    """
    if not returns_by_strategy:
        raise ValueError("returns_by_strategy must not be empty")
    if n_candidates <= 0:
        raise ValueError("n_candidates must be positive")

    strategy_ids = list(returns_by_strategy)
    n_strategies = len(strategy_ids)
    equal_weights = np.full(n_strategies, 1.0 / n_strategies)
    random_vectors = (
        rng.dirichlet(np.ones(n_strategies), size=n_candidates - 1)
        if n_candidates > 1
        else np.empty((0, n_strategies))
    )
    candidate_vectors = [equal_weights, *random_vectors]

    def _weights_from_vector(vector: NDArray[np.float64]) -> dict[str, float]:
        return dict(zip(strategy_ids, (float(w) for w in vector), strict=True))

    def _simulate(candidate_weights: dict[str, float]) -> PropSimResult:
        seed = int(rng.integers(0, 2**63 - 1))
        return simulate_portfolio(
            returns_by_strategy,
            weights=candidate_weights,
            ruleset=ruleset,
            phase_name=phase_name,
            risk_per_trade_pct=risk_per_trade_pct,
            trades_per_day=trades_per_day,
            max_days=max_days,
            n_paths=n_paths,
            rng=np.random.default_rng(seed),
            block_size=block_size,
            initial_balance=initial_balance,
            daily_loss_guard=daily_loss_guard,
        )

    best_weights = _weights_from_vector(candidate_vectors[0])
    best_result = _simulate(best_weights)
    for vector in candidate_vectors[1:]:
        candidate_weights = _weights_from_vector(vector)
        result = _simulate(candidate_weights)
        if result.p_pass > best_result.p_pass:
            best_result = result
            best_weights = candidate_weights

    return AllocationSearchResult(
        weights=best_weights,
        portfolio=best_result,
        n_candidates_evaluated=len(candidate_vectors),
    )
