"""Tests de edgelab.validation.bootstrap (Phase 4)."""

import numpy as np
import pytest
from edgelab.validation.bootstrap import (
    block_bootstrap_paths,
    compare_block_vs_iid_bootstrap,
    iid_bootstrap_paths,
    longest_losing_streak,
    max_drawdown,
)


def test_max_drawdown_on_monotonic_gains_is_zero() -> None:
    """Une série de gains purs n'a jamais de creux."""
    returns = np.array([0.01, 0.02, 0.01, 0.03])

    assert max_drawdown(returns) == 0.0


def test_max_drawdown_measures_the_deepest_peak_to_trough_decline() -> None:
    """Le drawdown mesure l'écart maximal entre le sommet et le creux qui suit."""
    # équité cumulée : 0.1, 0.2, 0.05, 0.15 -> creux de 0.2 à 0.05 = 0.15
    returns = np.array([0.1, 0.1, -0.15, 0.10])

    assert max_drawdown(returns) == pytest.approx(0.15)


def test_max_drawdown_of_empty_array_is_zero() -> None:
    """Un tableau vide n'a pas de drawdown défini ; convention : zéro."""
    assert max_drawdown(np.array([])) == 0.0


def test_longest_losing_streak_counts_consecutive_negative_returns() -> None:
    """La plus longue série de pertes consécutives, pas le nombre total de pertes."""
    returns = np.array([1.0, -1.0, -1.0, -1.0, 1.0, -1.0])

    assert longest_losing_streak(returns) == 3


def test_longest_losing_streak_is_zero_without_any_loss() -> None:
    """Aucune perte : la série de pertes est nulle."""
    assert longest_losing_streak(np.array([1.0, 2.0, 3.0])) == 0


def test_block_bootstrap_paths_preserve_length_and_count() -> None:
    """Chaque chemin rééchantillonné a la même longueur que la série d'origine."""
    returns = np.arange(50, dtype=np.float64)
    rng = np.random.default_rng(0)

    paths = block_bootstrap_paths(returns, block_size=5, n_resamples=20, rng=rng)

    assert paths.shape == (20, 50)


def test_block_bootstrap_rejects_block_size_larger_than_series() -> None:
    """Un bloc plus grand que la série entière n'a pas de sens."""
    returns = np.arange(10, dtype=np.float64)
    rng = np.random.default_rng(0)

    with pytest.raises(ValueError, match="block_size"):
        block_bootstrap_paths(returns, block_size=11, n_resamples=10, rng=rng)


def test_block_bootstrap_rejects_non_positive_block_size() -> None:
    """Un bloc de taille nulle ou négative n'a pas de sens."""
    returns = np.arange(10, dtype=np.float64)
    rng = np.random.default_rng(0)

    with pytest.raises(ValueError, match="block_size"):
        block_bootstrap_paths(returns, block_size=0, n_resamples=10, rng=rng)


def test_iid_bootstrap_paths_preserve_length_and_count() -> None:
    """Le bootstrap iid produit aussi des chemins de la longueur d'origine."""
    returns = np.arange(50, dtype=np.float64)
    rng = np.random.default_rng(0)

    paths = iid_bootstrap_paths(returns, n_resamples=20, rng=rng)

    assert paths.shape == (20, 50)


def test_block_bootstrap_underestimation_ratio_exceeds_one_with_clustered_losses() -> None:
    """Critère du domaine : des pertes groupées font sous-estimer le drawdown par l'iid.

    Le bootstrap iid casse la dépendance sérielle qui produit le creux
    profond ; le ratio block/iid doit donc dépasser 1, et le rapport
    l'affiche systématiquement plutôt que de le masquer.
    """
    rng_data = np.random.default_rng(1)
    returns = np.concatenate(
        [
            rng_data.normal(0.002, 0.003, 80),
            -np.abs(rng_data.normal(0.01, 0.002, 20)),  # série de pertes groupée
            rng_data.normal(0.002, 0.003, 80),
        ]
    )

    comparison = compare_block_vs_iid_bootstrap(
        returns, block_size=15, n_resamples=3000, rng=np.random.default_rng(2)
    )

    assert comparison.drawdown_underestimation_ratio > 1.0
    assert comparison.streak_underestimation_ratio > 1.0


def test_compare_block_vs_iid_bootstrap_rejects_empty_returns() -> None:
    """Une série de rendements vide n'a rien à rééchantillonner."""
    with pytest.raises(ValueError, match="empty"):
        compare_block_vs_iid_bootstrap(
            np.array([]), block_size=5, n_resamples=100, rng=np.random.default_rng(0)
        )
