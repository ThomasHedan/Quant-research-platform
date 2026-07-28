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
    """Isole chaque test : répertoire de bundles, registre, lockbox et papiers dédiés."""
    monkeypatch.setattr(store, "SEED_DATA_DIR", tmp_path / "strategies")
    monkeypatch.setattr(store, "DEFAULT_REGISTRY_DB", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_LOCKBOX_DB", tmp_path / "lockbox.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_PAPERS_DB", tmp_path / "papers.sqlite3")
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


def test_list_papers_is_empty_on_a_fresh_store(client: TestClient) -> None:
    """Aucun papier créé : liste vide, jamais un placeholder inventé."""
    response = client.get("/api/papers")

    assert response.status_code == 200
    assert response.json() == []


def test_create_paper_then_get_it_roundtrips(
    client: TestClient, make_paper_analysis_request: Callable[..., Any]
) -> None:
    """Un papier créé via `POST /api/papers` est relisible via `GET /api/papers/{id}`."""
    payload = make_paper_analysis_request(title="Titre API HTTP").model_dump(mode="json")

    create_response = client.post("/api/papers", json=payload)

    assert create_response.status_code == 200
    paper_id = create_response.json()["sheet"]["id"]

    get_response = client.get(f"/api/papers/{paper_id}")
    assert get_response.status_code == 200
    assert get_response.json()["sheet"]["title"] == "Titre API HTTP"
    assert get_response.json()["status"] == "fiche_faite"


def test_create_paper_rejects_an_invalid_payload(client: TestClient) -> None:
    """Un JSON qui ne respecte pas le schéma renvoie 422, la validation FastAPI standard."""
    response = client.post("/api/papers", json={"title": ""})

    assert response.status_code == 422


def test_get_paper_404s_for_an_unknown_id(client: TestClient) -> None:
    """Un papier inconnu renvoie 404, jamais un enregistrement vide silencieux."""
    response = client.get("/api/papers/does-not-exist")

    assert response.status_code == 404


def test_get_paper_analysis_prompt_is_not_captured_by_the_paper_id_route(
    client: TestClient,
) -> None:
    """`/api/papers/prompt` renvoie le prompt statique, pas un 404 pour `paper_id='prompt'`."""
    response = client.get("/api/papers/prompt")

    assert response.status_code == 200
    assert "language_source" in response.json()["prompt"]


def test_get_paper_hypothesis_prompt_embeds_the_paper_fiche(
    client: TestClient, make_paper_analysis_request: Callable[..., Any]
) -> None:
    """Le prompt personnalisé embarque la fiche du papier concerné."""
    payload = make_paper_analysis_request(title="Titre Prompt HTTP").model_dump(mode="json")
    paper_id = client.post("/api/papers", json=payload).json()["sheet"]["id"]

    response = client.get(f"/api/papers/{paper_id}/hypothesis-prompt")

    assert response.status_code == 200
    assert "Titre Prompt HTTP" in response.json()["prompt"]


def test_get_paper_hypothesis_prompt_404s_for_an_unknown_id(client: TestClient) -> None:
    """Demander le prompt d'un papier inconnu renvoie 404."""
    response = client.get("/api/papers/does-not-exist/hypothesis-prompt")

    assert response.status_code == 404


def test_add_paper_hypothesis_advances_the_triage_status(
    client: TestClient,
    make_paper_analysis_request: Callable[..., Any],
    make_hypothesis_draft_request: Callable[..., Any],
) -> None:
    """Rattacher un brouillon valide fait avancer le papier à `hypothese_ecrite`."""
    paper_payload = make_paper_analysis_request().model_dump(mode="json")
    paper_id = client.post("/api/papers", json=paper_payload).json()["sheet"]["id"]
    hypothesis_payload = make_hypothesis_draft_request().model_dump(mode="json")

    response = client.post(f"/api/papers/{paper_id}/hypothesis", json=hypothesis_payload)

    assert response.status_code == 200
    assert response.json()["status"] == "hypothese_ecrite"


def test_add_paper_hypothesis_400s_when_unfalsifiable(
    client: TestClient,
    make_paper_analysis_request: Callable[..., Any],
    make_hypothesis_draft_request: Callable[..., Any],
) -> None:
    """I2 : un brouillon dont `where_it_should_not_work` est vide renvoie 400, pas un 500."""
    paper_payload = make_paper_analysis_request().model_dump(mode="json")
    paper_id = client.post("/api/papers", json=paper_payload).json()["sheet"]["id"]
    unfalsifiable = make_hypothesis_draft_request(where_it_should_not_work="").model_dump(
        mode="json"
    )

    response = client.post(f"/api/papers/{paper_id}/hypothesis", json=unfalsifiable)

    assert response.status_code == 400


def test_add_paper_hypothesis_404s_for_an_unknown_paper(
    client: TestClient, make_hypothesis_draft_request: Callable[..., Any]
) -> None:
    """Rattacher un brouillon à un papier inconnu renvoie 404."""
    payload = make_hypothesis_draft_request().model_dump(mode="json")

    response = client.post("/api/papers/does-not-exist/hypothesis", json=payload)

    assert response.status_code == 404


def test_update_paper_status_moves_the_paper(
    client: TestClient, make_paper_analysis_request: Callable[..., Any]
) -> None:
    """`PATCH .../status` déplace le papier dans la file de triage."""
    payload = make_paper_analysis_request().model_dump(mode="json")
    paper_id = client.post("/api/papers", json=payload).json()["sheet"]["id"]

    response = client.patch(f"/api/papers/{paper_id}/status", json={"status": "en_test"})

    assert response.status_code == 200
    assert response.json()["status"] == "en_test"


def test_update_paper_status_mort_without_reason_400s(
    client: TestClient, make_paper_analysis_request: Callable[..., Any]
) -> None:
    """`mort` sans motif écrit renvoie 400 — le motif de mort doit rester conservé."""
    payload = make_paper_analysis_request().model_dump(mode="json")
    paper_id = client.post("/api/papers", json=payload).json()["sheet"]["id"]

    response = client.patch(f"/api/papers/{paper_id}/status", json={"status": "mort"})

    assert response.status_code == 400


def test_update_paper_status_404s_for_an_unknown_paper(client: TestClient) -> None:
    """Changer le statut d'un papier inconnu renvoie 404."""
    response = client.patch("/api/papers/does-not-exist/status", json={"status": "en_test"})

    assert response.status_code == 404
