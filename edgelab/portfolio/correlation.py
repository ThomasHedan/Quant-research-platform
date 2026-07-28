"""Corrélation entre stratégies, par trade et par jour (Phase 6).

Deux stratégies rentables mais corrélées peuvent breacher la perte
journalière agrégée le même jour : le propsim de portefeuille ne s'applique
jamais aux stratégies isolées (spec Phase 6). Ce module calcule la matrice
de corrélation qui alimente ce diagnostic.

Limite connue : la corrélation par trade suppose que le trade `i` de chaque
stratégie est aligné dans le temps avec le trade `i` des autres — la même
simplification que le rééchantillonnage joint de `simulator.py` (mêmes
indices de bloc partagés entre stratégies). Un vrai alignement par
horodatage attendra le moteur de backtest de la Phase 3.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import numpy as np
from numpy.typing import NDArray

from edgelab.portfolio.models import CorrelationMatrix

_MIN_STRATEGIES = 2


def correlation_matrix_by_trade(
    returns_by_strategy: Mapping[str, NDArray[np.float64]],
) -> CorrelationMatrix:
    """Corrélation des rendements trade par trade entre stratégies.

    Raises:
        ValueError: si moins de deux stratégies sont fournies, ou si leurs
            séries n'ont pas toutes la même longueur.
    """
    return _correlation_matrix(returns_by_strategy)


def aggregate_to_daily_returns(
    returns: NDArray[np.float64], *, trades_per_day: int
) -> NDArray[np.float64]:
    """Somme des rendements par blocs consécutifs de `trades_per_day` trades = un rendement/jour.

    Les derniers trades qui ne forment pas un jour complet sont tronqués,
    jamais agrégés dans un jour partiel qui fausserait sa moyenne.

    Raises:
        ValueError: si `trades_per_day` n'est pas strictement positif.
    """
    if trades_per_day <= 0:
        raise ValueError("trades_per_day must be positive")
    n_days = returns.size // trades_per_day
    trimmed = returns[: n_days * trades_per_day]
    return trimmed.reshape(n_days, trades_per_day).sum(axis=1)


def correlation_matrix_by_day(
    returns_by_strategy: Mapping[str, NDArray[np.float64]], *, trades_per_day: int
) -> CorrelationMatrix:
    """Corrélation des rendements journaliers agrégés entre stratégies.

    Raises:
        ValueError: si moins de deux stratégies, si leurs séries n'ont pas
            toutes la même longueur, ou si `trades_per_day` n'est pas positif.
    """
    daily = {
        strategy_id: aggregate_to_daily_returns(returns, trades_per_day=trades_per_day)
        for strategy_id, returns in returns_by_strategy.items()
    }
    return _correlation_matrix(daily)


def _correlation_matrix(
    returns_by_strategy: Mapping[str, NDArray[np.float64]],
) -> CorrelationMatrix:
    if len(returns_by_strategy) < _MIN_STRATEGIES:
        raise ValueError("returns_by_strategy must contain at least 2 strategies")
    lengths = {series.size for series in returns_by_strategy.values()}
    if len(lengths) != 1:
        raise ValueError("all strategy series must have the same length")

    strategy_ids = tuple(returns_by_strategy)
    stacked = np.stack([returns_by_strategy[s] for s in strategy_ids])
    corr = cast(NDArray[np.float64], np.corrcoef(stacked))
    matrix = tuple(tuple(float(x) for x in row) for row in corr)
    return CorrelationMatrix(strategy_ids=strategy_ids, matrix=matrix)
