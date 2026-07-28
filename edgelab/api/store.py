"""Lecture des artefacts que l'API sert (I3 lockbox, bundles de stratégie, registre).

Ce module ne calcule jamais un résultat statistique ou de simulation : il lit
des fichiers JSON déjà produits (`edgelab/api/seed_data/`, voir
`scripts/seed_demo_strategies.py`) et le registre SQLite réel. Les deux
exceptions — `run_combination` et `run_risk_surface` — délèguent entièrement
à `edgelab.portfolio` / `edgelab.propsim` : ce sont des déclencheurs de job
(le README de l'API les autorise explicitement), pas de la logique métier
propre à l'API, puisqu'aucune décision n'y est prise et qu'aucun calcul n'y
est dupliqué.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

from edgelab.api.schemas import LeaderboardRow, StrategyBundle
from edgelab.config import DEFAULT_LOCKBOX_DB, DEFAULT_REGISTRY_DB
from edgelab.data.lockbox import HoldoutLockbox
from edgelab.portfolio.combination import explore_combination, optimize_allocation
from edgelab.portfolio.correlation import correlation_matrix_by_trade
from edgelab.portfolio.models import AllocationSearchResult, CombinationResult, CorrelationMatrix
from edgelab.propsim.loader import load_shipped_rulesets
from edgelab.propsim.models import PropFirmRuleset, RiskSurfaceResult
from edgelab.propsim.risk_surface import sweep_risk_surface
from edgelab.propsim.simulator import DEFAULT_BLOCK_SIZE
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_LOCKBOX_DB",
    "DEFAULT_REGISTRY_DB",
    "SEED_DATA_DIR",
    "StrategyNotFoundError",
    "get_bundle",
    "get_ruleset",
    "holdout_access_count",
    "leaderboard_rows",
    "list_bundles",
    "list_rulesets",
    "registry_trial_count",
    "registry_trials",
    "run_combination",
    "run_correlation",
    "run_optimize_allocation",
    "run_risk_surface",
]
"""`DEFAULT_REGISTRY_DB`/`DEFAULT_LOCKBOX_DB` sont réexportés délibérément : les tests
monkeypatchent `store.DEFAULT_REGISTRY_DB` pour isoler chaque cas sur un registre
temporaire, ce qui exige que le nom vive dans l'espace de noms de ce module."""

SEED_DATA_DIR = Path(__file__).parent / "seed_data" / "strategies"

_N_PATHS_INTERACTIVE = 2_000
"""Nombre de trajectoires Monte Carlo pour les endpoints interactifs (job triggers).

Plus faible que les 20 000+ utilisées pour les artefacts précalculés du seed :
un endpoint appelé depuis l'UI doit répondre en dessous de la seconde, la
précision du dernier chiffre significatif n'est pas ce qui est demandé ici.
"""

_N_PATHS_OPTIMIZE = 400
_N_CANDIDATES_OPTIMIZE = 12
"""`optimize_allocation` simule `n_candidates + 1` portefeuilles complets (recherche
aléatoire + référence équipondérée) : à `_N_PATHS_INTERACTIVE`, le coût total (mesuré
à ~12 s pour 2 stratégies) est trop lent pour un endpoint interactif. Réduit ici
spécifiquement — la recherche de l'allocation optimale est de toute façon une
approximation par tirages aléatoires, pas un optimum exact (voir edgelab/portfolio/README.md)."""


class StrategyNotFoundError(RuntimeError):
    """Levée quand `strategy_id` ne correspond à aucun bundle connu."""


def _stable_seed(text: str) -> int:
    """Graine RNG déterministe dérivée de `text`.

    `hash()` intégré à Python est randomisé par processus (protection contre
    le déni de service par collision de hash) : deux exécutions du même
    script produiraient des chemins Monte Carlo différents. SHA-256 est
    stable d'une exécution à l'autre, ce qui rend un endpoint interactif
    reproductible pour les mêmes arguments.
    """
    digest = hashlib.sha256(text.encode()).hexdigest()
    return int(digest, 16) % (2**32)


@lru_cache(maxsize=1)
def _load_all_bundles() -> dict[str, StrategyBundle]:
    if not SEED_DATA_DIR.exists():
        logger.warning("aucun répertoire de bundles trouvé: %s", SEED_DATA_DIR)
        return {}
    bundles: dict[str, StrategyBundle] = {}
    for path in sorted(SEED_DATA_DIR.glob("*.json")):
        bundle = StrategyBundle.model_validate_json(path.read_text(encoding="utf-8"))
        bundles[bundle.strategy_id] = bundle
    return bundles


def list_bundles() -> list[StrategyBundle]:
    """Tous les bundles de stratégie connus, triés par identifiant pour un ordre stable."""
    return [b for _, b in sorted(_load_all_bundles().items())]


def get_bundle(strategy_id: str) -> StrategyBundle:
    """Le bundle complet d'une stratégie.

    Raises:
        StrategyNotFoundError: si `strategy_id` est inconnu.
    """
    bundles = _load_all_bundles()
    if strategy_id not in bundles:
        raise StrategyNotFoundError(f"stratégie inconnue : {strategy_id}")
    return bundles[strategy_id]


def leaderboard_rows() -> list[LeaderboardRow]:
    """Les lignes du leaderboard, dérivées des bundles. Tri par `p_pass` fait côté vue."""
    rows = []
    for bundle in list_bundles():
        returns = np.asarray(bundle.trade_r_multiples, dtype=np.float64)
        rows.append(
            LeaderboardRow(
                strategy_id=bundle.strategy_id,
                family=bundle.family,
                universe=bundle.universe,
                status=bundle.status,
                n_trades=len(bundle.trade_r_multiples),
                net_expectancy_bps=float(np.mean(returns)) * 10_000.0,
                t_stat=_t_stat_from_bundle(bundle),
                dsr=bundle.dsr.deflated_sharpe_ratio,
                pbo=bundle.pbo.probability_of_overfitting,
                p_pass=bundle.propsim.strategy.p_pass,
                delta_vs_baseline_p_pass=bundle.propsim.edge_contribution_p_pass,
                max_dd_p95=bundle.bootstrap_comparison.block_max_drawdown_p95,
                worst_day_p95=bundle.propsim.strategy.worst_day_pct_p95,
                worst_streak_p95=bundle.bootstrap_comparison.block_worst_streak_p95,
                win_rate=float(np.mean(returns > 0.0)),
                holdout_access_count=bundle.holdout_access_count,
                holdout_flagged=bundle.holdout_flagged,
            )
        )
    return rows


_MIN_OBSERVATIONS_FOR_T_STAT = 2


def _t_stat_from_bundle(bundle: StrategyBundle) -> float:
    returns = np.asarray(bundle.trade_r_multiples, dtype=np.float64)
    n = returns.size
    if n < _MIN_OBSERVATIONS_FOR_T_STAT:
        return 0.0
    sem = float(np.std(returns, ddof=1)) / float(np.sqrt(n))
    return float(np.mean(returns)) / sem if sem > 0.0 else 0.0


def registry_trials(strategy_id: str | None = None) -> list[Trial]:
    """Essais réels du registre (I1), filtrés par stratégie si fourni."""
    with TrialRepository(DEFAULT_REGISTRY_DB) as repo:
        trials = repo.list_trials()
    if strategy_id is not None:
        trials = [t for t in trials if t.strategy_id == strategy_id]
    return trials


def registry_trial_count() -> int:
    """Compteur global d'essais — l'entrée du DSR, affichée en évidence dans l'UI."""
    return len(registry_trials())


def holdout_access_count(strategy_id: str) -> int:
    """Compteur d'accès holdout permanent (I3), lu en direct depuis la lockbox."""
    with HoldoutLockbox(DEFAULT_LOCKBOX_DB) as lockbox:
        return lockbox.access_count(strategy_id)


@lru_cache(maxsize=1)
def _shipped_rulesets() -> dict[str, PropFirmRuleset]:
    return load_shipped_rulesets()


def get_ruleset(ruleset_id: str) -> PropFirmRuleset:
    """Ruleset prop firm par id de fichier (`ftmo`, `the5ers`, `fundingpips`, `topstep`).

    Raises:
        KeyError: si `ruleset_id` ne correspond à aucun fichier livré.
    """
    rulesets = _shipped_rulesets()
    if ruleset_id.lower() not in rulesets:
        raise KeyError(f"ruleset inconnu : {ruleset_id}")
    return rulesets[ruleset_id.lower()]


def list_rulesets() -> list[dict[str, object]]:
    """Rulesets livrés, pour peupler le sélecteur de la vue surface de risque.

    Les noms de palier varient d'une firme à l'autre (`challenge` chez FTMO,
    `combine` chez Topstep, `phase_1` chez The5ers/FundingPips) : ils sont
    listés explicitement, jamais supposés identiques.
    """
    return [
        {
            "id": ruleset_id,
            "firm_name": ruleset.firm_name,
            "ruleset_name": ruleset.ruleset_name,
            "is_verified": ruleset.is_verified,
            "phases": [p.name for p in ruleset.phases],
        }
        for ruleset_id, ruleset in sorted(_shipped_rulesets().items())
    ]


def run_risk_surface(
    strategy_id: str, ruleset_name: str, phase_name: str | None = None
) -> RiskSurfaceResult:
    """Recalcule la surface de risque pour un ruleset choisi par l'utilisateur (job trigger).

    Le bundle précalculé (`bundle.risk_surface`) sert de défaut rapide ; cet
    endpoint ne recalcule que lorsque l'utilisateur change explicitement de
    ruleset dans le sélecteur de la vue. `phase_name` par défaut sur le
    premier palier du ruleset — les noms de palier ne sont pas uniformes
    d'une firme à l'autre (voir `list_rulesets`).
    """
    bundle = get_bundle(strategy_id)
    ruleset = get_ruleset(ruleset_name)
    phase_name = phase_name or ruleset.phases[0].name
    returns = np.asarray(bundle.trade_r_multiples, dtype=np.float64)
    rng = np.random.default_rng(_stable_seed(f"{strategy_id}:{ruleset_name}"))
    return sweep_risk_surface(
        returns,
        ruleset=ruleset,
        phase_name=phase_name,
        risk_levels_pct=np.arange(0.0025, 0.0225, 0.0025),
        trades_per_day=2,
        max_days=180,
        n_paths=_N_PATHS_INTERACTIVE,
        rng=rng,
        block_size=DEFAULT_BLOCK_SIZE,
    )


def run_correlation(strategy_ids: list[str]) -> CorrelationMatrix:
    """Matrice de corrélation par trade entre les stratégies sélectionnées (job trigger)."""
    bundles = {sid: get_bundle(sid) for sid in strategy_ids}
    returns_by_strategy = _aligned_returns(bundles)
    return correlation_matrix_by_trade(returns_by_strategy)


def run_combination(
    strategy_ids: list[str],
    weights: dict[str, float],
    ruleset_name: str,
    phase_name: str | None = None,
) -> CombinationResult:
    """P(passage) du portefeuille, corrélation et contribution marginale (job trigger, I5)."""
    bundles = {sid: get_bundle(sid) for sid in strategy_ids}
    returns_by_strategy = _aligned_returns(bundles)
    ruleset = get_ruleset(ruleset_name)
    phase_name = phase_name or ruleset.phases[0].name
    rng = np.random.default_rng(_stable_seed(",".join(sorted(strategy_ids))))
    return explore_combination(
        returns_by_strategy,
        weights=weights,
        ruleset=ruleset,
        phase_name=phase_name,
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=180,
        n_paths=_N_PATHS_INTERACTIVE,
        rng=rng,
    )


def run_optimize_allocation(
    strategy_ids: list[str], ruleset_name: str, phase_name: str | None = None
) -> AllocationSearchResult:
    """Poids qui maximisent P(passage) du portefeuille — jamais le Sharpe (I5), job trigger."""
    bundles = {sid: get_bundle(sid) for sid in strategy_ids}
    returns_by_strategy = _aligned_returns(bundles)
    ruleset = get_ruleset(ruleset_name)
    phase_name = phase_name or ruleset.phases[0].name
    rng = np.random.default_rng(_stable_seed(f"optimize:{','.join(sorted(strategy_ids))}"))
    return optimize_allocation(
        returns_by_strategy,
        ruleset=ruleset,
        phase_name=phase_name,
        risk_per_trade_pct=0.01,
        trades_per_day=2,
        max_days=180,
        n_paths=_N_PATHS_OPTIMIZE,
        n_candidates=_N_CANDIDATES_OPTIMIZE,
        rng=rng,
    )


def _aligned_returns(bundles: dict[str, StrategyBundle]) -> dict[str, np.ndarray]:
    """Tronque à la longueur commune la plus courte (limite documentée de `edgelab.portfolio`)."""
    min_len = min(len(b.trade_r_multiples) for b in bundles.values())
    return {
        sid: np.asarray(b.trade_r_multiples[:min_len], dtype=np.float64)
        for sid, b in bundles.items()
    }


def _write_bundle(bundle: StrategyBundle) -> None:
    """Persiste un bundle en JSON. Utilisé uniquement par le script de seed."""
    SEED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = SEED_DATA_DIR / f"{bundle.strategy_id}.json"
    path.write_text(json.dumps(bundle.model_dump(mode="json"), indent=2, ensure_ascii=False))
    _load_all_bundles.cache_clear()
