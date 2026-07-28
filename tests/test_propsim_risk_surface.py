"""Tests de edgelab.propsim.risk_surface (Phase 5, I5)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.propsim.models import PropFirmRuleset
from edgelab.propsim.risk_surface import kelly_fraction, sweep_risk_surface


def test_kelly_fraction_rejects_too_few_observations() -> None:
    """La variance n'est pas définie sous deux observations."""
    with pytest.raises(ValueError, match="trade_r_multiples"):
        kelly_fraction(np.array([1.0]))


def test_kelly_fraction_is_positive_for_a_positive_edge(positive_edge_trades: np.ndarray) -> None:
    """Un edge net positif donne une fraction de Kelly positive."""
    assert kelly_fraction(positive_edge_trades) > 0.0


def test_kelly_fraction_is_zero_for_zero_variance() -> None:
    """Une variance nulle (trades identiques) ne doit pas produire de division par zéro."""
    assert kelly_fraction(np.array([1.0, 1.0, 1.0])) == 0.0


def test_sweep_risk_surface_rejects_empty_risk_levels(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Balayer une liste de niveaux de risque vide n'a pas de sens."""
    with pytest.raises(ValueError, match="risk_levels_pct"):
        sweep_risk_surface(
            positive_edge_trades,
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_levels_pct=np.array([]),
            trades_per_day=2,
            max_days=40,
            n_paths=100,
            rng=np.random.default_rng(0),
        )


def test_risk_surface_has_an_interior_maximum(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère d'acceptation Phase 5 : la surface de risque est en cloche, pas monotone.

    Un risque trop faible n'atteint pas l'objectif de profit dans l'horizon
    simulé ; un risque trop fort breache la perte journalière ou le drawdown.
    L'optimum est donc strictement à l'intérieur du balayage, pas à une
    extrémité.
    """
    levels = np.arange(0.0025, 0.021, 0.0025)  # 0.25 % à 2 %, comme spécifié

    surface = sweep_risk_surface(
        positive_edge_trades,
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_levels_pct=levels,
        trades_per_day=2,
        max_days=40,
        n_paths=2000,
        rng=np.random.default_rng(11),
    )

    p_pass_values = [p.p_pass for p in surface.points]
    best_index = p_pass_values.index(max(p_pass_values))

    assert 0 < best_index < len(p_pass_values) - 1
    assert p_pass_values[best_index] > p_pass_values[0]
    assert p_pass_values[best_index] > p_pass_values[-1]


def test_risk_surface_optimum_sits_well_below_the_kelly_fraction(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """L'optimum de P(passage) est très en dessous du critère de Kelly (contrainte de drawdown).

    C'est le résultat le plus important que la plateforme produit (CLAUDE.md
    §4, Phase 5) : maximiser le rendement composé (Kelly) n'est pas la même
    chose que maximiser la probabilité de passer un challenge à drawdown
    borné.
    """
    levels = np.arange(0.0025, 0.021, 0.0025)

    surface = sweep_risk_surface(
        positive_edge_trades,
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_levels_pct=levels,
        trades_per_day=2,
        max_days=40,
        n_paths=2000,
        rng=np.random.default_rng(11),
    )

    assert surface.best_point.risk_per_trade_pct < surface.kelly_fraction
