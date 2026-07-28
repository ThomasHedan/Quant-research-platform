"""Simulation Monte Carlo de portefeuille (Phase 6).

Combine plusieurs stratégies en une trajectoire de rendements agrégés,
rééchantillonnées par blocs avec les MÊMES indices de départ de bloc pour
toutes les stratégies à l'intérieur d'un même chemin simulé — c'est ce qui
préserve leur corrélation croisée dans le rééchantillonnage. Rééchantillonner
chaque stratégie indépendamment la détruirait entièrement, et sous-estimerait
alors le risque de breach journalier agrégé que la spec Phase 6 exige de
capturer (deux stratégies corrélées qui perdent le même jour). La trajectoire
combinée traverse ensuite exactement la même mécanique de règles jour par
jour que `propsim.simulate_challenge`, via `propsim.simulate_from_paths`,
jamais dupliquée ici.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from edgelab.propsim.models import DailyLossGuard, PropFirmRuleset, PropSimResult
from edgelab.propsim.simulator import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_INITIAL_BALANCE,
    simulate_from_paths,
)

_WEIGHT_SUM_TOLERANCE = 1e-6


def simulate_portfolio(  # noqa: PLR0913 — paramètres de simulation, transmis tels quels
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
) -> PropSimResult:
    """Simule un portefeuille de stratégies pondérées, corrélation croisée préservée.

    `weights` doit couvrir exactement les mêmes clés que `returns_by_strategy`
    et sommer à 1 : les poids partitionnent un unique budget de risque
    (`risk_per_trade_pct`) plutôt que d'en ajouter un par stratégie, pour que
    comparer des allocations différentes compare bien la même exposition
    totale du portefeuille.

    Raises:
        ValueError: si `returns_by_strategy` est vide, si les clés de
            `weights` ne correspondent pas exactement, si les poids ne
            somment pas à 1, si les séries n'ont pas toutes la même longueur,
            ou si `trades_per_day`, `max_days`, `n_paths` ou `block_size` ne
            sont pas valides.
        KeyError: si `phase_name` ne correspond à aucun palier du ruleset.
    """
    ruleset.phase(phase_name)  # échoue tôt (KeyError) avant de rééchantillonner pour rien

    combined_paths = _build_combined_paths(
        returns_by_strategy,
        weights=weights,
        trades_per_day=trades_per_day,
        max_days=max_days,
        n_paths=n_paths,
        block_size=block_size,
        rng=rng,
    )
    return simulate_from_paths(
        combined_paths,
        ruleset=ruleset,
        phase_name=phase_name,
        risk_per_trade_pct=risk_per_trade_pct,
        trades_per_day=trades_per_day,
        max_days=max_days,
        initial_balance=initial_balance,
        daily_loss_guard=daily_loss_guard,
    )


def _build_combined_paths(  # noqa: PLR0913 — paramètres de simulation, transmis tels quels
    returns_by_strategy: Mapping[str, NDArray[np.float64]],
    *,
    weights: Mapping[str, float],
    trades_per_day: int,
    max_days: int,
    n_paths: int,
    block_size: int,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    if not returns_by_strategy:
        raise ValueError("returns_by_strategy must not be empty")
    if set(weights) != set(returns_by_strategy):
        raise ValueError("weights must cover exactly the strategies in returns_by_strategy")
    if abs(sum(weights.values()) - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError("weights must sum to 1")
    if trades_per_day <= 0:
        raise ValueError("trades_per_day must be positive")
    if max_days <= 0:
        raise ValueError("max_days must be positive")
    if n_paths <= 0:
        raise ValueError("n_paths must be positive")
    lengths = {series.size for series in returns_by_strategy.values()}
    if len(lengths) != 1:
        raise ValueError("all strategy series must have the same length")
    n = lengths.pop()
    if not 1 <= block_size <= n:
        raise ValueError(f"block_size must be in [1, {n}], got {block_size}")

    strategy_ids = list(returns_by_strategy)
    path_length = trades_per_day * max_days
    n_blocks_needed = -(-path_length // block_size)  # ceil division

    combined = np.zeros((n_paths, path_length))
    for i in range(n_paths):
        block_starts = rng.integers(0, n - block_size + 1, size=n_blocks_needed)
        for strategy_id in strategy_ids:
            series = returns_by_strategy[strategy_id]
            path = np.concatenate([series[s : s + block_size] for s in block_starts])
            combined[i] += weights[strategy_id] * path[:path_length]
    return combined
