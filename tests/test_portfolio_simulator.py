"""Tests de edgelab.portfolio.simulator (Phase 6, I5)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.portfolio.simulator import simulate_portfolio
from edgelab.propsim.models import PropFirmRuleset
from edgelab.propsim.simulator import simulate_challenge


def test_simulate_portfolio_rejects_empty_returns(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un portefeuille sans aucune stratégie n'a rien à simuler."""
    with pytest.raises(ValueError, match="returns_by_strategy"):
        simulate_portfolio(
            {},
            weights={},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_simulate_portfolio_rejects_weight_keys_mismatch(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Les clés de `weights` doivent correspondre exactement à celles de `returns_by_strategy`."""
    with pytest.raises(ValueError, match="weights"):
        simulate_portfolio(
            {"a": np.array([0.5, -1.0])},
            weights={"b": 1.0},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_simulate_portfolio_rejects_weights_not_summing_to_one(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Les poids doivent sommer à 1 : ils partitionnent un unique budget de risque."""
    with pytest.raises(ValueError, match="sum to 1"):
        simulate_portfolio(
            {"a": np.array([0.5, -1.0]), "b": np.array([0.3, -0.5])},
            weights={"a": 0.4, "b": 0.4},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_simulate_portfolio_rejects_mismatched_series_lengths(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Toutes les stratégies doivent couvrir la même période pour être rééchantillonnées."""
    with pytest.raises(ValueError, match="same length"):
        simulate_portfolio(
            {"a": np.zeros(10), "b": np.zeros(20)},
            weights={"a": 0.5, "b": 0.5},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


@pytest.mark.parametrize(
    ("field", "value"), [("trades_per_day", 0), ("max_days", 0), ("n_paths", 0)]
)
def test_simulate_portfolio_rejects_non_positive_parameters(
    make_ruleset: Callable[..., PropFirmRuleset], field: str, value: int
) -> None:
    """Trades/jour, horizon et nombre de chemins doivent être strictement positifs."""
    kwargs: dict[str, object] = {"trades_per_day": 2, "max_days": 10, "n_paths": 10}
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        simulate_portfolio(
            {"a": np.array([0.5, -1.0])},
            weights={"a": 1.0},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            rng=np.random.default_rng(0),
            **kwargs,  # type: ignore[arg-type]
        )


def test_simulate_portfolio_rejects_block_size_larger_than_trade_history(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """`block_size` doit tenir dans l'historique de trades fourni pour pouvoir rééchantillonner."""
    with pytest.raises(ValueError, match="block_size"):
        simulate_portfolio(
            {"a": np.array([0.5, -1.0])},
            weights={"a": 1.0},
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            block_size=5,
            rng=np.random.default_rng(0),
        )


def test_simulate_portfolio_raises_for_unknown_phase(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un nom de palier inexistant lève une erreur explicite avant toute simulation."""
    with pytest.raises(KeyError):
        simulate_portfolio(
            {"a": np.array([0.5, -1.0])},
            weights={"a": 1.0},
            ruleset=make_ruleset(),
            phase_name="does-not-exist",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_two_perfectly_correlated_strategies_match_a_single_strategy_at_adjusted_leverage(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère d'acceptation Phase 6 : corrélation parfaite = une seule stratégie, levier ajusté.

    `a` et `b` sont la même série de trades : à poids 0,5/0,5 (même budget de
    risque total qu'une seule stratégie seule), la trajectoire combinée est
    identique à `a` seule — le portefeuille ne doit apporter aucune
    diversification puisqu'il n'y en a aucune à apporter.
    """
    ruleset = make_ruleset()
    solo = simulate_challenge(
        positive_edge_trades,
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=4000,
        rng=np.random.default_rng(10),
    )
    portfolio = simulate_portfolio(
        {"a": positive_edge_trades, "b": positive_edge_trades},
        weights={"a": 0.5, "b": 0.5},
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=4000,
        rng=np.random.default_rng(10),
    )

    assert portfolio.p_pass == solo.p_pass


def test_two_uncorrelated_strategies_with_equal_edge_give_a_strictly_higher_p_pass(
    make_edge_trades: Callable[[int], np.ndarray], make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère d'acceptation Phase 6 : décorrélées à edge égal > P(passage) d'une seule stratégie.

    La diversification réduit la variance de la trajectoire combinée sans
    changer son edge moyen, ce qui améliore P(passage) sous une contrainte
    de drawdown — c'est la valeur ajoutée du portefeuille par rapport à
    n'importe quelle stratégie prise isolément.
    """
    ruleset = make_ruleset()
    a = make_edge_trades(1)
    b = make_edge_trades(2)
    solo = simulate_challenge(
        a,
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=4000,
        rng=np.random.default_rng(20),
    )
    portfolio = simulate_portfolio(
        {"a": a, "b": b},
        weights={"a": 0.5, "b": 0.5},
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=40,
        n_paths=4000,
        rng=np.random.default_rng(20),
    )

    assert portfolio.p_pass > solo.p_pass
