"""Deflated Sharpe Ratio — Bailey & López de Prado (2014), Phase 4.

`deflated_sharpe_ratio` est le calcul pur (testable en isolation).
`deflated_sharpe_ratio_from_registry` est le point d'entrée qu'un rapport
doit appeler : il lit `n_trials` directement dans le `TrialRepository`,
jamais une valeur saisie à la main — sans quoi toutes les statistiques de
significativité de la plateforme deviennent mensongères (I1).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import stats as scipy_stats

from edgelab.registry.repository import TrialRepository
from edgelab.validation.models import DeflatedSharpeResult

_EULER_E = np.e


def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    n_observations: int,
    skewness: float,
    kurtosis: float,
    n_trials: int,
) -> DeflatedSharpeResult:
    """Calcule le Deflated Sharpe Ratio à partir de ses paramètres bruts.

    `kurtosis` suit la convention de Pearson (non-excédentaire : une loi
    normale a une kurtosis de 3, pas 0).

    Raises:
        ValueError: si `n_observations < 2`, ou `n_trials < 1`.
    """
    if n_observations < 2:  # noqa: PLR2004 — écart-type non défini sous 2 observations
        raise ValueError("n_observations must be >= 2")
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")

    sharpe_variance = (
        1 - skewness * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe**2
    ) / (n_observations - 1)
    sharpe_std_error = float(np.sqrt(max(sharpe_variance, 1e-12)))

    if n_trials <= 1:
        # Sans essais multiples, il n'y a pas d'effet "look-elsewhere" à corriger :
        # la formule asymptotique en valeurs extrêmes n'est de toute façon valide
        # que pour N raisonnablement grand.
        expected_max_sharpe = 0.0
    else:
        euler_gamma = float(np.euler_gamma)
        expected_max_sharpe = sharpe_std_error * (
            (1 - euler_gamma) * scipy_stats.norm.ppf(1 - 1 / n_trials)
            + euler_gamma * scipy_stats.norm.ppf(1 - 1 / (n_trials * _EULER_E))
        )

    dsr = float(scipy_stats.norm.cdf((observed_sharpe - expected_max_sharpe) / sharpe_std_error))

    return DeflatedSharpeResult(
        observed_sharpe=observed_sharpe,
        n_observations=n_observations,
        skewness=skewness,
        kurtosis=kurtosis,
        n_trials=n_trials,
        expected_max_sharpe_under_null=expected_max_sharpe,
        sharpe_std_error=sharpe_std_error,
        deflated_sharpe_ratio=dsr,
    )


def deflated_sharpe_ratio_from_registry(
    returns: NDArray[np.float64], *, repository: TrialRepository
) -> DeflatedSharpeResult:
    """Calcule le DSR d'une série de rendements, `n_trials` lu dans le registre réel.

    Raises:
        ValueError: si `returns` a moins de 2 observations.
    """
    if returns.size < 2:  # noqa: PLR2004
        raise ValueError("returns must have at least 2 observations")

    std = float(np.std(returns, ddof=1))
    observed_sharpe = float(np.mean(returns)) / std if std > 0 else 0.0
    skewness = float(scipy_stats.skew(returns))
    kurtosis = float(scipy_stats.kurtosis(returns, fisher=False))
    n_trials = len(repository.list_trials())

    return deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_observations=returns.size,
        skewness=skewness,
        kurtosis=kurtosis,
        n_trials=n_trials,
    )
