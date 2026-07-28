"""Probability of Backtest Overfitting par CSCV (Phase 4).

Combinatorial Symmetric Cross-Validation (Bailey, Borwein, López de Prado &
Zhu, 2015) : la période est découpée en `n_partitions` blocs contigus égaux,
et pour chaque façon symétrique de désigner la moitié des blocs comme
échantillon d'entraînement et l'autre moitié comme test, on choisit le
paramètre gagnant en entraînement et on regarde où il se classe en test.
Un paramètre dont le rang en test est systématiquement médiocre malgré une
victoire en entraînement est le signe d'une sélection qui capture du bruit,
pas un edge stable — c'est exactement ce que `probability_of_overfitting`
mesure.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations

import numpy as np
from numpy.typing import NDArray

from edgelab.validation.models import PBOResult

_MIN_PARAMS = 2
_MIN_PARTITIONS = 2


def probability_of_backtest_overfitting(
    returns_by_param: Mapping[str, NDArray[np.float64]],
    *,
    n_partitions: int,
) -> PBOResult:
    """Calcule le PBO par CSCV sur une grille de paramètres.

    Raises:
        ValueError: si `returns_by_param` a moins de 2 paramètres, si
            `n_partitions` est impair ou < 2, si les séries n'ont pas toutes
            la même longueur, ou si cette longueur n'est pas divisible par
            `n_partitions`.
    """
    if len(returns_by_param) < _MIN_PARAMS:
        raise ValueError("returns_by_param must contain at least 2 parameters")
    if n_partitions < _MIN_PARTITIONS or n_partitions % 2 != 0:
        raise ValueError("n_partitions must be even and >= 2")
    lengths = {series.size for series in returns_by_param.values()}
    if len(lengths) != 1:
        raise ValueError("all parameter series must have the same length")
    n = lengths.pop()
    if n % n_partitions != 0:
        raise ValueError(f"series length ({n}) must be divisible by n_partitions ({n_partitions})")

    params = list(returns_by_param.keys())
    partition_size = n // n_partitions
    blocks = {
        p: [
            returns_by_param[p][i * partition_size : (i + 1) * partition_size]
            for i in range(n_partitions)
        ]
        for p in params
    }

    half = n_partitions // 2
    logits: list[float] = []
    for in_sample_indices in combinations(range(n_partitions), half):
        out_of_sample_indices = [i for i in range(n_partitions) if i not in in_sample_indices]

        in_sample_scores = {
            p: float(np.mean(np.concatenate([blocks[p][i] for i in in_sample_indices])))
            for p in params
        }
        out_of_sample_scores = {
            p: float(np.mean(np.concatenate([blocks[p][i] for i in out_of_sample_indices])))
            for p in params
        }

        winner = max(in_sample_scores, key=lambda p: in_sample_scores[p])
        sorted_oos = sorted(out_of_sample_scores.values())
        rank = sorted_oos.index(out_of_sample_scores[winner]) + 1  # 1-indexé, croissant
        relative_rank = rank / (len(params) + 1)  # dans (0, 1), jamais 0 ni 1
        logits.append(float(np.log(relative_rank / (1 - relative_rank))))

    probability_of_overfitting = float(np.mean([1.0 if lam <= 0 else 0.0 for lam in logits]))

    return PBOResult(
        n_partitions=n_partitions,
        n_combinations=len(logits),
        probability_of_overfitting=probability_of_overfitting,
        logits=tuple(logits),
    )
