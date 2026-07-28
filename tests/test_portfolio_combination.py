"""Tests de edgelab.portfolio.combination (Phase 6, I5)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.portfolio.combination import explore_combination, optimize_allocation
from edgelab.propsim.models import PropFirmRuleset


def test_explore_combination_rejects_a_single_strategy(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """« Combinaison » n'a pas de sens avec une seule stratégie."""
    with pytest.raises(ValueError, match="at least 2 strategies"):
        explore_combination(
            {"a": positive_edge_trades},
            weights={"a": 1.0},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_explore_combination_returns_a_correlation_matrix_and_portfolio_result(
    make_edge_trades: Callable[[int], np.ndarray], make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """La combinaison expose la corrélation croisée et le résultat du portefeuille combiné."""
    result = explore_combination(
        {"a": make_edge_trades(1), "b": make_edge_trades(2)},
        weights={"a": 0.5, "b": 0.5},
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=20,
        n_paths=500,
        rng=np.random.default_rng(0),
    )

    assert result.strategy_ids == ("a", "b")
    assert result.correlation.strategy_ids == ("a", "b")
    assert len(result.marginal_contributions) == 2


def test_marginal_contribution_is_negative_for_a_pure_noise_strategy(
    make_edge_trades: Callable[[int], np.ndarray], make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère de propriété connue : ajouter une stratégie sans edge dégrade le portefeuille.

    Diluer un edge réel avec une allocation à une stratégie de bruit pur
    réduit l'edge moyen du portefeuille sans compenser par une réduction de
    variance suffisante : la contribution marginale doit donc être négative,
    exactement ce que la spec Phase 6 exige de rendre visible.
    """
    edge = make_edge_trades(1)
    noise = np.random.default_rng(5).normal(0.0, 1.0, 100)

    result = explore_combination(
        {"edge": edge, "noise": noise},
        weights={"edge": 0.5, "noise": 0.5},
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=3000,
        rng=np.random.default_rng(30),
    )

    by_id = {mc.strategy_id: mc for mc in result.marginal_contributions}
    assert by_id["noise"].delta < 0.0
    assert by_id["edge"].delta > 0.0


def test_marginal_contribution_handles_zero_remaining_weight(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Exclure la seule stratégie porteuse de tout le budget de risque laisse un reste vide."""
    result = explore_combination(
        {"a": positive_edge_trades, "b": positive_edge_trades},
        weights={"a": 1.0, "b": 0.0},
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=10,
        n_paths=200,
        rng=np.random.default_rng(0),
    )

    by_id = {mc.strategy_id: mc for mc in result.marginal_contributions}
    assert by_id["a"].p_pass_without == 0.0


def test_optimize_allocation_rejects_empty_returns(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Il n'y a rien à allouer sans aucune stratégie candidate."""
    with pytest.raises(ValueError, match="returns_by_strategy"):
        optimize_allocation(
            {},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_optimize_allocation_rejects_non_positive_n_candidates(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Zéro candidat ne permet aucune recherche."""
    with pytest.raises(ValueError, match="n_candidates"):
        optimize_allocation(
            {"a": positive_edge_trades},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
            n_candidates=0,
        )


def test_optimize_allocation_weights_always_sum_to_one(
    make_edge_trades: Callable[[int], np.ndarray], make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Chaque candidat évalué reste un budget de risque partitionné, jamais démultiplié."""
    result = optimize_allocation(
        {"a": make_edge_trades(1), "b": make_edge_trades(2)},
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=20,
        n_paths=200,
        rng=np.random.default_rng(0),
        n_candidates=5,
    )

    assert sum(result.weights.values()) == pytest.approx(1.0)
    assert result.n_candidates_evaluated == 5


def test_optimize_allocation_favors_the_real_edge_over_pure_noise(
    make_edge_trades: Callable[[int], np.ndarray], make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère de propriété connue : la recherche alloue davantage à la stratégie qui a un edge.

    C'est P(passage), pas le Sharpe ni le rendement espéré, qui pilote la
    recherche (I5) — mais dans les deux cas ici, une stratégie sans edge ne
    peut qu'être pénalisée : l'allocation optimale doit s'en détourner.
    """
    edge = make_edge_trades(1)
    noise = np.random.default_rng(5).normal(0.0, 1.0, 100)

    result = optimize_allocation(
        {"edge": edge, "noise": noise},
        ruleset=make_ruleset(),
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=1500,
        rng=np.random.default_rng(40),
        n_candidates=20,
    )

    assert result.weights["edge"] > result.weights["noise"]
