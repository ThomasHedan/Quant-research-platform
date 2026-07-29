"""Fixtures et factories partagées entre tous les modules de test.

Convention du projet : exercer les vraies dépendances (SQLite `sqlite://`,
`tmp_path`, DuckDB en mémoire) plutôt que de mocker. Les fixtures ajoutées
ici doivent rester génériques ; les factories spécifiques à un module
vivent dans le `test_<module>.py` correspondant si elles ne sont utilisées
qu'une fois.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
import pytest
from edgelab.costs.models import CostModel, FixedSpreadCost, SlippageByOrderType
from edgelab.data.integrity import IntegrityReport
from edgelab.data.lockbox import HoldoutAccessRecord, HoldoutLockbox
from edgelab.data.manifest import DatasetManifest, DatasetPartition, DatasetStatus
from edgelab.data.selection import DatasetSelection, DataSplit
from edgelab.data.store import DatasetStore
from edgelab.papers.models import HypothesisDraftRequest, KillCriterionInput, PaperAnalysisRequest
from edgelab.papers.repository import PaperRepository
from edgelab.propsim.models import ChallengePhase, DrawdownBasis, DrawdownType, PropFirmRuleset
from edgelab.registry.models import Trial, TrialType
from edgelab.registry.repository import TrialRepository
from edgelab.strategies.models import HypothesisSheet, KillCriterion
from edgelab.universe import (
    FX_MAJORS,
    INDEX_FUTURES,
    AssetClass,
    Instrument,
    SessionCalendar,
    SessionWindow,
)
from edgelab.validation.kill_criteria import StrategyLifecycleRepository, evaluate_kill_criteria


@pytest.fixture
def registry_db_path(tmp_path: Path) -> Path:
    """Chemin d'un registre SQLite isolé pour un test."""
    return tmp_path / "registry.sqlite3"


@pytest.fixture
def trial_repository(registry_db_path: Path) -> Iterator[TrialRepository]:
    """Un `TrialRepository` adossé à un fichier SQLite temporaire."""
    with TrialRepository(registry_db_path) as repo:
        yield repo


@pytest.fixture
def make_trial() -> Callable[..., Trial]:
    """Factory produisant un `Trial` valide, personnalisable via overrides."""

    def _make_trial(**overrides: Any) -> Trial:
        defaults: dict[str, Any] = {
            "trial_type": TrialType.EVENT_STUDY,
            "strategy_id": "orb-fade-v1",
            "code_hash": "c0de" * 16,
            "params": {"horizon": 10},
            "params_hash": "params" * 10 + "abcd",
            "dataset_hash": "data" * 16,
            "lineage_hash": "1ineage" * 9 + "abc",
        }
        defaults.update(overrides)
        return Trial(**defaults)

    return _make_trial


@pytest.fixture
def lockbox_db_path(tmp_path: Path) -> Path:
    """Chemin d'une lockbox SQLite isolée pour un test."""
    return tmp_path / "lockbox.sqlite3"


@pytest.fixture
def lockbox(lockbox_db_path: Path) -> Iterator[HoldoutLockbox]:
    """Une `HoldoutLockbox` adossée à un fichier SQLite temporaire."""
    with HoldoutLockbox(lockbox_db_path) as box:
        yield box


@pytest.fixture
def eurusd() -> Instrument:
    """L'instrument EURUSD de l'univers `fx_majors`, calendrier + coûts inclus."""
    return FX_MAJORS.get("EURUSD")


@pytest.fixture
def es_future() -> Instrument:
    """L'instrument ES (E-mini S&P 500) de l'univers `index_futures`."""
    return INDEX_FUTURES.get("ES")


@pytest.fixture
def make_clean_bars() -> Callable[..., pl.DataFrame]:
    """Factory produisant des barres OHLCV propres, alignées sur un calendrier de session.

    Les horodatages sont ceux attendus par `SessionCalendar.expected_bar_starts`,
    donc le résultat passe le contrôle d'intégrité par construction — les
    tests qui veulent un dataset défaillant retirent ou dupliquent des lignes
    à partir de là plutôt que de construire leurs propres horodatages.
    """

    def _make_clean_bars(
        instrument: Instrument,
        *,
        start: datetime,
        end: datetime,
        frequency: timedelta,
        base_price: float = 1.10,
        seed: int = 0,
    ) -> pl.DataFrame:
        rng = random.Random(seed)
        timestamps = instrument.session_calendar.expected_bar_starts(start, end, frequency)
        price = base_price
        rows = []
        for ts in timestamps:
            price += rng.gauss(0, base_price * 1e-4)
            high = price + abs(rng.gauss(0, 1e-5))
            low = price - abs(rng.gauss(0, 1e-5))
            rows.append((ts, price, high, low, price, 100.0))
        return pl.DataFrame(
            rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
        )

    return _make_clean_bars


@pytest.fixture
def make_partition() -> Callable[..., DatasetPartition]:
    """Factory produisant un `DatasetPartition` valide à partir de bornes explicites."""

    def _make_partition(research_end: datetime, validation_end: datetime) -> DatasetPartition:
        return DatasetPartition(research_end=research_end, validation_end=validation_end)

    return _make_partition


@pytest.fixture
def dataset_store(tmp_path: Path) -> Iterator[DatasetStore]:
    """Un `DatasetStore` (catalogue DuckDB + Parquet) adossé à un répertoire temporaire."""
    with DatasetStore(tmp_path / "catalog.duckdb", tmp_path / "bars") as store:
        yield store


@pytest.fixture
def make_research_instrument() -> Callable[..., Instrument]:
    """Factory produisant un instrument minimal pour les tests d'event study.

    Le calendrier de session n'est pas consulté par le calcul d'event study
    (qui opère directement sur les barres fournies) ; il doit seulement être
    valide pour construire l'`Instrument`. Coût nul par défaut pour isoler
    la mesure du signal de tout biais de coût dans les tests de récupération
    d'amplitude.
    """
    calendar = SessionCalendar(
        timezone="UTC",
        windows=tuple(
            SessionWindow(weekday=d, open=time(0, 0), close=time(0, 0)) for d in range(7)
        ),
    )

    def _make(symbol: str, cost_model: CostModel | None = None) -> Instrument:
        return Instrument(
            symbol=symbol,
            name=symbol,
            asset_class=AssetClass.FX,
            session_calendar=calendar,
            cost_model=cost_model
            or FixedSpreadCost(spread=0.0, commission=0.0, slippage=SlippageByOrderType()),
            price_decimals=5,
            pip_size=0.0001,
        )

    return _make


@pytest.fixture
def make_bar_frame() -> Callable[..., pl.DataFrame]:
    """Factory produisant des barres OHLCV horaires continues à partir d'une liste de clôtures.

    `open[i] = close[i-1]` (série sans gap) : les tests de backtest qui ont
    besoin de fills prévisibles au centime près construisent leurs clôtures
    à la main plutôt que de dépendre d'un générateur aléatoire.
    """

    def _make(
        closes: list[float],
        *,
        start: datetime = datetime(2024, 1, 1, tzinfo=UTC),
        wick: float = 0.01,
    ) -> pl.DataFrame:
        rows = []
        for i, close in enumerate(closes):
            open_ = closes[i - 1] if i > 0 else close
            high = max(open_, close) + wick
            low = min(open_, close) - wick
            rows.append((start + timedelta(hours=i), open_, high, low, close, 100.0))
        return pl.DataFrame(
            rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
        )

    return _make


@pytest.fixture
def wrap_selection() -> Callable[..., DatasetSelection]:
    """Factory emballant des barres déjà construites dans une `DatasetSelection`.

    Le moteur de backtest n'accepte plus de DataFrame nu : passer par une
    sélection est ce qui prouve que la quarantaine a été vérifiée et que le
    holdout, le cas échéant, a été journalisé (I3). Les bornes de partition
    sont calées pour que toutes les barres tombent dans le split demandé.
    """

    def _make(
        bars: pl.DataFrame,
        *,
        split: DataSplit = DataSplit.RESEARCH,
        instrument_symbol: str = "EURUSD",
        status: DatasetStatus = DatasetStatus.OK,
    ) -> DatasetSelection:
        start = cast(datetime, bars["timestamp"].min())
        end = cast(datetime, bars["timestamp"].max())
        far_past = start - timedelta(days=1)
        far_future = end + timedelta(days=1)
        match split:
            case DataSplit.RESEARCH:
                partition = DatasetPartition(
                    research_end=far_future, validation_end=far_future + timedelta(days=1)
                )
            case DataSplit.VALIDATION:
                partition = DatasetPartition(research_end=far_past, validation_end=far_future)
            case DataSplit.HOLDOUT:
                partition = DatasetPartition(
                    research_end=far_past, validation_end=far_past + timedelta(hours=1)
                )
        manifest = DatasetManifest(
            dataset_id=f"ds-{instrument_symbol}-{split.value}",
            instrument_symbol=instrument_symbol,
            source="synthetic",
            start=start,
            end=end,
            timezone="UTC",
            roll_method=None,
            partition=partition,
            integrity_report=IntegrityReport(issues=()),
            status=status,
            manifest_hash="0" * 64,
        )
        access = (
            HoldoutAccessRecord(strategy_id="test", reason="fixture", accessed_at=datetime.now(UTC))
            if split is DataSplit.HOLDOUT
            else None
        )
        return DatasetSelection(manifest=manifest, split=split, bars=bars, holdout_access=access)

    return _make


@pytest.fixture
def make_selection(
    make_bar_frame: Callable[..., pl.DataFrame],
    wrap_selection: Callable[..., DatasetSelection],
) -> Callable[..., DatasetSelection]:
    """Factory produisant une `DatasetSelection` à partir d'une liste de clôtures."""

    def _make(
        closes: list[float],
        *,
        split: DataSplit = DataSplit.RESEARCH,
        instrument_symbol: str = "EURUSD",
        status: DatasetStatus = DatasetStatus.OK,
        **bar_kwargs: object,
    ) -> DatasetSelection:
        return wrap_selection(
            make_bar_frame(closes, **bar_kwargs),
            split=split,
            instrument_symbol=instrument_symbol,
            status=status,
        )

    return _make


@pytest.fixture
def make_hypothesis() -> Callable[..., HypothesisSheet]:
    """Factory produisant une `HypothesisSheet` (I2) valide, personnalisable via overrides."""

    def _make(**overrides: Any) -> HypothesisSheet:
        defaults: dict[str, Any] = {
            "strategy_id": "orb-fade-v1",
            "economic_hypothesis": "Les mèches d'ouverture asiatique fadent en session londonienne",
            "predicted_direction": "both",
            "predicted_amplitude_atr": 0.5,
            "predicted_hit_rate": 0.55,
            "predicted_horizon_bars": 20,
            "where_it_should_not_work": "En période de forte tendance directionnelle (ADX > 30)",
            "kill_criteria": (
                KillCriterion(
                    name="t-stat trop faible",
                    metric="t_stat",
                    comparison="less_than",
                    threshold=2.0,
                    recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
                ),
            ),
        }
        defaults.update(overrides)
        return HypothesisSheet(**defaults)

    return _make


@pytest.fixture
def lifecycle_db_path(tmp_path: Path) -> Path:
    """Chemin d'un registre de cycle de vie de stratégies SQLite isolé pour un test."""
    return tmp_path / "lifecycle.sqlite3"


@pytest.fixture
def lifecycle_repository(lifecycle_db_path: Path) -> Iterator[StrategyLifecycleRepository]:
    """Un `StrategyLifecycleRepository` adossé à un fichier SQLite temporaire."""
    with StrategyLifecycleRepository(lifecycle_db_path) as repo:
        yield repo


@pytest.fixture
def make_phase() -> Callable[..., ChallengePhase]:
    """Factory produisant un `ChallengePhase` valide, personnalisable via overrides."""

    def _make(**overrides: Any) -> ChallengePhase:
        defaults: dict[str, Any] = {
            "name": "challenge",
            "profit_target_pct": 0.10,
            "max_daily_loss_pct": 0.05,
            "max_drawdown_pct": 0.10,
            "drawdown_type": DrawdownType.STATIC,
            "drawdown_basis": DrawdownBasis.BALANCE,
            "min_trading_days": 4,
            "max_duration_days": None,
        }
        defaults.update(overrides)
        return ChallengePhase(**defaults)

    return _make


@pytest.fixture
def make_ruleset(make_phase: Callable[..., ChallengePhase]) -> Callable[..., PropFirmRuleset]:
    """Factory produisant un `PropFirmRuleset` à un seul palier, personnalisable via overrides."""

    def _make(**overrides: Any) -> PropFirmRuleset:
        phase_overrides = overrides.pop("phase_overrides", {})
        defaults: dict[str, Any] = {
            "firm_name": "TestFirm",
            "ruleset_name": "Test Ruleset",
            "phases": (make_phase(**phase_overrides),),
        }
        defaults.update(overrides)
        return PropFirmRuleset(**defaults)

    return _make


@pytest.fixture
def positive_edge_trades() -> np.ndarray:
    """100 trades en multiples de R à edge positif net (45 % à +2R, 55 % à -1R, mean=0.35)."""
    trades = np.concatenate([np.full(45, 2.0), np.full(55, -1.0)])
    np.random.default_rng(3).shuffle(trades)
    return trades


@pytest.fixture
def make_edge_trades() -> Callable[[int], np.ndarray]:
    """Factory produisant 100 trades au même edge net (45 % à +2R, 55 % à -1R) mais mélangés
    indépendamment par graine — deux appels avec des graines différentes produisent des
    séries au même edge mais décorrélées ; la même graine reproduit `positive_edge_trades`."""

    def _make(seed: int) -> np.ndarray:
        trades = np.concatenate([np.full(45, 2.0), np.full(55, -1.0)])
        np.random.default_rng(seed).shuffle(trades)
        return trades

    return _make


@pytest.fixture
def make_strategy_bundle(
    make_hypothesis: Callable[..., HypothesisSheet],
    make_ruleset: Callable[..., PropFirmRuleset],
    trial_repository: TrialRepository,
) -> Callable[..., Any]:
    """Factory produisant un `StrategyBundle` (Phase 8) réel, calculé sur `returns` fournis.

    Chaque champ est produit par les vraies fonctions de `edgelab.validation` /
    `edgelab.propsim`, avec de petits `n_paths` pour rester rapide — jamais des
    valeurs inventées à la main.
    """
    from edgelab.api.schemas import (
        ConfidenceInterval,
        InstrumentBreakdown,
        MonteCarloFan,
        NaiveComparison,
        StrategyBundle,
        SubperiodPoint,
        VolRegimePoint,
    )
    from edgelab.propsim.baseline import simulate_with_baseline
    from edgelab.propsim.risk_surface import sweep_risk_surface
    from edgelab.strategies.models import StrategyStatus
    from edgelab.validation.bootstrap import block_bootstrap_paths, compare_block_vs_iid_bootstrap
    from edgelab.validation.costs_stress import costs_stress_test
    from edgelab.validation.dsr import deflated_sharpe_ratio_from_registry
    from edgelab.validation.pbo import probability_of_backtest_overfitting
    from edgelab.validation.permutation import permutation_test
    from edgelab.validation.start_date_sensitivity import start_date_sensitivity
    from edgelab.validation.walk_forward import walk_forward

    def _ci(values: np.ndarray) -> ConfidenceInterval:
        mean = float(np.mean(values))
        sem = (
            float(np.std(values, ddof=1)) / float(np.sqrt(values.size)) if values.size > 1 else 0.0
        )
        return ConfidenceInterval(
            mean=mean, ci_low=mean - 1.96 * sem, ci_high=mean + 1.96 * sem, n=values.size
        )

    def _make(
        *, strategy_id: str = "orb-fade-v1", returns: np.ndarray | None = None, seed: int = 7
    ) -> Any:
        rng = np.random.default_rng(seed)
        r = returns if returns is not None else rng.normal(0.3, 1.0, 100)
        param_grid = {"a": r, "b": rng.normal(0.0, 1.0, r.size)}

        permutation = permutation_test(r, n_permutations=200, rng=rng)
        walk_fwd = walk_forward(param_grid, in_sample_size=40, out_of_sample_size=20)
        pbo = probability_of_backtest_overfitting(param_grid, n_partitions=4)
        # Le DSR lit un compteur d'essais réel (I1) : au moins un essai doit exister avant
        # de le calculer, sans quoi `deflated_sharpe_ratio_from_registry` refuse (n_trials=0).
        trial_repository.record(
            Trial(
                id=f"{strategy_id}__seed__{rng.integers(0, 2**31)}",
                trial_type=TrialType.BACKTEST,
                strategy_id=strategy_id,
                code_hash="c0de" * 16,
                params={},
                params_hash="params" * 10 + "abcd",
                dataset_hash="data" * 16,
                lineage_hash="1ineage" * 9 + "abc",
            )
        )
        dsr = deflated_sharpe_ratio_from_registry(r, repository=trial_repository)
        hypothesis = make_hypothesis(strategy_id=strategy_id)
        verdict = evaluate_kill_criteria(hypothesis, {"t_stat": 3.0})
        ruleset = make_ruleset()
        propsim = simulate_with_baseline(
            r,
            ruleset=ruleset,
            phase_name="challenge",
            risk_per_trade_pct=0.01,
            trades_per_day=2,
            max_days=60,
            n_paths=200,
            rng=rng,
        )
        risk_surface = sweep_risk_surface(
            r,
            ruleset=ruleset,
            phase_name="challenge",
            risk_levels_pct=np.array([0.005, 0.01]),
            trades_per_day=2,
            max_days=60,
            n_paths=100,
            rng=rng,
        )
        fan_paths = block_bootstrap_paths(r, block_size=5, n_resamples=50, rng=rng)
        fan_equity = np.cumsum(fan_paths, axis=1)
        return StrategyBundle(
            strategy_id=strategy_id,
            family="Test",
            universe="fx_majors",
            status=StrategyStatus.CANDIDATE,
            lineage=(strategy_id,),
            hypothesis=hypothesis,
            kill_criteria_verdict=verdict,
            trade_r_multiples=tuple(r.tolist()),
            equity_curve=tuple(np.cumsum(r).tolist()),
            mae_mfe_mean_mae=0.4,
            mae_mfe_mean_mfe=0.6,
            subperiod_stats=(SubperiodPoint(label="T1", stats=_ci(r), t_stat=1.0),),
            vol_regime_stats=(VolRegimePoint(tercile="low", stats=_ci(r), t_stat=1.0),),
            naive_comparison=NaiveComparison(
                triggered=_ci(r),
                naive=_ci(r * 0.1),
                mean_diff=0.1,
                p_value=0.2,
                improves_on_naive=True,
            ),
            instrument_breakdown=(
                InstrumentBreakdown(symbol="EURUSD", stats=_ci(r), t_stat=1.0, hit_rate=0.5),
            ),
            monte_carlo_fan=MonteCarloFan(
                trade_index=tuple(range(r.size)),
                p10=tuple(np.quantile(fan_equity, 0.1, axis=0).tolist()),
                p50=tuple(np.quantile(fan_equity, 0.5, axis=0).tolist()),
                p90=tuple(np.quantile(fan_equity, 0.9, axis=0).tolist()),
            ),
            bootstrap_comparison=compare_block_vs_iid_bootstrap(
                r, block_size=5, n_resamples=100, rng=rng
            ),
            permutation=permutation,
            walk_forward=walk_fwd,
            dsr=dsr,
            pbo=pbo,
            start_date_sensitivity=start_date_sensitivity(r, n_start_dates=30, window_length=50),
            costs_stress=costs_stress_test(r, 0.05),
            propsim=propsim,
            risk_surface=risk_surface,
            ruleset_name="test",
            holdout_access_count=0,
            holdout_flagged=False,
        )

    return _make


@pytest.fixture
def papers_db_path(tmp_path: Path) -> Path:
    """Chemin d'un stockage papiers SQLite isolé pour un test."""
    return tmp_path / "papers.sqlite3"


@pytest.fixture
def paper_repository(papers_db_path: Path) -> Iterator[PaperRepository]:
    """Un `PaperRepository` adossé à un fichier SQLite temporaire."""
    with PaperRepository(papers_db_path) as repo:
        yield repo


@pytest.fixture
def make_paper_analysis_request() -> Callable[..., PaperAnalysisRequest]:
    """Factory produisant un `PaperAnalysisRequest` valide, personnalisable via overrides."""

    def _make(**overrides: Any) -> PaperAnalysisRequest:
        defaults: dict[str, Any] = {
            "title": "Momentum Crashes in Chinese Commodity Futures",
            "authors": ("Wei Zhang", "Li Chen"),
            "publication_year": 2016,
            "language_source": "zh",
            "venue": "Journal of Futures Markets",
            "anomaly_family": "momentum",
            "asset_class": "futures matières premières",
            "frequency": "quotidien",
            "sample_period": "2005-2014",
            "claimed_sharpe_or_hit_rate": "Sharpe 1.2 sur le portefeuille long-short",
            "costs_considered": "partiel",
            "economic_hypothesis": "Les futures chinoises sous-réagissent au flux d'ordre.",
            "data_needed": "Prix quotidiens Dalian et Shanghai Futures Exchange",
            "replication_difficulty": "moyenne",
            "instrument_available_at_prop_firms": False,
            "data_accessible": True,
            "mechanizable_without_discretion": True,
        }
        defaults.update(overrides)
        return PaperAnalysisRequest(**defaults)

    return _make


@pytest.fixture
def make_hypothesis_draft_request() -> Callable[..., HypothesisDraftRequest]:
    """Factory produisant un `HypothesisDraftRequest` valide, personnalisable via overrides."""

    def _make(**overrides: Any) -> HypothesisDraftRequest:
        defaults: dict[str, Any] = {
            "economic_hypothesis": "Un signal de flux d'ordre à 5 jours prédit une continuation.",
            "predicted_direction": "long",
            "predicted_amplitude_atr": 0.4,
            "predicted_hit_rate": 0.53,
            "predicted_horizon_bars": 10,
            "where_it_should_not_work": "Hors des trois contrats les plus liquides.",
            "kill_criteria": (
                KillCriterionInput(
                    name="edge non significatif",
                    metric="t_stat",
                    comparison="less_than",
                    threshold=2.0,
                ),
            ),
            "strategy_code_skeleton": "def signal(bar_window):\n    return False\n",
        }
        defaults.update(overrides)
        return HypothesisDraftRequest(**defaults)

    return _make
