"""Tests de edgelab.api.store (Phase 8)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from edgelab.api import store
from edgelab.data.lockbox import HoldoutLockbox
from edgelab.papers.models import TriageStatus
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isole chaque test : répertoire de bundles, registre, lockbox et papiers dédiés."""
    monkeypatch.setattr(store, "SEED_DATA_DIR", tmp_path / "strategies")
    monkeypatch.setattr(store, "DEFAULT_REGISTRY_DB", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_LOCKBOX_DB", tmp_path / "lockbox.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_PAPERS_DB", tmp_path / "papers.sqlite3")
    store._load_all_bundles.cache_clear()
    store._shipped_rulesets.cache_clear()
    yield
    store._load_all_bundles.cache_clear()
    store._shipped_rulesets.cache_clear()


def test_list_bundles_is_empty_when_no_seed_directory_exists() -> None:
    """Sans répertoire de seed, la liste des bundles est vide plutôt qu'une erreur."""
    assert store.list_bundles() == []


def test_write_bundle_then_get_roundtrips(make_strategy_bundle: Callable[..., Any]) -> None:
    """Un bundle écrit par `_write_bundle` est relu à l'identique par `get_bundle`."""
    bundle = make_strategy_bundle(strategy_id="demo-a")

    store._write_bundle(bundle)

    assert store.get_bundle("demo-a").strategy_id == "demo-a"


def test_get_bundle_raises_for_unknown_strategy() -> None:
    """Un `strategy_id` inconnu lève `StrategyNotFoundError`, pas un accès silencieux."""
    with pytest.raises(store.StrategyNotFoundError):
        store.get_bundle("nope")


def test_leaderboard_rows_derive_from_written_bundles(
    make_strategy_bundle: Callable[..., Any],
) -> None:
    """Chaque bundle produit exactement une ligne de leaderboard, cohérente avec ses données."""
    bundle = make_strategy_bundle(strategy_id="demo-a")
    store._write_bundle(bundle)

    rows = store.leaderboard_rows()

    assert len(rows) == 1
    assert rows[0].strategy_id == "demo-a"
    assert rows[0].n_trades == len(bundle.trade_r_multiples)
    assert 0.0 <= rows[0].win_rate <= 1.0


def test_registry_trials_filters_by_strategy_id(make_trial: Callable[..., Trial]) -> None:
    """`registry_trials(strategy_id=...)` ne renvoie que les essais de cette stratégie."""
    with TrialRepository(store.DEFAULT_REGISTRY_DB) as repo:
        repo.record(make_trial(id="t1", strategy_id="a"))
        repo.record(make_trial(id="t2", strategy_id="b"))

    assert [t.id for t in store.registry_trials("a")] == ["t1"]
    assert store.registry_trial_count() == 2


def test_holdout_access_count_reads_the_live_lockbox() -> None:
    """Le compteur d'accès holdout reflète la lockbox réelle, pas un artefact figé."""
    with HoldoutLockbox(store.DEFAULT_LOCKBOX_DB) as box:
        box.access("demo-a", "vérification avant abandon")
        box.access("demo-a", "seconde vérification")

    assert store.holdout_access_count("demo-a") == 2


def test_get_ruleset_raises_key_error_for_unknown_id() -> None:
    """Un identifiant de ruleset inconnu lève `KeyError`, jamais un ruleset par défaut deviné."""
    with pytest.raises(KeyError):
        store.get_ruleset("does-not-exist")


def test_list_rulesets_includes_the_four_shipped_rulesets() -> None:
    """Les quatre rulesets livrés (Phase 5) apparaissent, chacun avec son statut de vérification."""
    rulesets = store.list_rulesets()

    assert {r["id"] for r in rulesets} == {"ftmo", "the5ers", "fundingpips", "topstep"}
    ftmo = next(r for r in rulesets if r["id"] == "ftmo")
    assert ftmo["is_verified"] is True


def test_run_correlation_between_two_bundles(make_strategy_bundle: Callable[..., Any]) -> None:
    """La corrélation par trade entre deux stratégies sélectionnées se calcule en direct."""
    rng = np.random.default_rng(1)
    store._write_bundle(make_strategy_bundle(strategy_id="a", returns=rng.normal(0.2, 1.0, 100)))
    store._write_bundle(make_strategy_bundle(strategy_id="b", returns=rng.normal(0.2, 1.0, 100)))

    matrix = store.run_correlation(["a", "b"])

    assert matrix.strategy_ids == ("a", "b")
    assert matrix.correlation("a", "a") == pytest.approx(1.0)


def test_run_combination_returns_a_joint_p_pass(make_strategy_bundle: Callable[..., Any]) -> None:
    """La combinaison de portefeuille délègue à `edgelab.portfolio` sans dupliquer sa mécanique."""
    rng = np.random.default_rng(2)
    store._write_bundle(make_strategy_bundle(strategy_id="a", returns=rng.normal(0.3, 1.0, 100)))
    store._write_bundle(make_strategy_bundle(strategy_id="b", returns=rng.normal(0.3, 1.0, 100)))

    result = store.run_combination(["a", "b"], {"a": 0.5, "b": 0.5}, "ftmo", "challenge")

    assert 0.0 <= result.portfolio.p_pass <= 1.0
    assert {m.strategy_id for m in result.marginal_contributions} == {"a", "b"}


def test_run_optimize_allocation_returns_weights_summing_to_one(
    make_strategy_bundle: Callable[..., Any],
) -> None:
    """L'allocation optimale délègue à `edgelab.portfolio.optimize_allocation` (I5)."""
    rng = np.random.default_rng(3)
    store._write_bundle(make_strategy_bundle(strategy_id="a", returns=rng.normal(0.3, 1.0, 100)))
    store._write_bundle(make_strategy_bundle(strategy_id="b", returns=rng.normal(0.3, 1.0, 100)))

    result = store.run_optimize_allocation(["a", "b"], "ftmo")

    assert result.weights.keys() == {"a", "b"}
    assert sum(result.weights.values()) == pytest.approx(1.0)


def test_run_risk_surface_recomputes_for_a_chosen_ruleset(
    make_strategy_bundle: Callable[..., Any],
) -> None:
    """Choisir un ruleset relance `sweep_risk_surface` sur les rendements de la stratégie."""
    store._write_bundle(make_strategy_bundle(strategy_id="a"))

    result = store.run_risk_surface("a", "topstep")

    assert len(result.points) > 0


def test_list_papers_is_empty_on_a_fresh_store() -> None:
    """Aucun papier créé : liste vide, pas d'erreur."""
    assert store.list_papers() == []


def test_create_paper_then_list_papers_roundtrips(
    make_paper_analysis_request: Callable[..., Any],
) -> None:
    """Un papier créé via le déclencheur d'écriture apparaît dans la liste."""
    store.create_paper(make_paper_analysis_request(title="Titre API"))

    records = store.list_papers()

    assert [r.sheet.title for r in records] == ["Titre API"]


def test_get_paper_raises_for_an_unknown_id() -> None:
    """`get_paper` échoue explicitement plutôt que de renvoyer `None` en silence."""
    with pytest.raises(store.PaperNotFoundError):
        store.get_paper("does-not-exist")


def test_attach_paper_hypothesis_advances_status(
    make_paper_analysis_request: Callable[..., Any],
    make_hypothesis_draft_request: Callable[..., Any],
) -> None:
    """Rattacher un brouillon d'hypothèse fait avancer le statut de triage."""
    created = store.create_paper(make_paper_analysis_request())

    updated = store.attach_paper_hypothesis(created.sheet.id, make_hypothesis_draft_request())

    assert updated.status.value == "hypothese_ecrite"


def test_set_paper_status_mort_without_reason_raises(
    make_paper_analysis_request: Callable[..., Any],
) -> None:
    """Le déclencheur d'écriture porte la même règle que le repository : motif obligatoire."""
    created = store.create_paper(make_paper_analysis_request())

    with pytest.raises(store.PaperRepositoryError):
        store.set_paper_status(created.sheet.id, TriageStatus.MORT)


def test_paper_analysis_prompt_mentions_the_json_contract() -> None:
    """Le prompt statique documente le schéma JSON attendu."""
    assert "language_source" in store.paper_analysis_prompt()


def test_paper_hypothesis_prompt_embeds_the_paper_title(
    make_paper_analysis_request: Callable[..., Any],
) -> None:
    """Le prompt personnalisé embarque la fiche du papier concerné."""
    created = store.create_paper(make_paper_analysis_request(title="Titre Unique Prompt"))

    prompt = store.paper_hypothesis_prompt(created.sheet.id)

    assert "Titre Unique Prompt" in prompt


def test_paper_hypothesis_prompt_raises_for_an_unknown_paper() -> None:
    """Demander un prompt pour un papier inconnu échoue explicitement."""
    with pytest.raises(store.PaperNotFoundError):
        store.paper_hypothesis_prompt("does-not-exist")
