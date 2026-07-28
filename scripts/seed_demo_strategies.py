"""Génère des stratégies de démonstration pour peupler l'UI (Phase 8).

Ces quatre stratégies sont **synthétiques et honnêtement labellisées comme
telles** dans leur `economic_hypothesis` : elles reproduisent, sur des
rendements générés avec des propriétés connues, le motif documenté dans
`CLAUDE.md` §1 (ORB sous le plafond de friction, or intraday indiscernable
du bruit, volume brut à t-stat nul) plus une quatrième stratégie à edge
injecté qui survit. Ce ne sont PAS les résultats réels de la recherche
manuelle antérieure de l'utilisateur — juste assez de contenu réel, calculé
par les vrais modules `edgelab.validation` / `edgelab.propsim` /
`edgelab.portfolio` sur ces rendements synthétiques, pour que le leaderboard
ne soit pas vide au premier lancement (voir `CLAUDE.md` §5 : le squelette de
l'UI « donne envie de le remplir »).

Régénère `.edgelab/registry.sqlite3`, `.edgelab/lockbox.sqlite3` (état local,
gitignored) et `edgelab/api/seed_data/strategies/*.json` (committé, comme un
fixture de démonstration). Supprimer les trois avant de relancer : le
registre est append-only et refuse un `id` de trial déjà utilisé.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np
from edgelab.api.schemas import (
    ConfidenceInterval,
    InstrumentBreakdown,
    MonteCarloFan,
    NaiveComparison,
    StrategyBundle,
    SubperiodPoint,
    VolRegimePoint,
)
from edgelab.api.store import _write_bundle
from edgelab.config import DEFAULT_LOCKBOX_DB, DEFAULT_REGISTRY_DB
from edgelab.data.lockbox import HoldoutLockbox
from edgelab.propsim.baseline import simulate_with_baseline
from edgelab.propsim.loader import load_shipped_rulesets
from edgelab.propsim.risk_surface import sweep_risk_surface
from edgelab.registry.hashing import compute_lineage_hash, hash_bytes, hash_params
from edgelab.registry.models import Trial, TrialType
from edgelab.registry.repository import TrialRepository
from edgelab.research.stats import one_sample_t_test, tercile_labels, two_sample_t_test
from edgelab.strategies.models import HypothesisSheet, KillCriterion
from edgelab.universe.universe import get_universe
from edgelab.validation.bootstrap import block_bootstrap_paths, compare_block_vs_iid_bootstrap
from edgelab.validation.costs_stress import costs_stress_test
from edgelab.validation.dsr import deflated_sharpe_ratio_from_registry
from edgelab.validation.kill_criteria import StrategyLifecycleRepository, evaluate_kill_criteria
from edgelab.validation.pbo import probability_of_backtest_overfitting
from edgelab.validation.permutation import permutation_test
from edgelab.validation.start_date_sensitivity import start_date_sensitivity
from edgelab.validation.walk_forward import walk_forward
from numpy.typing import NDArray

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_demo_strategies")

_RULESET_NAME = "ftmo"
_PHASE_NAME = "challenge"
_N_PER_INSTRUMENT = 200
_N_PARTITIONS_PBO = 10
_N_START_DATES = 200
_START_WINDOW = 300
_SIGNIFICANCE_ALPHA = 0.05


@dataclass(frozen=True)
class DemoSpec:
    """Description d'une stratégie de démonstration : ce qui varie d'une idée à l'autre."""

    strategy_id: str
    family: str
    universe: str
    instruments: tuple[str, ...]
    economic_hypothesis: str
    predicted_direction: Literal["long", "short", "both"]
    predicted_amplitude_atr: float
    predicted_hit_rate: float
    predicted_horizon_bars: int
    where_it_should_not_work: str
    dominant_mean: float
    alt_means: tuple[float, ...]
    std: float
    cost_per_trade: float
    holdout_accesses: tuple[str, ...] = field(default_factory=tuple)


_DEMOS = (
    DemoSpec(
        strategy_id="demo_orb_friction_floor",
        family="ORB (Opening Range Breakout)",
        universe="fx_majors",
        instruments=("EURUSD", "GBPUSD", "USDJPY"),
        economic_hypothesis=(
            "[DÉMO SYNTHÉTIQUE] Le breakout du range des 15 premières minutes de session "
            "Londres capture un déséquilibre ordre/liquidité assez grand pour dépasser le "
            "spread + commission — reproduit le motif documenté dans CLAUDE.md §1, pas un "
            "résultat réel."
        ),
        predicted_direction="both",
        predicted_amplitude_atr=0.35,
        predicted_hit_rate=0.52,
        predicted_horizon_bars=20,
        where_it_should_not_work=(
            "Doit disparaître dès que le coût aller-retour dépasse le plafond de friction "
            "observé en session Londres, et hors des trois paires les plus liquides."
        ),
        dominant_mean=-0.04,
        alt_means=(0.02, -0.03, 0.015, -0.02),
        std=1.0,
        cost_per_trade=0.02,
        holdout_accesses=("vérification finale avant abandon de l'idée",),
    ),
    DemoSpec(
        strategy_id="demo_gold_intraday_momentum",
        family="Momentum intraday",
        universe="energy_metals",
        instruments=("XAUUSD",),
        economic_hypothesis=(
            "[DÉMO SYNTHÉTIQUE] La continuation de momentum sur l'or en intraday reflète un "
            "flux directionnel institutionnel — reproduit le motif documenté dans CLAUDE.md §1 "
            "(or intraday indiscernable du bruit), pas un résultat réel."
        ),
        predicted_direction="both",
        predicted_amplitude_atr=0.4,
        predicted_hit_rate=0.53,
        predicted_horizon_bars=15,
        where_it_should_not_work=(
            "Doit disparaître hors des heures de recouvrement Londres/New York et sur tout "
            "instrument autre que l'or."
        ),
        dominant_mean=0.0,
        alt_means=(0.01, -0.01, 0.02, -0.02),
        std=1.05,
        cost_per_trade=0.02,
        holdout_accesses=(
            "recalibrage du horizon de sortie",
            "test d'une variante de filtre de volatilité",
            "dernière vérification avant abandon",
        ),
    ),
    DemoSpec(
        strategy_id="demo_raw_volume_signal",
        family="Volume brut (déclencheur)",
        universe="index_futures",
        instruments=("ES", "NQ", "YM"),
        economic_hypothesis=(
            "[DÉMO SYNTHÉTIQUE] Un pic de volume brut au-delà de 2 écarts-types signale une "
            "prise de position institutionnelle exploitable — reproduit le motif documenté dans "
            "CLAUDE.md §1 (volume brut à t-stat nul), pas un résultat réel."
        ),
        predicted_direction="long",
        predicted_amplitude_atr=0.25,
        predicted_hit_rate=0.51,
        predicted_horizon_bars=10,
        where_it_should_not_work=(
            "Doit disparaître en dehors des trois indices les plus liquides et en l'absence de "
            "normalisation par le volume moyen de la session."
        ),
        dominant_mean=0.0,
        alt_means=(0.0, 0.0, 0.0, 0.0),
        std=1.2,
        cost_per_trade=0.02,
        holdout_accesses=("contrôle avant classement dead",) * 2,
    ),
    DemoSpec(
        strategy_id="demo_atr_trend_follow",
        family="Trend-following normalisé ATR",
        universe="broad_12",
        instruments=("EURUSD", "XAUUSD", "ES"),
        economic_hypothesis=(
            "[DÉMO SYNTHÉTIQUE] Un stop et un dimensionnement normalisés par l'ATR permettent "
            "de capturer la prime de continuation de tendance à travers des instruments non "
            "corrélés — edge injecté connu, pas un résultat réel, sert à montrer à quoi "
            "ressemble une fiche qui survit."
        ),
        predicted_direction="both",
        predicted_amplitude_atr=0.6,
        predicted_hit_rate=0.48,
        predicted_horizon_bars=40,
        where_it_should_not_work=(
            "Doit disparaître sur un univers mono-instrument ou en régime de range serré sans "
            "tendance directionnelle établie."
        ),
        dominant_mean=0.32,
        alt_means=(0.03, -0.02, 0.04, 0.0),
        std=1.0,
        cost_per_trade=0.03,
        holdout_accesses=("revue de robustesse avant validation",),
    ),
)


_MIN_OBSERVATIONS_FOR_CI = 2
_Z_95 = 1.96


def _stable_seed(text: str) -> int:
    """Graine RNG déterministe dérivée de `text`.

    `hash()` intégré à Python est randomisé par processus : deux exécutions
    de ce script produiraient des tirages différents et un artefact non
    reproductible. SHA-256 est stable d'une exécution à l'autre.
    """
    digest = hashlib.sha256(text.encode()).hexdigest()
    return int(digest, 16) % (2**32)


def _confidence_interval(returns: NDArray[np.float64]) -> ConfidenceInterval:
    n = returns.size
    mean = float(np.mean(returns))
    if n < _MIN_OBSERVATIONS_FOR_CI:
        return ConfidenceInterval(mean=mean, ci_low=mean, ci_high=mean, n=n)
    sem = float(np.std(returns, ddof=1)) / float(np.sqrt(n))
    return ConfidenceInterval(mean=mean, ci_low=mean - _Z_95 * sem, ci_high=mean + _Z_95 * sem, n=n)


def _record_trial(  # noqa: PLR0913 — un essai a intrinsèquement ces attributs (voir I1)
    repo: TrialRepository,
    *,
    strategy_id: str,
    trial_type: TrialType,
    params: dict[str, Any],
    metrics: dict[str, float],
    seq: int,
) -> None:
    code_hash = hash_bytes(f"{strategy_id}:{trial_type.value}".encode())
    params_hash = hash_params(params)
    dataset_hash = hash_bytes(f"synthetic-demo:{strategy_id}".encode())
    lineage_hash = compute_lineage_hash(
        code_hash=code_hash, params_hash=params_hash, dataset_hash=dataset_hash
    )
    repo.record(
        Trial(
            id=f"{strategy_id}__{trial_type.value}__{seq}",
            trial_type=trial_type,
            strategy_id=strategy_id,
            code_hash=code_hash,
            params=params,
            params_hash=params_hash,
            dataset_hash=dataset_hash,
            lineage_hash=lineage_hash,
            metrics=metrics,
            note=f"seed de démonstration ({trial_type.value})",
        )
    )


def _build_bundle(
    spec: DemoSpec, *, trial_repo: TrialRepository, rng: np.random.Generator
) -> StrategyBundle:
    n = _N_PER_INSTRUMENT * len(spec.instruments)
    param_grid = {
        "param_dominant": rng.normal(spec.dominant_mean, spec.std, n),
        **{
            f"param_alt_{i}": rng.normal(mean, spec.std, n) for i, mean in enumerate(spec.alt_means)
        },
    }
    returns = param_grid["param_dominant"]

    t_stat, _ = one_sample_t_test(returns)
    permutation = permutation_test(returns, n_permutations=2_000, rng=rng)
    bootstrap = compare_block_vs_iid_bootstrap(returns, block_size=10, n_resamples=1_000, rng=rng)
    walk_fwd = walk_forward(param_grid, in_sample_size=100, out_of_sample_size=50)
    pbo = probability_of_backtest_overfitting(param_grid, n_partitions=_N_PARTITIONS_PBO)
    window_length = min(_START_WINDOW, n // 2)
    start_sensitivity = start_date_sensitivity(
        returns, n_start_dates=_N_START_DATES, window_length=window_length
    )
    costs_stress = costs_stress_test(returns, spec.cost_per_trade)

    # Les essais de cette stratégie sont enregistrés AVANT le calcul du DSR : le DSR lit un
    # compteur d'essais réel (I1), il ne peut refléter que des essais déjà écrits, jamais
    # l'essai qu'il est lui-même en train de produire.
    _record_trial(
        trial_repo,
        strategy_id=spec.strategy_id,
        trial_type=TrialType.EVENT_STUDY,
        params={"instruments": list(spec.instruments)},
        metrics={"t_stat": t_stat, "n_trades": float(n)},
        seq=1,
    )
    _record_trial(
        trial_repo,
        strategy_id=spec.strategy_id,
        trial_type=TrialType.WALK_FORWARD,
        params={"in_sample_size": 100, "out_of_sample_size": 50},
        metrics={"out_of_sample_mean_return": walk_fwd.out_of_sample_mean_return},
        seq=2,
    )
    _record_trial(
        trial_repo,
        strategy_id=spec.strategy_id,
        trial_type=TrialType.OPTIMIZATION,
        params={"n_partitions": _N_PARTITIONS_PBO, "n_params": len(param_grid)},
        metrics={"pbo": pbo.probability_of_overfitting},
        seq=3,
    )

    dsr = deflated_sharpe_ratio_from_registry(returns, repository=trial_repo)

    measured_metrics = {
        "t_stat": t_stat,
        "permutation_p_value": permutation.p_value,
        "survives_2x_costs": 1.0 if costs_stress.survives_2x_costs else 0.0,
        "dsr": dsr.deflated_sharpe_ratio,
        "pbo": pbo.probability_of_overfitting,
    }
    kill_criteria = (
        KillCriterion(
            name="edge non significatif",
            metric="t_stat",
            comparison="less_than",
            threshold=2.0,
            recorded_at=_RECORDED_AT,
        ),
        KillCriterion(
            name="permutation non significative",
            metric="permutation_p_value",
            comparison="greater_than",
            threshold=0.05,
            recorded_at=_RECORDED_AT,
        ),
        KillCriterion(
            name="ne survit pas au double des coûts",
            metric="survives_2x_costs",
            comparison="less_than",
            threshold=1.0,
            recorded_at=_RECORDED_AT,
        ),
        KillCriterion(
            name="probabilité de surapprentissage trop élevée",
            metric="pbo",
            comparison="greater_than",
            threshold=0.2,
            recorded_at=_RECORDED_AT,
        ),
    )
    hypothesis = HypothesisSheet(
        strategy_id=spec.strategy_id,
        economic_hypothesis=spec.economic_hypothesis,
        predicted_direction=spec.predicted_direction,
        predicted_amplitude_atr=spec.predicted_amplitude_atr,
        predicted_hit_rate=spec.predicted_hit_rate,
        predicted_horizon_bars=spec.predicted_horizon_bars,
        where_it_should_not_work=spec.where_it_should_not_work,
        kill_criteria=kill_criteria,
        created_at=_RECORDED_AT,
    )
    verdict = evaluate_kill_criteria(hypothesis, measured_metrics)

    ruleset = load_shipped_rulesets()[_RULESET_NAME]
    propsim = simulate_with_baseline(
        returns,
        ruleset=ruleset,
        phase_name=_PHASE_NAME,
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=180,
        n_paths=20_000,
        rng=rng,
    )
    risk_surface = sweep_risk_surface(
        returns,
        ruleset=ruleset,
        phase_name=_PHASE_NAME,
        risk_levels_pct=np.arange(0.0025, 0.0225, 0.0025),
        trades_per_day=2,
        max_days=180,
        n_paths=8_000,
        rng=rng,
    )

    naive_returns = rng.normal(spec.dominant_mean * 0.25, spec.std, n)
    naive_t, naive_p = two_sample_t_test(returns, naive_returns)
    naive_comparison = NaiveComparison(
        triggered=_confidence_interval(returns),
        naive=_confidence_interval(naive_returns),
        mean_diff=float(np.mean(returns) - np.mean(naive_returns)),
        p_value=naive_p,
        improves_on_naive=bool(naive_t > 0 and naive_p < _SIGNIFICANCE_ALPHA),
    )

    chunks = np.array_split(returns, 4)
    subperiods = tuple(
        SubperiodPoint(
            label=f"T{i + 1}", stats=_confidence_interval(chunk), t_stat=one_sample_t_test(chunk)[0]
        )
        for i, chunk in enumerate(chunks)
    )

    vol_proxy = rng.random(n)
    labels = tercile_labels(vol_proxy)
    vol_regime = tuple(
        VolRegimePoint(
            tercile=tercile,
            stats=_confidence_interval(returns[labels == tercile]),
            t_stat=one_sample_t_test(returns[labels == tercile])[0],
        )
        for tercile in ("low", "mid", "high")
    )

    instrument_chunks = np.array_split(returns, len(spec.instruments))
    instrument_breakdown = tuple(
        InstrumentBreakdown(
            symbol=symbol,
            stats=_confidence_interval(chunk),
            t_stat=one_sample_t_test(chunk)[0],
            hit_rate=float(np.mean(chunk > 0.0)),
        )
        for symbol, chunk in zip(spec.instruments, instrument_chunks, strict=True)
    )

    fan_paths = block_bootstrap_paths(returns, block_size=10, n_resamples=500, rng=rng)
    fan_equity = np.cumsum(fan_paths, axis=1)
    fan = MonteCarloFan(
        trade_index=tuple(range(n)),
        p10=tuple(np.quantile(fan_equity, 0.10, axis=0).tolist()),
        p50=tuple(np.quantile(fan_equity, 0.50, axis=0).tolist()),
        p90=tuple(np.quantile(fan_equity, 0.90, axis=0).tolist()),
    )

    with StrategyLifecycleRepository(DEFAULT_LOCKBOX_DB.parent / "lifecycle.sqlite3") as lifecycle:
        lifecycle.register_hypothesis(hypothesis)
        status = lifecycle.apply_verdict(verdict)
        lineage = tuple(lifecycle.lineage(spec.strategy_id))

    with HoldoutLockbox(DEFAULT_LOCKBOX_DB) as lockbox:
        for reason in spec.holdout_accesses:
            lockbox.access(spec.strategy_id, reason)
        holdout_count = lockbox.access_count(spec.strategy_id)
        holdout_flagged = lockbox.is_flagged(spec.strategy_id)

    _record_trial(
        trial_repo,
        strategy_id=spec.strategy_id,
        trial_type=TrialType.BACKTEST,
        params={"universe": spec.universe, "cost_per_trade": spec.cost_per_trade},
        metrics={"p_pass": propsim.strategy.p_pass, "dsr": dsr.deflated_sharpe_ratio},
        seq=4,
    )

    return StrategyBundle(
        strategy_id=spec.strategy_id,
        family=spec.family,
        universe=spec.universe,
        status=status,
        lineage=lineage,
        hypothesis=hypothesis,
        kill_criteria_verdict=verdict,
        trade_r_multiples=tuple(returns.tolist()),
        equity_curve=tuple(np.cumsum(returns).tolist()),
        mae_mfe_mean_mae=float(np.mean(np.abs(np.minimum(returns - spec.std * 0.3, 0.0)))),
        mae_mfe_mean_mfe=float(np.mean(np.maximum(returns + spec.std * 0.3, 0.0))),
        subperiod_stats=subperiods,
        vol_regime_stats=vol_regime,
        naive_comparison=naive_comparison,
        instrument_breakdown=instrument_breakdown,
        monte_carlo_fan=fan,
        bootstrap_comparison=bootstrap,
        permutation=permutation,
        walk_forward=walk_fwd,
        dsr=dsr,
        pbo=pbo,
        start_date_sensitivity=start_sensitivity,
        costs_stress=costs_stress,
        propsim=propsim,
        risk_surface=risk_surface,
        ruleset_name=_RULESET_NAME,
        holdout_access_count=holdout_count,
        holdout_flagged=holdout_flagged,
    )


_RECORDED_AT = None  # renseigné dans main() une fois la date de seed choisie


def main() -> None:
    """Génère et persiste les quatre bundles de démonstration."""
    global _RECORDED_AT  # noqa: PLW0603 — constante de module fixée une fois au démarrage
    _RECORDED_AT = datetime(2026, 3, 1, tzinfo=UTC)

    for symbol_group in (d.universe for d in _DEMOS):
        get_universe(symbol_group)  # valide que l'univers existe réellement

    with TrialRepository(DEFAULT_REGISTRY_DB) as trial_repo:
        for spec in _DEMOS:
            rng = np.random.default_rng(_stable_seed(spec.strategy_id))
            logger.info("génération de %s", spec.strategy_id)
            bundle = _build_bundle(spec, trial_repo=trial_repo, rng=rng)
            _write_bundle(bundle)
            logger.info(
                "%s -> status=%s p_pass=%.4f dsr=%.4f pbo=%.4f",
                spec.strategy_id,
                bundle.status.value,
                bundle.propsim.strategy.p_pass,
                bundle.dsr.deflated_sharpe_ratio,
                bundle.pbo.probability_of_overfitting,
            )

    logger.info(
        "terminé : %d stratégies écrites dans edgelab/api/seed_data/strategies/", len(_DEMOS)
    )


if __name__ == "__main__":
    main()
