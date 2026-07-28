"""Tests de edgelab.validation.dsr (Deflated Sharpe Ratio, Phase 4)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository
from edgelab.validation.dsr import deflated_sharpe_ratio, deflated_sharpe_ratio_from_registry


def test_deflated_sharpe_ratio_rejects_too_few_observations() -> None:
    """Un écart-type n'est pas défini sous deux observations."""
    with pytest.raises(ValueError, match="n_observations"):
        deflated_sharpe_ratio(
            observed_sharpe=1.0, n_observations=1, skewness=0.0, kurtosis=3.0, n_trials=10
        )


def test_deflated_sharpe_ratio_rejects_non_positive_n_trials() -> None:
    """Au moins un essai (l'essai courant lui-même) est nécessaire."""
    with pytest.raises(ValueError, match="n_trials"):
        deflated_sharpe_ratio(
            observed_sharpe=1.0, n_observations=100, skewness=0.0, kurtosis=3.0, n_trials=0
        )


def test_dsr_strictly_decreases_as_trials_increase_at_constant_sharpe() -> None:
    """Critère d'acceptation Phase 4 : le DSR décroît quand on ajoute des essais (Sharpe fixe)."""
    trial_counts = [1, 5, 20, 100, 500, 2000, 10000]
    dsr_values = [
        deflated_sharpe_ratio(
            observed_sharpe=0.5, n_observations=100, skewness=0.1, kurtosis=4.0, n_trials=n
        ).deflated_sharpe_ratio
        for n in trial_counts
    ]

    assert dsr_values == sorted(dsr_values, reverse=True)
    assert dsr_values[0] > dsr_values[-1]


def test_expected_max_sharpe_under_null_increases_with_trials() -> None:
    """Le seuil de Sharpe attendu sous H0 (pure chance) monte avec le nombre d'essais tentés."""
    low_n = deflated_sharpe_ratio(
        observed_sharpe=1.0, n_observations=200, skewness=0.0, kurtosis=3.0, n_trials=5
    )
    high_n = deflated_sharpe_ratio(
        observed_sharpe=1.0, n_observations=200, skewness=0.0, kurtosis=3.0, n_trials=5000
    )

    assert high_n.expected_max_sharpe_under_null > low_n.expected_max_sharpe_under_null


def test_deflated_sharpe_ratio_from_registry_reads_n_trials_from_the_repository(
    trial_repository: TrialRepository, make_trial: Callable[..., Trial]
) -> None:
    """`n_trials` provient d'un comptage réel du registre, jamais d'une valeur saisie à la main."""
    for i in range(7):
        trial_repository.record(make_trial(id=f"trial-{i}"))
    returns = np.random.default_rng(0).normal(0.001, 0.01, 100)

    result = deflated_sharpe_ratio_from_registry(returns, repository=trial_repository)

    assert result.n_trials == 7


def test_deflated_sharpe_ratio_from_registry_n_trials_tracks_new_recordings(
    trial_repository: TrialRepository, make_trial: Callable[..., Trial]
) -> None:
    """Enregistrer un nouvel essai fait immédiatement monter `n_trials` du DSR suivant."""
    returns = np.random.default_rng(1).normal(0.001, 0.01, 100)
    trial_repository.record(make_trial(id="trial-1"))
    first = deflated_sharpe_ratio_from_registry(returns, repository=trial_repository)

    trial_repository.record(make_trial(id="trial-2"))
    second = deflated_sharpe_ratio_from_registry(returns, repository=trial_repository)

    assert second.n_trials == first.n_trials + 1


def test_deflated_sharpe_ratio_from_registry_rejects_too_few_observations(
    trial_repository: TrialRepository,
) -> None:
    """Moins de deux rendements ne permet aucun calcul de Sharpe."""
    with pytest.raises(ValueError, match="returns"):
        deflated_sharpe_ratio_from_registry(np.array([1.0]), repository=trial_repository)
