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
from typing import Any

import polars as pl
import pytest
from edgelab.costs.models import CostModel, FixedSpreadCost, SlippageByOrderType
from edgelab.data.lockbox import HoldoutLockbox
from edgelab.data.manifest import DatasetPartition
from edgelab.data.store import DatasetStore
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
from edgelab.validation.kill_criteria import StrategyLifecycleRepository


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
