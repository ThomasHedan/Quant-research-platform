"""Tests de edgelab.api.main (Phase 8) : l'API HTTP en lecture seule."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from edgelab.api import store
from edgelab.api.main import app
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isole chaque test : répertoire de bundles, registre et lockbox dédiés, cache vidé."""
    monkeypatch.setattr(store, "SEED_DATA_DIR", tmp_path / "strategies")
    monkeypatch.setattr(store, "DEFAULT_REGISTRY_DB", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_LOCKBOX_DB", tmp_path / "lockbox.sqlite3")
    store._load_all_bundles.cache_clear()
    yield
    store._load_all_bundles.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Client HTTP synchrone contre l'app FastAPI, sans serveur réel."""
    return TestClient(app)


def test_health_check_reports_ok(client: TestClient) -> None:
    """La sonde de vie répond `ok` sans dépendre d'aucun artefact."""
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_strategies_reflects_written_bundles(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """Le leaderboard reflète les bundles présents sur disque, aucun de plus."""
    store._write_bundle(make_strategy_bundle(strategy_id="demo-a"))

    response = client.get("/api/strategies")

    assert response.status_code == 200
    assert [row["strategy_id"] for row in response.json()] == ["demo-a"]


def test_get_strategy_returns_the_full_bundle(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """La fiche stratégie complète est servie telle quelle, artefact réel."""
    store._write_bundle(make_strategy_bundle(strategy_id="demo-a"))

    response = client.get("/api/strategies/demo-a")

    assert response.status_code == 200
    assert response.json()["strategy_id"] == "demo-a"
    assert "kill_criteria_verdict" in response.json()


def test_get_strategy_404s_for_an_unknown_id(client: TestClient) -> None:
    """Une stratégie inconnue renvoie 404, jamais un bundle vide silencieux."""
    response = client.get("/api/strategies/does-not-exist")

    assert response.status_code == 404


def test_list_trials_and_count_read_the_real_registry(
    client: TestClient, make_trial: Callable[..., Trial]
) -> None:
    """Le journal d'essais et son compteur global lisent le registre réel (I1)."""
    with TrialRepository(store.DEFAULT_REGISTRY_DB) as repo:
        repo.record(make_trial(id="t1", strategy_id="demo-a"))
        repo.record(make_trial(id="t2", strategy_id="demo-b"))

    assert len(client.get("/api/trials").json()) == 2
    assert client.get("/api/trials/count").json() == {"count": 2}
    assert client.get("/api/trials/t1").json()["id"] == "t1"


def test_get_trial_404s_for_an_unknown_id(client: TestClient) -> None:
    """Un essai inconnu renvoie 404 plutôt qu'un 500 ou un objet vide."""
    assert client.get("/api/trials/does-not-exist").status_code == 404


def test_get_strategy_trials_filters_by_strategy(
    client: TestClient, make_trial: Callable[..., Trial]
) -> None:
    """Le journal lié à une fiche stratégie ne montre que ses propres essais."""
    with TrialRepository(store.DEFAULT_REGISTRY_DB) as repo:
        repo.record(make_trial(id="t1", strategy_id="demo-a"))
        repo.record(make_trial(id="t2", strategy_id="demo-b"))

    response = client.get("/api/strategies/demo-a/trials")

    assert [t["id"] for t in response.json()] == ["t1"]


def test_list_rulesets_exposes_verification_status(client: TestClient) -> None:
    """Le sélecteur de ruleset reçoit le statut `is_verified` de chaque firme."""
    rulesets = client.get("/api/rulesets").json()

    assert any(r["id"] == "ftmo" and r["is_verified"] for r in rulesets)


def test_get_risk_surface_returns_the_precomputed_artifact_by_default(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """Sans `ruleset`, la surface de risque servie est l'artefact précalculé du bundle."""
    bundle = make_strategy_bundle(strategy_id="demo-a")
    store._write_bundle(bundle)

    response = client.get("/api/strategies/demo-a/risk-surface")

    assert response.status_code == 200
    assert response.json()["points"] == [
        p.model_dump(mode="json") for p in bundle.risk_surface.points
    ]


def test_get_risk_surface_recomputes_for_a_different_ruleset(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """Choisir un ruleset différent du bundle relance le calcul (job trigger)."""
    store._write_bundle(make_strategy_bundle(strategy_id="demo-a"))

    response = client.get("/api/strategies/demo-a/risk-surface", params={"ruleset": "topstep"})

    assert response.status_code == 200
    assert len(response.json()["points"]) > 0


def test_get_risk_surface_404s_for_an_unknown_strategy(client: TestClient) -> None:
    """Une surface de risque pour une stratégie inconnue renvoie 404."""
    assert client.get("/api/strategies/nope/risk-surface").status_code == 404


def test_get_risk_surface_404s_for_an_unknown_ruleset(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """Un ruleset inconnu renvoie 404, jamais un ruleset par défaut deviné silencieusement."""
    store._write_bundle(make_strategy_bundle(strategy_id="demo-a"))

    response = client.get(
        "/api/strategies/demo-a/risk-surface", params={"ruleset": "does-not-exist"}
    )

    assert response.status_code == 404


def test_portfolio_correlation_requires_at_least_two_strategies(client: TestClient) -> None:
    """Sélectionner une seule stratégie pour une matrice de corrélation est une erreur 400."""
    response = client.get("/api/portfolio/correlation", params={"strategy_ids": ["a"]})

    assert response.status_code == 400


def test_portfolio_correlation_returns_a_matrix_for_two_strategies(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """La matrice de corrélation par trade se calcule pour deux stratégies sélectionnées."""
    rng = np.random.default_rng(9)
    store._write_bundle(make_strategy_bundle(strategy_id="a", returns=rng.normal(0.2, 1.0, 100)))
    store._write_bundle(make_strategy_bundle(strategy_id="b", returns=rng.normal(0.2, 1.0, 100)))

    response = client.get("/api/portfolio/correlation", params={"strategy_ids": ["a", "b"]})

    assert response.status_code == 200
    assert response.json()["strategy_ids"] == ["a", "b"]


def test_portfolio_combination_404s_for_an_unknown_strategy(client: TestClient) -> None:
    """Combiner une stratégie inconnue renvoie 404, jamais un portefeuille partiel silencieux."""
    response = client.get("/api/portfolio/combination", params={"strategy_ids": ["nope"]})

    assert response.status_code == 404


def test_portfolio_combination_400s_for_a_single_known_strategy(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """Une seule stratégie connue renvoie 400 (400, pas un 500 non géré) : la contribution
    marginale se mesure par exclusion, ce qui n'a pas de sens à N=1."""
    store._write_bundle(make_strategy_bundle(strategy_id="a"))

    response = client.get("/api/portfolio/combination", params={"strategy_ids": ["a"]})

    assert response.status_code == 400


def test_portfolio_combination_returns_marginal_contributions(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """L'explorateur de combinaisons renvoie P(passage) du portefeuille et sa décomposition."""
    rng = np.random.default_rng(5)
    store._write_bundle(make_strategy_bundle(strategy_id="a", returns=rng.normal(0.3, 1.0, 100)))
    store._write_bundle(make_strategy_bundle(strategy_id="b", returns=rng.normal(0.3, 1.0, 100)))

    response = client.get("/api/portfolio/combination", params={"strategy_ids": ["a", "b"]})

    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["portfolio"]["p_pass"] <= 1.0
    assert len(body["marginal_contributions"]) == 2


def test_portfolio_optimize_returns_weights_and_portfolio_p_pass(
    client: TestClient, make_strategy_bundle: Callable[..., Any]
) -> None:
    """L'endpoint d'allocation optimale renvoie des poids et un P(passage) de portefeuille."""
    rng = np.random.default_rng(6)
    store._write_bundle(make_strategy_bundle(strategy_id="a", returns=rng.normal(0.3, 1.0, 100)))
    store._write_bundle(make_strategy_bundle(strategy_id="b", returns=rng.normal(0.3, 1.0, 100)))

    response = client.get("/api/portfolio/optimize", params={"strategy_ids": ["a", "b"]})

    assert response.status_code == 200
    body = response.json()
    assert set(body["weights"].keys()) == {"a", "b"}
    assert 0.0 <= body["portfolio"]["p_pass"] <= 1.0


def test_portfolio_optimize_404s_for_an_unknown_strategy(client: TestClient) -> None:
    """Optimiser une allocation sur une stratégie inconnue renvoie 404."""
    response = client.get("/api/portfolio/optimize", params={"strategy_ids": ["nope"]})

    assert response.status_code == 404


def test_papers_status_is_explicit_about_phase_7_being_unbuilt(client: TestClient) -> None:
    """La vue papiers dit honnêtement qu'elle n'est pas livrée, jamais un placeholder silencieux."""
    body = client.get("/api/papers").json()

    assert body["implemented"] is False
    assert "Phase 7" in body["message"]
