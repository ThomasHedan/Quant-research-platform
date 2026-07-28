"""Tests de edgelab.validation.kill_criteria (évaluation des critères de mort, Phase 4)."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from edgelab.strategies.models import HypothesisSheet, KillCriterion, StrategyStatus
from edgelab.validation.kill_criteria import (
    DeadParentNotDeadError,
    StrategyLifecycleRepository,
    UnknownStrategyError,
    evaluate_kill_criteria,
)


def test_evaluate_kill_criteria_not_triggered_when_metric_is_healthy(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une métrique au-dessus du seuil ne déclenche pas le critère (`less_than`)."""
    hypothesis = make_hypothesis()

    verdict = evaluate_kill_criteria(hypothesis, {"t_stat": 3.0})

    assert verdict.any_triggered is False
    assert verdict.criteria[0].measured_value == 3.0


def test_evaluate_kill_criteria_triggered_when_metric_breaches_threshold(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une métrique sous le seuil déclenche le critère (`less_than`)."""
    hypothesis = make_hypothesis()

    verdict = evaluate_kill_criteria(hypothesis, {"t_stat": 1.0})

    assert verdict.any_triggered is True
    assert verdict.criteria[0].triggered is True


def test_evaluate_kill_criteria_greater_than_comparison() -> None:
    """Le sens `greater_than` déclenche quand la métrique dépasse le seuil."""
    criterion = KillCriterion(
        name="drawdown trop profond",
        metric="max_drawdown",
        comparison="greater_than",
        threshold=0.2,
        recorded_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    hypothesis = HypothesisSheet(
        strategy_id="s1",
        economic_hypothesis="x",
        predicted_direction="both",
        predicted_amplitude_atr=0.5,
        predicted_hit_rate=0.5,
        predicted_horizon_bars=10,
        where_it_should_not_work="y",
        kill_criteria=(criterion,),
    )

    verdict = evaluate_kill_criteria(hypothesis, {"max_drawdown": 0.35})

    assert verdict.any_triggered is True


def test_evaluate_kill_criteria_missing_metric_is_not_triggered(
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une métrique absente ne tue pas la stratégie : le verdict le montre, il ne l'invente pas."""
    hypothesis = make_hypothesis()

    verdict = evaluate_kill_criteria(hypothesis, {})

    assert verdict.any_triggered is False
    assert verdict.criteria[0].measured_value is None


def test_register_hypothesis_starts_as_candidate(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une stratégie fraîchement enregistrée démarre au statut `candidate`."""
    lifecycle_repository.register_hypothesis(make_hypothesis())

    assert lifecycle_repository.status("orb-fade-v1") is StrategyStatus.CANDIDATE


def test_register_hypothesis_rejects_duplicate_strategy_id(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Un `strategy_id` déjà enregistré ne peut pas être réutilisé."""
    lifecycle_repository.register_hypothesis(make_hypothesis())

    with pytest.raises(UnknownStrategyError):
        lifecycle_repository.register_hypothesis(make_hypothesis())


def test_apply_verdict_marks_strategy_dead_when_triggered(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Un critère déclenché fait passer la stratégie à `dead`."""
    hypothesis = make_hypothesis()
    lifecycle_repository.register_hypothesis(hypothesis)
    verdict = evaluate_kill_criteria(hypothesis, {"t_stat": 0.5})

    status = lifecycle_repository.apply_verdict(verdict)

    assert status is StrategyStatus.DEAD
    assert lifecycle_repository.status("orb-fade-v1") is StrategyStatus.DEAD


def test_apply_verdict_leaves_strategy_candidate_when_not_triggered(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Aucun critère déclenché : la stratégie reste `candidate`."""
    hypothesis = make_hypothesis()
    lifecycle_repository.register_hypothesis(hypothesis)
    verdict = evaluate_kill_criteria(hypothesis, {"t_stat": 3.0})

    status = lifecycle_repository.apply_verdict(verdict)

    assert status is StrategyStatus.CANDIDATE


def test_dead_strategy_cannot_be_revived_by_a_later_healthy_verdict(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Critère d'acceptation Phase 4 : `dead` ne peut pas être remise en `candidate`."""
    hypothesis = make_hypothesis()
    lifecycle_repository.register_hypothesis(hypothesis)
    lifecycle_repository.apply_verdict(evaluate_kill_criteria(hypothesis, {"t_stat": 0.1}))
    assert lifecycle_repository.status("orb-fade-v1") is StrategyStatus.DEAD

    healthy_verdict = evaluate_kill_criteria(hypothesis, {"t_stat": 5.0})
    status = lifecycle_repository.apply_verdict(healthy_verdict)

    assert status is StrategyStatus.DEAD
    assert lifecycle_repository.status("orb-fade-v1") is StrategyStatus.DEAD


def test_dead_strategy_cannot_be_revived_via_raw_sql(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
    lifecycle_db_path: Path,
) -> None:
    """Le garde-fou tient même en SQL brut, via une connexion séparée (comme I1)."""
    hypothesis = make_hypothesis()
    lifecycle_repository.register_hypothesis(hypothesis)
    lifecycle_repository.apply_verdict(evaluate_kill_criteria(hypothesis, {"t_stat": 0.1}))

    with (
        sqlite3.connect(lifecycle_db_path) as raw_conn,
        pytest.raises(sqlite3.IntegrityError),
    ):
        raw_conn.execute(
            "UPDATE strategy_lifecycle SET status = 'candidate' WHERE strategy_id = ?",
            ("orb-fade-v1",),
        )


def test_apply_verdict_raises_for_unknown_strategy(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Appliquer un verdict à une stratégie jamais enregistrée lève une erreur explicite."""
    verdict = evaluate_kill_criteria(make_hypothesis(), {"t_stat": 0.1})

    with pytest.raises(UnknownStrategyError):
        lifecycle_repository.apply_verdict(verdict)


def test_retest_after_death_requires_a_dead_parent(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une nouvelle fiche ne peut se rattacher qu'à un parent effectivement mort."""
    parent = make_hypothesis(strategy_id="orb-fade-v1")
    lifecycle_repository.register_hypothesis(parent)  # reste "candidate"

    child = make_hypothesis(strategy_id="orb-fade-v2", parent_strategy_id="orb-fade-v1")
    with pytest.raises(DeadParentNotDeadError):
        lifecycle_repository.register_hypothesis(child)


def test_retest_after_death_preserves_lineage(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une nouvelle fiche rattachée à un parent mort est acceptée et la filiation reste lisible."""
    parent = make_hypothesis(strategy_id="orb-fade-v1")
    lifecycle_repository.register_hypothesis(parent)
    lifecycle_repository.apply_verdict(evaluate_kill_criteria(parent, {"t_stat": 0.1}))

    child = make_hypothesis(strategy_id="orb-fade-v2", parent_strategy_id="orb-fade-v1")
    lifecycle_repository.register_hypothesis(child)

    assert lifecycle_repository.status("orb-fade-v2") is StrategyStatus.CANDIDATE
    assert lifecycle_repository.lineage("orb-fade-v2") == ["orb-fade-v1", "orb-fade-v2"]


def test_register_hypothesis_rejects_unknown_parent(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Un parent référencé mais jamais enregistré est refusé."""
    child = make_hypothesis(strategy_id="orb-fade-v2", parent_strategy_id="does-not-exist")

    with pytest.raises(UnknownStrategyError):
        lifecycle_repository.register_hypothesis(child)


def test_lineage_of_an_unrelated_strategy_is_itself_alone(
    lifecycle_repository: StrategyLifecycleRepository,
    make_hypothesis: Callable[..., HypothesisSheet],
) -> None:
    """Une stratégie sans parent a une filiation réduite à elle-même."""
    lifecycle_repository.register_hypothesis(make_hypothesis())

    assert lifecycle_repository.lineage("orb-fade-v1") == ["orb-fade-v1"]
