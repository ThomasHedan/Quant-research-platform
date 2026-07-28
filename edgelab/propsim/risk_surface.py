"""Surface de risque : P(passage) en fonction du risque par trade (I5).

La courbe attendue est en cloche, pas monotone : un risque trop faible
échoue par temps écoulé (l'objectif de profit n'est pas atteint dans
l'horizon simulé), un risque trop fort échoue par breach (perte journalière
ou drawdown). L'optimum se situe très en dessous du critère de Kelly, car la
contrainte de drawdown domine — c'est le résultat le plus important que la
plateforme produit (`CLAUDE.md` §4, Phase 5).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from edgelab.propsim.models import (
    DailyLossGuard,
    PropFirmRuleset,
    RiskSurfacePoint,
    RiskSurfaceResult,
)
from edgelab.propsim.simulator import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_INITIAL_BALANCE,
    simulate_challenge,
)

_MIN_OBSERVATIONS_FOR_VARIANCE = 2


def kelly_fraction(trade_r_multiples: NDArray[np.float64]) -> float:
    """Fraction de Kelly continue (moyenne / variance) pour des gains en multiples de R.

    Approximation standard pour un payoff continu (f* = E[R] / Var[R]), par
    opposition à la formule binaire gain/perte qui suppose deux issues
    discrètes. Négative ou nulle si l'edge est nul ou négatif : un signal, pas
    une erreur.

    Raises:
        ValueError: si `trade_r_multiples` a moins de 2 observations.
    """
    if trade_r_multiples.size < _MIN_OBSERVATIONS_FOR_VARIANCE:
        raise ValueError("trade_r_multiples must have at least 2 observations")
    variance = float(np.var(trade_r_multiples, ddof=1))
    if variance == 0.0:
        return 0.0
    return float(np.mean(trade_r_multiples)) / variance


def sweep_risk_surface(  # noqa: PLR0913 — paramètres de simulation, transmis tels quels
    trade_r_multiples: NDArray[np.float64],
    *,
    ruleset: PropFirmRuleset,
    phase_name: str,
    risk_levels_pct: NDArray[np.float64],
    trades_per_day: int,
    max_days: int,
    n_paths: int,
    rng: np.random.Generator,
    block_size: int = DEFAULT_BLOCK_SIZE,
    initial_balance: float = DEFAULT_INITIAL_BALANCE,
    daily_loss_guard: DailyLossGuard | None = None,
) -> RiskSurfaceResult:
    """Balaie `risk_levels_pct`, une graine indépendante par niveau pour ne pas
    corréler artificiellement les points de la courbe entre eux.

    Raises:
        ValueError: si `risk_levels_pct` est vide.
    """
    if risk_levels_pct.size == 0:
        raise ValueError("risk_levels_pct must not be empty")

    seeds = rng.integers(0, 2**63 - 1, size=risk_levels_pct.size)
    points = []
    for risk_pct, seed in zip(risk_levels_pct, seeds, strict=True):
        result = simulate_challenge(
            trade_r_multiples,
            ruleset=ruleset,
            phase_name=phase_name,
            risk_per_trade_pct=float(risk_pct),
            trades_per_day=trades_per_day,
            max_days=max_days,
            n_paths=n_paths,
            rng=np.random.default_rng(int(seed)),
            block_size=block_size,
            initial_balance=initial_balance,
            daily_loss_guard=daily_loss_guard,
        )
        points.append(RiskSurfacePoint(risk_per_trade_pct=float(risk_pct), p_pass=result.p_pass))

    return RiskSurfaceResult(points=tuple(points), kelly_fraction=kelly_fraction(trade_r_multiples))
