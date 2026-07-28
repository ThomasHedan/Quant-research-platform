"""Test de permutation par retournement de signe (Phase 4).

Sous H0 (aucun edge directionnel réel), le signe de chaque trade est
librement échangeable : rien ne distingue un gain d'une perte de même
magnitude, la séquence observée n'est qu'un tirage parmi 2^n aussi probables
les uns que les autres. On compare la moyenne observée à la distribution des
moyennes obtenues en retournant aléatoirement le signe de chaque trade — la
p-value est la fraction de moyennes permutées au moins aussi extrêmes.

Ce test porte sur le *niveau* du edge, pas sur sa structure temporelle :
réordonner une série ne change pas sa moyenne, contrairement à un
retournement de signe. « Mélanger les dates », au sens de la spec Phase 4,
est donc opérationnalisé ici comme « détruire l'information directionnelle
que porte chaque trade tout en conservant sa magnitude ». Un test
complémentaire — rejouer la stratégie sur un historique de prix
permuté — a besoin du moteur de backtest (Phase 3) et n'existe pas encore.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from edgelab.validation.models import PermutationTestResult


def permutation_test(
    returns: NDArray[np.float64], *, n_permutations: int, rng: np.random.Generator
) -> PermutationTestResult:
    """Test de permutation par retournement de signe sur une série de rendements de trades.

    Raises:
        ValueError: si `returns` est vide ou `n_permutations` n'est pas positif.
    """
    if returns.size == 0:
        raise ValueError("returns must not be empty")
    if n_permutations <= 0:
        raise ValueError("n_permutations must be positive")

    observed_mean = float(np.mean(returns))
    n = returns.size
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_permutations, n))
    null_means = np.mean(returns[np.newaxis, :] * signs, axis=1)
    p_value = float(np.mean(np.abs(null_means) >= abs(observed_mean)))

    return PermutationTestResult(
        observed_mean=observed_mean, n_permutations=n_permutations, p_value=p_value
    )
