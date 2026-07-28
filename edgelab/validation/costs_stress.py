"""Test de coûts x2 (Phase 4).

Un edge qui ne survit pas à deux fois les coûts réalistes est trop fin pour
être exploité : le spread s'élargit, le slippage empire en période de
volatilité, la commission d'un broker change. `returns` est déjà net d'une
première couche de coûts réalistes ; ce test soustrait cette même couche une
seconde fois pour simuler leur doublement.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import stats as scipy_stats

from edgelab.validation.models import CostsStressResult

_MIN_OBSERVATIONS = 2


def costs_stress_test(
    returns: NDArray[np.float64], cost_per_trade: NDArray[np.float64] | float
) -> CostsStressResult:
    """Double le coût déjà appliqué à `returns` et mesure si le rendement moyen reste positif.

    `cost_per_trade` est le coût par trade déjà soustrait une fois pour
    produire `returns` (un scalaire appliqué uniformément, ou un tableau si
    le coût varie par trade) ; le soustraire une seconde fois porte le coût
    total à 2x.

    Raises:
        ValueError: si `returns` a moins de 2 observations.
    """
    if returns.size < _MIN_OBSERVATIONS:
        raise ValueError("returns must have at least 2 observations")

    cost_array = (
        np.full(returns.size, cost_per_trade)
        if np.isscalar(cost_per_trade)
        else np.asarray(cost_per_trade)
    )
    stressed_returns = returns - cost_array

    t_stat_net = float(scipy_stats.ttest_1samp(returns, popmean=0.0).statistic)
    stressed_test = scipy_stats.ttest_1samp(stressed_returns, popmean=0.0)

    return CostsStressResult(
        mean_return_net=float(np.mean(returns)),
        mean_return_stressed=float(np.mean(stressed_returns)),
        t_stat_net=t_stat_net,
        t_stat_stressed=float(stressed_test.statistic),
        p_value_stressed=float(stressed_test.pvalue),
        survives_2x_costs=bool(np.mean(stressed_returns) > 0.0),
    )
