"""Moteur Monte Carlo de simulation de challenge prop firm (Phase 5, I5).

Prend en entrée une distribution de trades en multiples de R et la
rééchantillonne par blocs (jamais iid : la dépendance sérielle des séries de
pertes est exactement ce qui fait breacher un compte, voir
`validation/bootstrap.py`). Le risque par trade est recalculé sur le solde
courant à chaque trade (risque fixe en % du capital, avec effet de
capitalisation) — c'est la pratique de gestion de risque standard sur
laquelle ce module est bâti.

Limite connue : la granularité est le trade clôturé, pas la barre. Il n'y a
donc pas de P&L flottant intrabar, et `DrawdownBasis.EQUITY` est traité comme
`DrawdownBasis.BALANCE` — la distinction attendra le moteur de backtest
(Phase 3) qui produira un vrai P&L flottant à chaque pas de temps.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from edgelab.propsim.models import (
    DailyLossGuard,
    DrawdownType,
    PropFirmRuleset,
    PropSimResult,
)

DEFAULT_INITIAL_BALANCE = 100_000.0
DEFAULT_BLOCK_SIZE = 5
_P95 = 0.95


def simulate_challenge(  # noqa: PLR0913 — paramètres de simulation, un seul point d'entrée public
    trade_r_multiples: NDArray[np.float64],
    *,
    ruleset: PropFirmRuleset,
    phase_name: str,
    risk_per_trade_pct: float,
    trades_per_day: int,
    max_days: int,
    n_paths: int,
    rng: np.random.Generator,
    block_size: int = DEFAULT_BLOCK_SIZE,
    initial_balance: float = DEFAULT_INITIAL_BALANCE,
    daily_loss_guard: DailyLossGuard | None = None,
) -> PropSimResult:
    """Simule `n_paths` tentatives de challenge par Monte Carlo.

    Raises:
        ValueError: si `trade_r_multiples` est vide, ou si `risk_per_trade_pct`,
            `trades_per_day`, `max_days` ou `n_paths` ne sont pas strictement positifs.
        KeyError: si `phase_name` ne correspond à aucun palier du ruleset.
    """
    if trade_r_multiples.size == 0:
        raise ValueError("trade_r_multiples must not be empty")
    if risk_per_trade_pct <= 0.0:
        raise ValueError("risk_per_trade_pct must be positive")
    if trades_per_day <= 0:
        raise ValueError("trades_per_day must be positive")
    if max_days <= 0:
        raise ValueError("max_days must be positive")
    if n_paths <= 0:
        raise ValueError("n_paths must be positive")

    phase = ruleset.phase(phase_name)
    guard = daily_loss_guard if daily_loss_guard is not None and daily_loss_guard.enabled else None

    path_length = trades_per_day * max_days
    trade_paths = _resample_paths(
        trade_r_multiples,
        block_size=block_size,
        n_paths=n_paths,
        path_length=path_length,
        rng=rng,
    )

    n_pass = 0
    n_breach_daily = 0
    n_breach_dd = 0
    days_to_target: list[int] = []
    worst_days: list[float] = []

    for path in trade_paths:
        outcome = _simulate_one_path(
            path,
            trades_per_day=trades_per_day,
            max_days=max_days,
            initial_balance=initial_balance,
            max_daily_loss_pct=phase.max_daily_loss_pct,
            max_drawdown_pct=phase.max_drawdown_pct,
            drawdown_type=phase.drawdown_type,
            profit_target_pct=phase.profit_target_pct,
            min_trading_days=phase.min_trading_days,
            guard=guard,
            risk_per_trade_pct=risk_per_trade_pct,
        )
        n_pass += int(outcome.passed)
        n_breach_daily += int(outcome.breached_daily)
        n_breach_dd += int(outcome.breached_drawdown)
        if outcome.day_reached is not None:
            days_to_target.append(outcome.day_reached)
        worst_days.append(outcome.worst_day_loss_pct)

    return PropSimResult(
        firm_name=ruleset.firm_name,
        phase_name=phase.name,
        risk_per_trade_pct=risk_per_trade_pct,
        n_paths=n_paths,
        p_pass=n_pass / n_paths,
        p_breach_daily_loss=n_breach_daily / n_paths,
        p_breach_max_drawdown=n_breach_dd / n_paths,
        median_days_to_target=float(np.median(days_to_target)) if days_to_target else None,
        worst_day_pct_p95=float(np.quantile(worst_days, _P95)) if worst_days else 0.0,
    )


class _PathOutcome:
    """Résultat interne d'une trajectoire simulée — pas exposé hors de ce module."""

    __slots__ = (
        "breached_daily",
        "breached_drawdown",
        "day_reached",
        "passed",
        "worst_day_loss_pct",
    )

    def __init__(
        self,
        *,
        passed: bool,
        breached_daily: bool,
        breached_drawdown: bool,
        day_reached: int | None,
        worst_day_loss_pct: float,
    ) -> None:
        self.passed = passed
        self.breached_daily = breached_daily
        self.breached_drawdown = breached_drawdown
        self.day_reached = day_reached
        self.worst_day_loss_pct = worst_day_loss_pct


def _simulate_one_path(  # noqa: PLR0913 — mécanique de simulation, un seul point d'entrée testé
    path: NDArray[np.float64],
    *,
    trades_per_day: int,
    max_days: int,
    initial_balance: float,
    max_daily_loss_pct: float,
    max_drawdown_pct: float,
    drawdown_type: DrawdownType,
    profit_target_pct: float | None,
    min_trading_days: int,
    guard: DailyLossGuard | None,
    risk_per_trade_pct: float,
) -> _PathOutcome:
    balance = initial_balance
    peak_balance = initial_balance
    days_traded = 0
    breached_daily = False
    breached_drawdown = False
    day_reached: int | None = None
    worst_day_loss_pct = 0.0
    cursor = 0

    for day in range(max_days):
        day_start_balance = balance
        day_stopped = False

        # trades_per_day est validé > 0 par simulate_challenge : au moins un trade
        # s'exécute toujours avant que le garde-fou ne puisse arrêter la journée.
        for _ in range(trades_per_day):
            if day_stopped:
                break
            r = float(path[cursor])
            cursor += 1
            balance += r * risk_per_trade_pct * balance
            peak_balance = max(peak_balance, balance)

            daily_loss_pct = max(0.0, (day_start_balance - balance) / day_start_balance)
            worst_day_loss_pct = max(worst_day_loss_pct, daily_loss_pct)

            if guard is not None and daily_loss_pct >= guard.threshold_pct:
                day_stopped = True

            if daily_loss_pct >= max_daily_loss_pct:
                breached_daily = True
                break

            dd_reference = (
                peak_balance if drawdown_type is DrawdownType.TRAILING else initial_balance
            )
            dd_pct = max(0.0, (dd_reference - balance) / dd_reference)
            if dd_pct >= max_drawdown_pct:
                breached_drawdown = True
                break

        days_traded += 1
        if breached_daily or breached_drawdown:
            break

        target_met = profit_target_pct is not None and balance >= initial_balance * (
            1.0 + profit_target_pct
        )
        if target_met and days_traded >= min_trading_days:
            day_reached = day + 1
            break

    if breached_daily or breached_drawdown:
        passed = False
    elif profit_target_pct is None:
        # Palier sans objectif de profit (compte financé) : "passer" signifie survivre
        # sans breach sur tout l'horizon simulé, en respectant le minimum de jours tradés.
        passed = days_traded >= min_trading_days
    else:
        passed = day_reached is not None

    return _PathOutcome(
        passed=passed,
        breached_daily=breached_daily,
        breached_drawdown=breached_drawdown,
        day_reached=day_reached,
        worst_day_loss_pct=worst_day_loss_pct,
    )


def _resample_paths(
    trade_r_multiples: NDArray[np.float64],
    *,
    block_size: int,
    n_paths: int,
    path_length: int,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    """`n_paths` séquences de trades de longueur `path_length`, par bootstrap de blocs.

    Généralisation de `validation.bootstrap.block_bootstrap_paths` à une
    longueur de chemin arbitraire : propsim doit pouvoir simuler un horizon
    de plusieurs mois à partir d'un historique de trades plus court.

    Raises:
        ValueError: si `block_size` n'est pas dans [1, len(trade_r_multiples)].
    """
    n = trade_r_multiples.size
    if not 1 <= block_size <= n:
        raise ValueError(f"block_size must be in [1, {n}], got {block_size}")
    n_blocks_needed = -(-path_length // block_size)  # ceil division
    paths = np.empty((n_paths, path_length))
    for i in range(n_paths):
        block_starts = rng.integers(0, n - block_size + 1, size=n_blocks_needed)
        path = np.concatenate([trade_r_multiples[s : s + block_size] for s in block_starts])
        paths[i] = path[:path_length]
    return paths
