"""Tests de edgelab.validation.start_date_sensitivity (Phase 4)."""

import numpy as np
import pytest
from edgelab.validation.start_date_sensitivity import start_date_sensitivity


@pytest.mark.parametrize(("n_start_dates", "window_length"), [(0, 10), (10, 0), (-1, 10)])
def test_start_date_sensitivity_rejects_non_positive_parameters(
    n_start_dates: int, window_length: int
) -> None:
    """`n_start_dates` et `window_length` doivent être strictement positifs."""
    with pytest.raises(ValueError):
        start_date_sensitivity(
            np.zeros(100), n_start_dates=n_start_dates, window_length=window_length
        )


def test_start_date_sensitivity_rejects_series_shorter_than_window() -> None:
    """Une seule fenêtre de `window_length` doit tenir dans `returns`."""
    with pytest.raises(ValueError, match="too short"):
        start_date_sensitivity(np.zeros(10), n_start_dates=5, window_length=20)


def test_start_date_sensitivity_caps_n_start_dates_to_what_fits() -> None:
    """Moins de départs valides que demandé : la fonction réduit silencieusement, sans erreur."""
    result = start_date_sensitivity(np.zeros(15), n_start_dates=250, window_length=10)

    assert result.n_start_dates == 6  # 15 - 10 + 1


def test_start_date_sensitivity_final_returns_match_windowed_sums() -> None:
    """Chaque rendement final est bien la somme de sa fenêtre, pas une autre statistique."""
    returns = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    result = start_date_sensitivity(returns, n_start_dates=3, window_length=2)

    assert result.final_returns == (3.0, 5.0, 7.0)  # (1+2), (2+3), (3+4)


def test_start_date_sensitivity_is_higher_under_a_regime_shift_than_a_stable_regime() -> None:
    """Critère de propriété connue : un régime qui bascule produit une dispersion plus grande.

    Une série stable (même distribution partout) est peu sensible à la date
    de départ ; une série dont le régime change en cours de route (edge fort
    puis edge inversé) l'est fortement, puisque le résultat final dépend de
    la proportion de chaque régime capturée par la fenêtre.
    """
    rng = np.random.default_rng(2)
    stable = rng.normal(0.1, 1.0, 600)
    regime_shift = np.concatenate([rng.normal(1.0, 1.0, 300), rng.normal(-1.0, 1.0, 300)])

    stable_result = start_date_sensitivity(stable, n_start_dates=250, window_length=200)
    regime_result = start_date_sensitivity(regime_shift, n_start_dates=250, window_length=200)

    assert regime_result.std_final_return > 2 * stable_result.std_final_return
