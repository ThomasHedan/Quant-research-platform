"""Tests de edgelab.propsim.simulator (Phase 5, I5)."""

from collections.abc import Callable

import numpy as np
import pytest
from edgelab.propsim.models import DailyLossGuard, DrawdownType, PropFirmRuleset
from edgelab.propsim.simulator import simulate_challenge


def test_simulate_challenge_rejects_empty_trades(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Une distribution de trades vide n'a rien à rééchantillonner."""
    with pytest.raises(ValueError, match="trade_r_multiples"):
        simulate_challenge(
            np.array([]),
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("risk_per_trade_pct", 0.0), ("trades_per_day", 0), ("max_days", 0), ("n_paths", 0)],
)
def test_simulate_challenge_rejects_non_positive_parameters(
    make_ruleset: Callable[..., PropFirmRuleset], field: str, value: int | float
) -> None:
    """Risque, trades/jour, horizon et nombre de chemins doivent être strictement positifs."""
    kwargs: dict[str, object] = {
        "risk_per_trade_pct": 0.01,
        "trades_per_day": 2,
        "max_days": 10,
        "n_paths": 10,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        simulate_challenge(
            np.array([0.5, -1.0]),
            ruleset=make_ruleset(),
            phase_name="challenge",
            rng=np.random.default_rng(0),
            **kwargs,  # type: ignore[arg-type]
        )


def test_simulate_challenge_rejects_block_size_larger_than_trade_history(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """`block_size` doit tenir dans l'historique de trades fourni pour pouvoir rééchantillonner."""
    with pytest.raises(ValueError, match="block_size"):
        simulate_challenge(
            np.array([0.5, -1.0]),
            ruleset=make_ruleset(),
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            block_size=5,
            rng=np.random.default_rng(0),
        )


def test_simulate_challenge_raises_for_unknown_phase(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un nom de palier inexistant lève une erreur explicite."""
    with pytest.raises(KeyError):
        simulate_challenge(
            np.array([0.5, -1.0]),
            ruleset=make_ruleset(),
            phase_name="does-not-exist",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=10,
            n_paths=10,
            rng=np.random.default_rng(0),
        )


def test_a_reliable_small_winner_always_passes(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un edge positif constant, sans aucune perte, atteint toujours l'objectif de profit."""
    ruleset = make_ruleset(
        phase_overrides={"profit_target_pct": 0.05, "min_trading_days": 1, "max_drawdown_pct": 0.5}
    )
    trades = np.full(20, 0.1)

    result = simulate_challenge(
        trades,
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.02,
        trades_per_day=5,
        max_days=10,
        n_paths=50,
        rng=np.random.default_rng(0),
    )

    assert result.p_pass == 1.0
    assert result.p_breach_daily_loss == 0.0
    assert result.p_breach_max_drawdown == 0.0


def test_a_reliable_large_loser_always_breaches_daily_loss(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Une perte constante et systématique breache la perte journalière avant tout objectif."""
    ruleset = make_ruleset()
    trades = np.full(20, -1.0)

    result = simulate_challenge(
        trades,
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.02,
        trades_per_day=5,
        max_days=10,
        n_paths=50,
        rng=np.random.default_rng(0),
    )

    assert result.p_pass == 0.0
    assert result.p_breach_daily_loss == 1.0


def test_same_seed_gives_reproducible_result(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Une graine identique produit un résultat de simulation identique."""
    ruleset = make_ruleset()
    kwargs: dict[str, object] = {
        "ruleset": ruleset,
        "phase_name": "challenge",
        "risk_per_trade_pct": 0.01,
        "trades_per_day": 2,
        "max_days": 20,
        "n_paths": 200,
    }

    first = simulate_challenge(positive_edge_trades, rng=np.random.default_rng(7), **kwargs)  # type: ignore[arg-type]
    second = simulate_challenge(positive_edge_trades, rng=np.random.default_rng(7), **kwargs)  # type: ignore[arg-type]

    assert first == second


def test_trailing_drawdown_gives_strictly_lower_p_pass_than_static(
    positive_edge_trades: np.ndarray, make_ruleset: Callable[..., PropFirmRuleset]
) -> None:
    """Critère d'acceptation Phase 5 : un ruleset trailing breache plus souvent qu'en statique.

    Le seuil trailing suit le plus haut de solde atteint, qui ne redescend
    jamais sous le capital initial : à drawdown_pct identique, il est donc au
    moins aussi restrictif que le seuil statique, et strictement plus
    restrictif dès qu'une trajectoire est passée en profit avant de retomber.
    """
    static_ruleset = make_ruleset(phase_overrides={"drawdown_type": DrawdownType.STATIC})
    trailing_ruleset = make_ruleset(phase_overrides={"drawdown_type": DrawdownType.TRAILING})
    kwargs: dict[str, object] = {
        "phase_name": "challenge",
        "risk_per_trade_pct": 0.01,
        "trades_per_day": 2,
        "max_days": 40,
        "n_paths": 3000,
    }

    static_result = simulate_challenge(
        positive_edge_trades,
        ruleset=static_ruleset,
        rng=np.random.default_rng(20),
        **kwargs,  # type: ignore[arg-type]
    )
    trailing_result = simulate_challenge(
        positive_edge_trades,
        ruleset=trailing_ruleset,
        rng=np.random.default_rng(20),
        **kwargs,  # type: ignore[arg-type]
    )

    assert trailing_result.p_pass < static_result.p_pass


def test_daily_loss_guard_reduces_daily_breach_probability(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Le garde-fou de perte journalière réduit la probabilité de breach journalier."""
    ruleset = make_ruleset()
    rng_data = np.random.default_rng(7)
    trades = rng_data.normal(0.1, 1.5, 200)
    kwargs: dict[str, object] = {
        "ruleset": ruleset,
        "phase_name": "challenge",
        "risk_per_trade_pct": 0.02,
        "trades_per_day": 4,
        "max_days": 40,
        "n_paths": 2000,
    }

    without_guard = simulate_challenge(trades, rng=np.random.default_rng(99), **kwargs)  # type: ignore[arg-type]
    with_guard = simulate_challenge(
        trades,
        rng=np.random.default_rng(99),
        daily_loss_guard=DailyLossGuard(enabled=True, threshold_pct=0.03),
        **kwargs,  # type: ignore[arg-type]
    )

    assert with_guard.p_breach_daily_loss < without_guard.p_breach_daily_loss


def test_funded_phase_without_profit_target_passes_by_surviving(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un palier sans objectif de profit (compte financé) passe en survivant sans breach."""
    ruleset = make_ruleset(
        phase_overrides={"profit_target_pct": None, "min_trading_days": 0, "max_drawdown_pct": 0.5}
    )
    trades = np.full(10, 0.01)

    result = simulate_challenge(
        trades,
        ruleset=ruleset,
        phase_name="challenge",
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=5,
        n_paths=10,
        rng=np.random.default_rng(0),
    )

    assert result.p_pass == 1.0
    assert result.median_days_to_target is None
