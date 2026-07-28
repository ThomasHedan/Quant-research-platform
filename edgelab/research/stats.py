"""Fonctions statistiques pures utilisées par l'event study (Phase 2).

Toutes ces fonctions opèrent sur des tableaux NumPy déjà extraits — aucune
n'accède au disque, au réseau, ou à un DataFrame Polars. C'est le cœur pur et
testable du module (voir CLAUDE.md §6 : « effets de bord aux frontières,
cœur pur et testable »).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import stats as scipy_stats

_MIN_SAMPLE_SIZE = 2


def one_sample_t_test(returns: NDArray[np.float64]) -> tuple[float, float]:
    """t-stat et p-value d'un test contre H0 : moyenne == 0.

    Renvoie `(0.0, 1.0)` — aucune conclusion possible — s'il y a moins de
    deux observations ou si la variance est nulle (division par zéro).
    """
    if returns.size < _MIN_SAMPLE_SIZE or np.std(returns, ddof=1) == 0:
        return 0.0, 1.0
    t_stat, p_value = scipy_stats.ttest_1samp(returns, popmean=0.0)
    return float(t_stat), float(p_value)


def two_sample_t_test(a: NDArray[np.float64], b: NDArray[np.float64]) -> tuple[float, float]:
    """t-stat et p-value d'un test de Welch (variances inégales) entre deux échantillons."""
    if a.size < _MIN_SAMPLE_SIZE or b.size < _MIN_SAMPLE_SIZE:
        return 0.0, 1.0
    t_stat, p_value = scipy_stats.ttest_ind(a, b, equal_var=False)
    return float(t_stat), float(p_value)


def hit_rate(returns: NDArray[np.float64]) -> float:
    """Fraction des rendements strictement positifs."""
    if returns.size == 0:
        return 0.0
    return float(np.mean(returns > 0))


def mean_excluding_top(returns: NDArray[np.float64], top_pct: float) -> tuple[float, int]:
    """Moyenne des rendements après exclusion du `top_pct` le plus élevé.

    Renvoie `(moyenne, nombre de trades exclus)`. N'exclut rien si
    l'échantillon est trop petit pour qu'au moins un trade sorte.
    """
    n = returns.size
    if n == 0:
        return 0.0, 0
    n_excluded = int(np.ceil(n * top_pct))
    if n_excluded <= 0 or n_excluded >= n:
        return float(np.mean(returns)), 0
    kept = np.sort(returns)[: n - n_excluded]
    return float(np.mean(kept)), n_excluded


def tercile_labels(values: NDArray[np.float64]) -> NDArray[np.str_]:
    """Étiquette chaque valeur `"low"` / `"mid"` / `"high"` par tercile empirique."""
    low_cut, high_cut = np.quantile(values, [1 / 3, 2 / 3])
    return np.where(values <= low_cut, "low", np.where(values <= high_cut, "mid", "high"))
