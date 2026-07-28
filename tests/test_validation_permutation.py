"""Tests de edgelab.validation.permutation (Phase 4)."""

import numpy as np
import pytest
from edgelab.validation.permutation import permutation_test
from scipy import stats as scipy_stats


def test_permutation_test_rejects_empty_returns() -> None:
    """Une série de rendements vide n'a rien à permuter."""
    with pytest.raises(ValueError, match="empty"):
        permutation_test(np.array([]), n_permutations=100, rng=np.random.default_rng(0))


def test_permutation_test_rejects_non_positive_n_permutations() -> None:
    """Zéro ou moins de permutations n'a pas de sens."""
    with pytest.raises(ValueError, match="n_permutations"):
        permutation_test(np.array([1.0, -1.0]), n_permutations=0, rng=np.random.default_rng(0))


def test_permutation_test_detects_a_clear_edge() -> None:
    """Un edge net et systématique produit une p-value proche de zéro."""
    rng = np.random.default_rng(1)
    returns = rng.normal(0.5, 0.1, 200)  # toujours largement positif

    result = permutation_test(returns, n_permutations=2000, rng=np.random.default_rng(2))

    assert result.p_value < 0.01


def test_permutation_test_p_value_is_uniform_on_null_edge_across_seeds() -> None:
    """Critère d'acceptation Phase 4 : sous un edge nul, la p-value est uniforme sur [0, 1].

    On construit 300 séries de rendements indépendantes à moyenne nulle
    (le vrai H0), on calcule une p-value de permutation pour chacune avec
    une graine différente, et on vérifie par un test de Kolmogorov-Smirnov
    que ces p-values sont statistiquement indiscernables d'une loi
    Uniforme(0, 1) — la propriété fondamentale d'un test de permutation
    valide quand H0 est exactement vrai.
    """
    p_values = []
    for seed in range(300):
        data_rng = np.random.default_rng(1000 + seed)
        returns = data_rng.normal(0.0, 1.0, 60)
        perm_rng = np.random.default_rng(2000 + seed)
        result = permutation_test(returns, n_permutations=500, rng=perm_rng)
        p_values.append(result.p_value)

    ks_stat, ks_p_value = scipy_stats.kstest(p_values, "uniform")

    assert ks_p_value > 0.01, f"p-values do not look uniform (KS stat={ks_stat})"


def test_permutation_test_observed_mean_matches_sample_mean() -> None:
    """`observed_mean` est simplement la moyenne de l'échantillon fourni."""
    returns = np.array([1.0, 2.0, 3.0, -1.0])

    result = permutation_test(returns, n_permutations=100, rng=np.random.default_rng(0))

    assert result.observed_mean == pytest.approx(np.mean(returns))
