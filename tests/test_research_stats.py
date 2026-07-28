"""Tests de edgelab.research.stats (fonctions statistiques pures, Phase 2)."""

import numpy as np
import pytest
from edgelab.research.stats import (
    hit_rate,
    mean_excluding_top,
    one_sample_t_test,
    tercile_labels,
    two_sample_t_test,
)


def test_one_sample_t_test_detects_a_clear_positive_mean() -> None:
    """Un échantillon nettement positif produit un t-stat positif et significatif."""
    rng = np.random.default_rng(0)
    returns = rng.normal(0.5, 1.0, 500)

    t_stat, p_value = one_sample_t_test(returns)

    assert t_stat > 1.96
    assert p_value < 0.05


def test_one_sample_t_test_is_not_significant_on_pure_noise() -> None:
    """Bruit pur (moyenne nulle) : critère domaine — pas de conclusion positive."""
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0, 1.0, 500)

    t_stat, _ = one_sample_t_test(returns)

    assert abs(t_stat) < 1.96


def test_one_sample_t_test_returns_neutral_result_below_two_observations() -> None:
    """Moins de deux observations : aucune conclusion statistique possible."""
    assert one_sample_t_test(np.array([1.0])) == (0.0, 1.0)
    assert one_sample_t_test(np.array([])) == (0.0, 1.0)


def test_one_sample_t_test_returns_neutral_result_for_zero_variance() -> None:
    """Une variance nulle rendrait le t-stat infini : renvoyer un résultat neutre plutôt."""
    assert one_sample_t_test(np.array([1.0, 1.0, 1.0])) == (0.0, 1.0)


def test_two_sample_t_test_detects_a_mean_difference() -> None:
    """Deux échantillons de moyennes nettement différentes produisent un t-stat significatif."""
    rng = np.random.default_rng(2)
    a = rng.normal(0.0, 1.0, 300)
    b = rng.normal(2.0, 1.0, 300)

    t_stat, p_value = two_sample_t_test(a, b)

    assert t_stat < -1.96
    assert p_value < 0.05


def test_two_sample_t_test_returns_neutral_result_below_two_observations() -> None:
    """Un échantillon trop petit ne permet aucune conclusion."""
    assert two_sample_t_test(np.array([1.0]), np.array([1.0, 2.0])) == (0.0, 1.0)


def test_hit_rate_computes_fraction_of_positive_returns() -> None:
    """`hit_rate` est la fraction stricte de rendements positifs."""
    returns = np.array([1.0, -1.0, 2.0, -0.5])

    assert hit_rate(returns) == pytest.approx(0.5)


def test_hit_rate_is_zero_for_empty_array() -> None:
    """Un échantillon vide n'a pas de hit rate défini ; convention : zéro."""
    assert hit_rate(np.array([])) == 0.0


def test_mean_excluding_top_drops_the_highest_fraction() -> None:
    """Exclure les 20% les plus hauts sur 5 valeurs en retire une, la plus grande."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 100.0])

    mean, n_excluded = mean_excluding_top(values, 0.2)

    assert n_excluded == 1
    assert mean == pytest.approx(2.5)  # moyenne de [1, 2, 3, 4]


def test_mean_excluding_top_is_never_dominated_by_a_single_outlier() -> None:
    """L'espérance hors 5% des meilleurs trades est bornée par les valeurs restantes."""
    values = np.array([0.001] * 95 + [10.0] * 5)  # 5% de valeurs extrêmes

    mean, n_excluded = mean_excluding_top(values, 0.05)

    assert n_excluded == 5
    assert mean == pytest.approx(0.001)


def test_mean_excluding_top_handles_an_empty_array() -> None:
    """Un échantillon vide ne fait pas planter le calcul."""
    assert mean_excluding_top(np.array([]), 0.05) == (0.0, 0)


def test_tercile_labels_splits_into_three_roughly_equal_buckets() -> None:
    """Neuf valeurs ordonnées se répartissent en trois terciles de trois."""
    values = np.array([1.0, 2, 3, 4, 5, 6, 7, 8, 9])

    labels = tercile_labels(values)

    assert list(labels[:3]) == ["low", "low", "low"]
    assert list(labels[3:6]) == ["mid", "mid", "mid"]
    assert list(labels[6:]) == ["high", "high", "high"]
