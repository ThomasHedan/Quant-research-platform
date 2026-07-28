"""Bootstrap par blocs vs bootstrap iid (Phase 4).

Le bootstrap iid rééchantillonne chaque trade indépendamment : il détruit
toute dépendance sérielle (les séries de pertes groupées, par exemple) et
sous-estime systématiquement les métriques de queue qui en dépendent — max
drawdown, plus longue série de pertes. Le bootstrap par blocs préserve des
séquences consécutives de `block_size` trades, donc la dépendance sérielle
locale. L'écart entre les deux estimations est l'information utile.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from edgelab.validation.models import BootstrapComparison

P95 = 0.95


def max_drawdown(returns: NDArray[np.float64]) -> float:
    """Amplitude maximale de creux, en unités de rendement cumulé (>= 0)."""
    if returns.size == 0:
        return 0.0
    equity = np.cumsum(returns)
    running_max = np.maximum.accumulate(equity)
    drawdown = running_max - equity
    return float(np.max(drawdown))


def longest_losing_streak(returns: NDArray[np.float64]) -> int:
    """Plus longue séquence consécutive de rendements strictement négatifs."""
    longest = current = 0
    for r in returns:
        if r < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def block_bootstrap_paths(
    returns: NDArray[np.float64], *, block_size: int, n_resamples: int, rng: np.random.Generator
) -> NDArray[np.float64]:
    """`n_resamples` chemins rééchantillonnés par blocs consécutifs de `block_size` trades.

    Chaque chemin est construit en tirant des positions de départ de bloc
    avec remise, puis en concaténant les blocs consécutifs qui en résultent
    jusqu'à retrouver la longueur d'origine — c'est ce qui préserve la
    dépendance sérielle locale (contrairement au bootstrap iid).

    Raises:
        ValueError: si `block_size` n'est pas dans [1, len(returns)].
    """
    n = returns.size
    if not 1 <= block_size <= n:
        raise ValueError(f"block_size must be in [1, {n}], got {block_size}")
    n_blocks_needed = -(-n // block_size)  # ceil division
    paths = np.empty((n_resamples, n))
    for i in range(n_resamples):
        block_starts = rng.integers(0, n - block_size + 1, size=n_blocks_needed)
        path = np.concatenate([returns[s : s + block_size] for s in block_starts])
        paths[i] = path[:n]
    return paths


def iid_bootstrap_paths(
    returns: NDArray[np.float64], *, n_resamples: int, rng: np.random.Generator
) -> NDArray[np.float64]:
    """`n_resamples` chemins rééchantillonnés trade par trade, indépendamment (bootstrap iid)."""
    n = returns.size
    indices = rng.integers(0, n, size=(n_resamples, n))
    return returns[indices]


def compare_block_vs_iid_bootstrap(
    returns: NDArray[np.float64],
    *,
    block_size: int,
    n_resamples: int,
    rng: np.random.Generator,
) -> BootstrapComparison:
    """Compare drawdown et série de pertes p95 entre bootstrap par blocs et iid.

    Raises:
        ValueError: si `returns` est vide.
    """
    if returns.size == 0:
        raise ValueError("returns must not be empty")

    block_paths = block_bootstrap_paths(
        returns, block_size=block_size, n_resamples=n_resamples, rng=rng
    )
    iid_paths = iid_bootstrap_paths(returns, n_resamples=n_resamples, rng=rng)

    block_dd = np.array([max_drawdown(p) for p in block_paths])
    iid_dd = np.array([max_drawdown(p) for p in iid_paths])
    block_streak = np.array([longest_losing_streak(p) for p in block_paths], dtype=np.float64)
    iid_streak = np.array([longest_losing_streak(p) for p in iid_paths], dtype=np.float64)

    block_dd_p95 = float(np.quantile(block_dd, P95))
    iid_dd_p95 = float(np.quantile(iid_dd, P95))
    block_streak_p95 = float(np.quantile(block_streak, P95))
    iid_streak_p95 = float(np.quantile(iid_streak, P95))

    return BootstrapComparison(
        block_size=block_size,
        n_resamples=n_resamples,
        block_max_drawdown_p95=block_dd_p95,
        iid_max_drawdown_p95=iid_dd_p95,
        drawdown_underestimation_ratio=_safe_ratio(block_dd_p95, iid_dd_p95),
        block_worst_streak_p95=block_streak_p95,
        iid_worst_streak_p95=iid_streak_p95,
        streak_underestimation_ratio=_safe_ratio(block_streak_p95, iid_streak_p95),
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return float("nan") if numerator == 0 else float("inf")
    return numerator / denominator
