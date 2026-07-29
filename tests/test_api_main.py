"""Tests de edgelab.api.main (Phase 8) : l'API HTTP en lecture seule."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from edgelab import settings as settings_module
from edgelab.api import store
from edgelab.api.main import app
from edgelab.data.lse import LseDataError
from edgelab.registry.models import Trial
from edgelab.registry.repository import TrialRepository
from edgelab.settings import resolve
from fastapi.testclient import TestClient

from tests.test_constants import SAMPLE_API_KEY
from tests.test_data_lse import FakeLseClient


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isole chaque test : répertoire de bundles, registre, lockbox et papiers dédiés."""
    monkeypatch.setattr(store, "SEED_DATA_DIR", tmp_path / "strategies")
    monkeypatch.setattr(store, "DEFAULT_REGISTRY_DB", tmp_path / "registry.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_LOCKBOX_DB", tmp_path / "lockbox.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_PAPERS_DB", tmp_path / "papers.sqlite3")
    monkeypatch.setattr(store, "DEFAULT_DATASET_CATALOG", tmp_path / "catalog.duckdb")
    monkeypatch.setattr(store, "DEFAULT_BARS_DIR", tmp_path / "bars")
    monkeypatch.setattr(store, "DEFAULT_DOWNLOAD_DIR", tmp_path / "downloads")
    monkeypatch.setattr(store, "DEFAULT_CREDENTIALS_FILE", tmp_path / "credentials.env")
    monkeypatch.delenv("LSE_API_KEY", raising=False)
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


# --- Données de marché --------------------------------------------------------


@pytest.fixture
def vault_rows(make_clean_bars: Callable[..., Any], eurusd: Any) -> list[dict[str, Any]]:
    """Les lignes qu'un vault LSE renverrait pour vingt jours d'EURUSD horaire propre."""
    bars = make_clean_bars(
        eurusd,
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 21, tzinfo=UTC),
        frequency=timedelta(hours=1),
    )
    return [
        {
            "timestamp": row["timestamp"].isoformat().replace("+00:00", "Z"),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in bars.iter_rows(named=True)
    ]


def _download_payload() -> dict[str, Any]:
    return {
        "provider_symbol": "EUR/USD",
        "instrument_symbol": "EURUSD",
        "timeframe": "1h",
        "start": datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
        "end": datetime(2024, 1, 21, tzinfo=UTC).isoformat(),
        "research_end": datetime(2024, 1, 13, tzinfo=UTC).isoformat(),
        "validation_end": datetime(2024, 1, 17, tzinfo=UTC).isoformat(),
    }


def test_list_datasets_is_empty_before_any_download(client: TestClient) -> None:
    """Un store vierge renvoie une liste vide, pas une erreur."""
    assert client.get("/api/datasets").json() == []


def test_provider_catalog_reports_a_missing_key_as_service_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans clé API, le catalogue répond 503 avec le message actionnable du module data."""

    def _raise(*_a: object, **_k: object) -> None:
        raise LseDataError("clé API London Strategic Edge manquante : renseigner LSE_API_KEY")

    monkeypatch.setattr(store, "open_client", _raise)

    response = client.get("/api/provider/catalog")

    assert response.status_code == 503
    assert "LSE_API_KEY" in response.json()["detail"]


def test_provider_catalog_filters_on_the_search_term(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`search` filtre sur le symbole comme sur le nom, sans que l'API n'invente de règle."""
    rows = [
        {"symbol": "EUR/USD", "name": "Euro", "category": "Forex", "dataset": "fx"},
        {"symbol": "BTC/USD", "name": "Bitcoin", "category": "Crypto", "dataset": "crypto"},
    ]
    monkeypatch.setattr(store, "open_client", lambda *_a, **_k: FakeLseClient(catalog_rows=rows))

    response = client.get("/api/provider/catalog", params={"search": "bitcoin"})

    assert [row["symbol"] for row in response.json()] == ["BTC/USD"]


def test_download_ingests_a_dataset_and_reports_its_splits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vault_rows: list[dict[str, Any]]
) -> None:
    """Un téléchargement crée un dataset dont les trois splits sont décrits dans la réponse."""
    monkeypatch.setattr(store, "open_client", lambda *_a, **_k: FakeLseClient([vault_rows]))

    response = client.post("/api/provider/download", json=_download_payload())

    body = response.json()
    assert response.status_code == 200
    assert body["quarantined"] is False
    assert [s["split"] for s in body["dataset"]["splits"]] == [
        "research",
        "validation",
        "holdout",
    ]
    assert all(s["n_bars"] > 0 for s in body["dataset"]["splits"])


def test_download_rejects_an_unknown_instrument(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vault_rows: list[dict[str, Any]]
) -> None:
    """Un instrument absent des univers livrés est refusé en 422."""
    monkeypatch.setattr(store, "open_client", lambda *_a, **_k: FakeLseClient([vault_rows]))
    payload = _download_payload() | {"instrument_symbol": "DOGECOIN"}

    response = client.post("/api/provider/download", json=payload)

    assert response.status_code == 422


def test_get_dataset_returns_the_full_integrity_report(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vault_rows: list[dict[str, Any]]
) -> None:
    """Le détail d'un dataset expose le rapport d'intégrité, pas seulement son résumé."""
    monkeypatch.setattr(store, "open_client", lambda *_a, **_k: FakeLseClient([vault_rows]))
    dataset_id = client.post("/api/provider/download", json=_download_payload()).json()["dataset"][
        "dataset_id"
    ]

    response = client.get(f"/api/datasets/{dataset_id}")

    assert response.status_code == 200
    assert "issues" in response.json()["integrity_report"]


def test_get_dataset_reports_an_unknown_id_as_not_found(client: TestClient) -> None:
    """Un `dataset_id` inconnu répond 404."""
    assert client.get("/api/datasets/n-existe-pas").status_code == 404


def test_open_holdout_requires_a_written_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vault_rows: list[dict[str, Any]]
) -> None:
    """I3 tient aussi depuis l'UI : sans raison écrite, 422 et rien n'est compté."""
    monkeypatch.setattr(store, "open_client", lambda *_a, **_k: FakeLseClient([vault_rows]))
    dataset_id = client.post("/api/provider/download", json=_download_payload()).json()["dataset"][
        "dataset_id"
    ]

    response = client.post(
        "/api/datasets/holdout",
        json={"dataset_id": dataset_id, "strategy_id": "s1", "reason": "  "},
    )

    assert response.status_code == 422
    assert store.holdout_access_count("s1") == 0


def test_open_holdout_counts_the_access_permanently(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vault_rows: list[dict[str, Any]]
) -> None:
    """Chaque ouverture depuis l'UI incrémente le compteur permanent de la stratégie."""
    monkeypatch.setattr(store, "open_client", lambda *_a, **_k: FakeLseClient([vault_rows]))
    dataset_id = client.post("/api/provider/download", json=_download_payload()).json()["dataset"][
        "dataset_id"
    ]

    body = client.post(
        "/api/datasets/holdout",
        json={"dataset_id": dataset_id, "strategy_id": "s1", "reason": "validation finale"},
    ).json()

    assert body["access_count"] == 1
    assert body["flagged"] is False
    assert body["n_bars"] > 0


def test_open_holdout_reports_an_unknown_dataset_as_not_found(client: TestClient) -> None:
    """Ouvrir le holdout d'un dataset inexistant répond 404."""
    response = client.post(
        "/api/datasets/holdout",
        json={"dataset_id": "n-existe-pas", "strategy_id": "s1", "reason": "test"},
    )

    assert response.status_code == 404


# --- Réglages (clés API) ------------------------------------------------------


def test_settings_lists_the_known_slots_before_anything_is_set(client: TestClient) -> None:
    """L'emplacement LSE est exposé même vide, avec sa provenance effective."""
    body = client.get("/api/settings").json()

    slot = next(c for c in body["credentials"] if c["env_var"] == "LSE_API_KEY")
    assert slot["configured"] is False
    assert slot["source"] == "absent"
    assert slot["wired"] is True


def test_setting_a_credential_never_returns_it_in_clear(client: TestClient) -> None:
    """Le garde-fou principal de l'API : aucune route ne rend une clé lisible."""
    response = client.put("/api/settings/LSE_API_KEY", json={"value": SAMPLE_API_KEY})

    assert response.status_code == 200
    assert SAMPLE_API_KEY not in response.text
    slot = next(c for c in response.json()["credentials"] if c["env_var"] == "LSE_API_KEY")
    assert slot["hint"].endswith(SAMPLE_API_KEY[-4:])
    assert slot["source"] == "file"


def test_a_stored_credential_is_read_back_by_the_provider_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Une clé posée depuis l'UI est bien celle que `open_client` utilise ensuite."""
    monkeypatch.setattr(settings_module, "DEFAULT_CREDENTIALS_FILE", tmp_path / "credentials.env")
    client.put("/api/settings/LSE_API_KEY", json={"value": SAMPLE_API_KEY})

    assert resolve("LSE_API_KEY") == SAMPLE_API_KEY


def test_setting_a_credential_rejects_an_invalid_name(client: TestClient) -> None:
    """Un nom qui ne serait pas sourçable dans un shell est refusé en 422."""
    response = client.put("/api/settings/ma-cle", json={"value": SAMPLE_API_KEY})

    assert response.status_code == 422


def test_setting_a_credential_rejects_an_empty_value(client: TestClient) -> None:
    """Une valeur vide est une suppression déguisée : refusée explicitement."""
    assert client.put("/api/settings/LSE_API_KEY", json={"value": "   "}).status_code == 422


def test_deleting_a_credential_removes_it(client: TestClient) -> None:
    """La suppression retire la clé du fichier et se reflète dans l'état renvoyé."""
    client.put("/api/settings/LSE_API_KEY", json={"value": SAMPLE_API_KEY})

    body = client.delete("/api/settings/LSE_API_KEY").json()

    slot = next(c for c in body["credentials"] if c["env_var"] == "LSE_API_KEY")
    assert slot["configured"] is False


def test_deleting_a_credential_that_was_never_stored_is_not_found(client: TestClient) -> None:
    """Supprimer une clé absente répond 404 plutôt qu'un succès silencieux."""
    assert client.delete("/api/settings/LSE_API_KEY").status_code == 404


def test_writing_a_credential_from_a_remote_host_is_forbidden() -> None:
    """L'API n'a pas d'authentification : seule la machine locale peut poser un secret."""
    remote = TestClient(app, client=("203.0.113.7", 51234))

    response = remote.put("/api/settings/LSE_API_KEY", json={"value": SAMPLE_API_KEY})

    assert response.status_code == 403
    assert "machine locale" in response.json()["detail"]
