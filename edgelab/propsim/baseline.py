"""Baseline sans edge (I5) — jamais masquable, toujours calculée à côté de la stratégie.

Sans elle, une bonne surface de risque serait attribuée à l'edge de la
stratégie alors qu'elle peut n'être qu'un problème de premier passage de
barrière (une marche aléatoire de variance suffisante finit par toucher une
cible haute avant une cible basse, même sans dérive). `edge_contribution_p_pass`
sur `PropSimComparison` est le seul chiffre qui isole la contribution réelle
de l'edge.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from edgelab.propsim.models import DailyLossGuard, PropFirmRuleset, PropSimComparison
from edgelab.propsim.simulator import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_INITIAL_BALANCE,
    simulate_challenge,
)


def zero_edge_returns(trade_r_multiples: NDArray[np.float64]) -> NDArray[np.float64]:
    """Même variance que `trade_r_multiples`, moyenne ramenée à zéro par recentrage.

    Un décalage ne change pas la variance : c'est la construction la plus
    simple et la plus honnête d'un « profil de variance identique, edge nul ».

    Raises:
        ValueError: si `trade_r_multiples` est vide.
    """
    if trade_r_multiples.size == 0:
        raise ValueError("trade_r_multiples must not be empty")
    return trade_r_multiples - np.mean(trade_r_multiples)


def simulate_with_baseline(  # noqa: PLR0913 — paramètres de simulation, transmis tels quels
    trade_r_multiples: NDArray[np.float64],
    *,
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
) -> PropSimComparison:
    """P(passage) de la stratégie ET de sa baseline sans edge, côte à côte (I5).

    Deux générateurs indépendants dérivés de `rng` pour que la baseline ne
    soit pas simulée sur la même séquence de résidus aléatoires que la
    stratégie, ce qui biaiserait leur comparaison.
    """
    strategy_seed, baseline_seed = rng.integers(0, 2**63 - 1, size=2)

    strategy = simulate_challenge(
        trade_r_multiples,
        ruleset=ruleset,
        phase_name=phase_name,
        risk_per_trade_pct=risk_per_trade_pct,
        trades_per_day=trades_per_day,
        max_days=max_days,
        n_paths=n_paths,
        rng=np.random.default_rng(int(strategy_seed)),
        block_size=block_size,
        initial_balance=initial_balance,
        daily_loss_guard=daily_loss_guard,
    )
    baseline = simulate_challenge(
        zero_edge_returns(trade_r_multiples),
        ruleset=ruleset,
        phase_name=phase_name,
        risk_per_trade_pct=risk_per_trade_pct,
        trades_per_day=trades_per_day,
        max_days=max_days,
        n_paths=n_paths,
        rng=np.random.default_rng(int(baseline_seed)),
        block_size=block_size,
        initial_balance=initial_balance,
        daily_loss_guard=daily_loss_guard,
    )
    return PropSimComparison(strategy=strategy, baseline=baseline)
