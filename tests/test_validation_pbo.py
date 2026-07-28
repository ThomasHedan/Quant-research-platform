"""Tests de edgelab.validation.pbo (Probability of Backtest Overfitting, Phase 4)."""

import numpy as np
import pytest
from edgelab.validation.pbo import probability_of_backtest_overfitting


def test_pbo_rejects_fewer_than_two_params() -> None:
    """Il faut au moins deux paramètres pour qu'une sélection ait un sens."""
    with pytest.raises(ValueError, match="2 parameters"):
        probability_of_backtest_overfitting({"a": np.zeros(16)}, n_partitions=4)


@pytest.mark.parametrize("n_partitions", [1, 3, 0])
def test_pbo_rejects_odd_or_too_small_n_partitions(n_partitions: int) -> None:
    """CSCV exige un nombre pair de partitions, au moins 2, pour un découpage symétrique."""
    with pytest.raises(ValueError, match="n_partitions"):
        probability_of_backtest_overfitting(
            {"a": np.zeros(16), "b": np.zeros(16)}, n_partitions=n_partitions
        )


def test_pbo_rejects_mismatched_series_lengths() -> None:
    """Toutes les séries de paramètres doivent couvrir la même période."""
    with pytest.raises(ValueError, match="same length"):
        probability_of_backtest_overfitting({"a": np.zeros(16), "b": np.zeros(20)}, n_partitions=4)


def test_pbo_rejects_length_not_divisible_by_partitions() -> None:
    """CSCV découpe la période en blocs égaux : la longueur doit être un multiple exact."""
    with pytest.raises(ValueError, match="divisible"):
        probability_of_backtest_overfitting({"a": np.zeros(15), "b": np.zeros(15)}, n_partitions=4)


def test_pbo_is_low_for_a_stable_dominant_edge() -> None:
    """Critère de propriété connue : un edge réel et stable donne un PBO proche de zéro."""
    rng = np.random.default_rng(0)
    n = 480
    returns_by_param = {
        "true": rng.normal(0.3, 1.0, n),
        **{f"noise_{i}": rng.normal(0.0, 1.0, n) for i in range(19)},
    }

    result = probability_of_backtest_overfitting(returns_by_param, n_partitions=16)

    assert result.probability_of_overfitting < 0.05
    assert result.n_combinations == 12870  # C(16, 8)


def test_pbo_is_higher_for_pure_noise_selection() -> None:
    """Critère de propriété connue : sans edge réel, la sélection en échantillon ne vaut rien.

    Choisir le meilleur paramètre parmi du bruit pur ne prédit rien hors
    échantillon : le PBO doit être nettement plus élevé que dans le cas d'un
    edge réel et stable, la propriété comparative que ce test vérifie.
    """
    rng = np.random.default_rng(0)
    n = 480
    edge_grid = {
        "true": rng.normal(0.3, 1.0, n),
        **{f"noise_{i}": rng.normal(0.0, 1.0, n) for i in range(19)},
    }
    noise_grid = {f"noise_{i}": rng.normal(0.0, 1.0, n) for i in range(20)}

    pbo_edge = probability_of_backtest_overfitting(edge_grid, n_partitions=16)
    pbo_noise = probability_of_backtest_overfitting(noise_grid, n_partitions=16)

    assert pbo_noise.probability_of_overfitting > pbo_edge.probability_of_overfitting
    assert pbo_noise.probability_of_overfitting > 0.2
