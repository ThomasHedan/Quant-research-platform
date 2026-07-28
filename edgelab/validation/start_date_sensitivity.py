"""Sensibilité à la date de départ (Phase 4).

Lance la même stratégie à chaque décalage de départ possible et rapporte la
dispersion du résultat final. Un edge dont le résultat dépend fortement du
jour arbitraire où on a commencé à le trader n'est pas un edge stable : c'est
une fenêtre de chance ou de malchance qu'un backtest unique, démarré une
seule fois, ne peut jamais révéler.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from edgelab.validation.models import StartDateSensitivityResult

_MIN_OBSERVATIONS_FOR_STD = 2


def start_date_sensitivity(
    returns: NDArray[np.float64], *, n_start_dates: int, window_length: int
) -> StartDateSensitivityResult:
    """Rendement cumulé sur une fenêtre de `window_length` rendements, à chaque date de départ.

    La fenêtre a une longueur fixe pour chaque départ : sans cela, les
    départs tardifs auraient mécaniquement moins d'observations que les
    départs précoces, et la dispersion mesurée serait un artefact de taille
    d'échantillon, pas une vraie sensibilité à la date de départ. Si moins de
    `n_start_dates` départs valides tiennent dans `returns`, tous ceux qui
    tiennent sont utilisés (silencieusement réduit, jamais une erreur).

    Raises:
        ValueError: si `n_start_dates` ou `window_length` ne sont pas
            strictement positifs, ou si `returns` est trop court pour une
            seule fenêtre de `window_length` rendements.
    """
    if n_start_dates <= 0 or window_length <= 0:
        raise ValueError("n_start_dates and window_length must be positive")
    n = returns.size
    max_start_dates = n - window_length + 1
    if max_start_dates <= 0:
        raise ValueError(
            f"returns is too short for window_length={window_length}: got {n} observations"
        )

    actual_n_start_dates = min(n_start_dates, max_start_dates)
    final_returns = np.array(
        [
            float(np.sum(returns[start : start + window_length]))
            for start in range(actual_n_start_dates)
        ]
    )

    return StartDateSensitivityResult(
        n_start_dates=actual_n_start_dates,
        window_length=window_length,
        final_returns=tuple(final_returns.tolist()),
        mean_final_return=float(np.mean(final_returns)),
        std_final_return=(
            float(np.std(final_returns, ddof=1))
            if actual_n_start_dates >= _MIN_OBSERVATIONS_FOR_STD
            else 0.0
        ),
        min_final_return=float(np.min(final_returns)),
        max_final_return=float(np.max(final_returns)),
    )
