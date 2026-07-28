"""Tests de edgelab.propsim.baseline (Phase 5, I5)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.propsim.baseline import simulate_with_baseline, zero_edge_returns
from edgelab.propsim.models import PropFirmRuleset


def test_zero_edge_returns_rejects_empty_array() -> None:
    """Rien à recentrer sur un tableau vide."""
    with pytest.raises(ValueError, match="trade_r_multiples"):
        zero_edge_returns(np.array([]))


def test_zero_edge_returns_has_zero_mean() -> None:
    """Le recentrage ramène la moyenne à zéro, exactement."""
    trades = np.array([2.0, -1.0, -1.0, 2.0, -1.0])

    baseline = zero_edge_returns(trades)

    assert baseline.mean() == pytest.approx(0.0, abs=1e-12)


def test_zero_edge_returns_preserves_variance() -> None:
    """Un simple décalage ne change pas la variance : c'est tout l'intérêt de ce recentrage."""
    trades = np.array([2.0, -1.0, -1.0, 2.0, -1.0])

    baseline = zero_edge_returns(trades)

    assert baseline.var() == pytest.approx(trades.var())


def test_zero_edge_strategy_passes_more_often_than_never_but_less_than_positive_edge(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère d'acceptation Phase 5 : 0 < P(passage) baseline < P(passage) stratégie à edge.

    Sans cette borne, un beau P(passage) pourrait n'être qu'un problème de
    premier passage de barrière (une marche aléatoire de variance suffisante
    finit par toucher la cible haute avant la basse), pas la preuve d'un edge.
    """
    comparison = simulate_with_baseline(
        positive_edge_trades,
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=3000,
        rng=np.random.default_rng(10),
    )

    assert comparison.baseline.p_pass > 0.0
    assert comparison.baseline.p_pass < comparison.strategy.p_pass
    assert comparison.edge_contribution_p_pass == pytest.approx(
        comparison.strategy.p_pass - comparison.baseline.p_pass
    )
