"""Tests de edgelab.strategies.models (fiche d'hypothèse, I2)."""

from collections.abc import Callable

import pytest
from edgelab.strategies.models import HypothesisSheet
from pydantic import ValidationError


def test_hypothesis_sheet_with_defaults_is_valid(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """La fiche par défaut de la factory passe sa propre validation."""
    make_hypothesis()


def test_hypothesis_sheet_rejects_empty_where_it_should_not_work(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Critère I2 : une hypothèse qui ne prédit son échec nulle part n'est pas falsifiable."""
    with pytest.raises(ValueError, match="falsifiable"):
        make_hypothesis(where_it_should_not_work="")


def test_hypothesis_sheet_rejects_whitespace_only_where_it_should_not_work(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Des espaces seuls ne comptent pas comme une condition d'échec valide."""
    with pytest.raises(ValueError, match="falsifiable"):
        make_hypothesis(where_it_should_not_work="   ")


def test_hypothesis_sheet_rejects_empty_kill_criteria(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Critère I2 : la liste des critères de mort est obligatoire et non vide."""
    with pytest.raises(ValueError, match="kill_criteria"):
        make_hypothesis(kill_criteria=())


def test_hypothesis_sheet_rejects_empty_economic_hypothesis(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """L'hypothèse économique en une phrase est obligatoire."""
    with pytest.raises(ValueError, match="economic_hypothesis"):
        make_hypothesis(economic_hypothesis="")


def test_hypothesis_sheet_rejects_hit_rate_out_of_range(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Un hit rate prédit doit rester une probabilité valide."""
    with pytest.raises(ValueError, match="predicted_hit_rate"):
        make_hypothesis(predicted_hit_rate=1.5)


def test_hypothesis_sheet_rejects_non_positive_horizon(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Un horizon prédit nul ou négatif n'a pas de sens."""
    with pytest.raises(ValueError, match="predicted_horizon_bars"):
        make_hypothesis(predicted_horizon_bars=0)


def test_hypothesis_sheet_is_frozen(make_hypothesis: Callable[..., HypothesisSheet]) -> None:
    """Une fiche d'hypothèse est immuable, comme un `Trial` (I1)."""
    hypothesis = make_hypothesis()

    with pytest.raises(ValidationError):
        hypothesis.economic_hypothesis = "changé après coup"  # type: ignore[misc]
