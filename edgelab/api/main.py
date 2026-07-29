"""FastAPI en lecture seule sur les artefacts produits par le CLI (Phase 8).

Chaque route délègue à `edgelab.api.store` : ce module n'encode aucune règle
de tri, de seuil ou de décision — il marshalle des requêtes HTTP vers des
lectures d'artefacts ou des appels directs aux modules de calcul (voir la
distinction documentée dans `store.py`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from edgelab.api import store
from edgelab.api.schemas import (
    CredentialUpdate,
    DatasetDetail,
    DatasetSummary,
    DownloadRequest,
    DownloadResult,
    HoldoutRequest,
    HoldoutResult,
    LeaderboardRow,
    ProviderInstrument,
    SettingsResponse,
    StrategyBundle,
    TrialLink,
)
from edgelab.data.lockbox import HoldoutAccessDeniedError
from edgelab.data.lse import LseDataError
from edgelab.data.manifest import QuarantinedDatasetError
from edgelab.data.selection import EmptySplitError, UnknownDatasetError
from edgelab.papers.models import HypothesisDraftRequest, PaperAnalysisRequest, TriageStatus
from edgelab.papers.repository import PaperNotFoundError, PaperRecord, PaperRepositoryError
from edgelab.portfolio.models import AllocationSearchResult, CombinationResult, CorrelationMatrix
from edgelab.propsim.models import RiskSurfaceResult
from edgelab.registry.models import Trial
from edgelab.settings import CredentialError

app = FastAPI(
    title="EdgeLab API",
    description="Vue en lecture sur les artefacts d'EdgeLab. Aucune logique métier.",
    version="0.1.0",
)

_MIN_STRATEGIES_FOR_CORRELATION = 2

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Sonde de vie triviale."""
    return {"status": "ok"}


@app.get("/api/trials", response_model=list[Trial])
def list_trials(strategy_id: str | None = None) -> list[Trial]:
    """Registre d'essais brut (I1), filtrable par stratégie. Le plus récent en premier."""
    return store.registry_trials(strategy_id)


@app.get("/api/trials/count")
def trial_count() -> dict[str, int]:
    """Compteur global d'essais — l'entrée du Deflated Sharpe Ratio."""
    return {"count": store.registry_trial_count()}


@app.get("/api/trials/{trial_id}", response_model=Trial)
def get_trial(trial_id: str) -> Trial:
    """Détail d'un essai. 404 s'il est inconnu du registre."""
    trials = {t.id: t for t in store.registry_trials()}
    if trial_id not in trials:
        raise HTTPException(status_code=404, detail=f"essai inconnu : {trial_id}")
    return trials[trial_id]


@app.get("/api/strategies", response_model=list[LeaderboardRow])
def list_strategies() -> list[LeaderboardRow]:
    """Lignes du leaderboard. Le tri par défaut (P(passage)) est appliqué côté vue."""
    return store.leaderboard_rows()


@app.get("/api/strategies/{strategy_id}", response_model=StrategyBundle)
def get_strategy(strategy_id: str) -> StrategyBundle:
    """Bundle complet d'une stratégie (fiche stratégie, vue 2)."""
    try:
        return store.get_bundle(strategy_id)
    except store.StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/strategies/{strategy_id}/trials", response_model=list[TrialLink])
def get_strategy_trials(strategy_id: str) -> list[TrialLink]:
    """Essais liés à une stratégie, pour le journal complet en bas de sa fiche."""
    return [
        TrialLink(
            id=t.id,
            trial_type=t.trial_type.value,
            created_at=t.created_at.isoformat(),
            lineage_hash=t.lineage_hash,
        )
        for t in store.registry_trials(strategy_id)
    ]


@app.get("/api/strategies/{strategy_id}/risk-surface", response_model=RiskSurfaceResult)
def get_risk_surface(
    strategy_id: str,
    ruleset: Annotated[str, Query()] = "",
    phase: Annotated[str | None, Query()] = None,
) -> RiskSurfaceResult:
    """Surface de risque. Sans `ruleset`, renvoie l'artefact précalculé du bundle."""
    try:
        bundle = store.get_bundle(strategy_id)
        if not ruleset or ruleset.lower() == bundle.ruleset_name.lower():
            return bundle.risk_surface
        return store.run_risk_surface(strategy_id, ruleset, phase)
    except store.StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/rulesets")
def list_rulesets() -> list[dict[str, object]]:
    """Rulesets prop firm livrés, pour le sélecteur de la vue surface de risque."""
    return store.list_rulesets()


@app.get("/api/portfolio/correlation", response_model=CorrelationMatrix)
def get_correlation(strategy_ids: Annotated[list[str], Query()]) -> CorrelationMatrix:
    """Matrice de corrélation par trade entre les stratégies sélectionnées."""
    if len(strategy_ids) < _MIN_STRATEGIES_FOR_CORRELATION:
        raise HTTPException(status_code=400, detail="au moins 2 strategy_ids requis")
    try:
        return store.run_correlation(strategy_ids)
    except store.StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/portfolio/combination", response_model=CombinationResult)
def get_combination(
    strategy_ids: Annotated[list[str], Query()],
    ruleset: Annotated[str, Query()] = "ftmo",
    phase: Annotated[str | None, Query()] = None,
) -> CombinationResult:
    """P(passage) du portefeuille, corrélation et contribution marginale par stratégie (I5).

    Requiert au moins 2 `strategy_ids` : la contribution marginale se mesure
    par exclusion, ce qui n'a pas de sens pour une seule stratégie
    (`edgelab.portfolio.combination.explore_combination`).
    """
    weight = 1.0 / len(strategy_ids)
    weights = dict.fromkeys(strategy_ids, weight)
    try:
        return store.run_combination(strategy_ids, weights, ruleset, phase)
    except store.StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/optimize", response_model=AllocationSearchResult)
def get_optimal_allocation(
    strategy_ids: Annotated[list[str], Query()],
    ruleset: Annotated[str, Query()] = "ftmo",
    phase: Annotated[str | None, Query()] = None,
) -> AllocationSearchResult:
    """Poids qui maximisent P(passage) du portefeuille, jamais le Sharpe ni le rendement (I5)."""
    try:
        return store.run_optimize_allocation(strategy_ids, ruleset, phase)
    except store.StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PaperStatusUpdate(BaseModel):
    """Corps de `PATCH /api/papers/{paper_id}/status`."""

    status: TriageStatus
    reason: str = ""


class PromptResponse(BaseModel):
    """Un prompt copiable, encapsulé en JSON."""

    prompt: str


@app.get("/api/papers", response_model=list[PaperRecord])
def list_papers() -> list[PaperRecord]:
    """Papiers connus (Phase 7), du plus récemment mis à jour au plus ancien."""
    return store.list_papers()


@app.post("/api/papers", response_model=PaperRecord)
def create_paper(request: PaperAnalysisRequest) -> PaperRecord:
    """Crée une fiche papier depuis le JSON collé par l'utilisateur (déclencheur d'écriture)."""
    return store.create_paper(request)


# Doit être déclaré avant `/api/papers/{paper_id}` : sinon Starlette router
# le chemin littéral "prompt" comme une valeur de `paper_id` (même forme de
# route, premier enregistré gagne).
@app.get("/api/papers/prompt", response_model=PromptResponse)
def get_paper_analysis_prompt() -> PromptResponse:
    """Prompt copiable statique « Analyse de papier de recherche »."""
    return PromptResponse(prompt=store.paper_analysis_prompt())


@app.get("/api/papers/{paper_id}", response_model=PaperRecord)
def get_paper(paper_id: str) -> PaperRecord:
    """Un papier complet, brouillon d'hypothèse inclus s'il existe."""
    try:
        return store.get_paper(paper_id)
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/papers/{paper_id}/hypothesis-prompt", response_model=PromptResponse)
def get_paper_hypothesis_prompt(paper_id: str) -> PromptResponse:
    """Prompt copiable « Générer une hypothèse falsifiable », personnalisé au papier."""
    try:
        return PromptResponse(prompt=store.paper_hypothesis_prompt(paper_id))
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/papers/{paper_id}/hypothesis", response_model=PaperRecord)
def add_paper_hypothesis(paper_id: str, request: HypothesisDraftRequest) -> PaperRecord:
    """Rattache un brouillon d'hypothèse (I2) au papier."""
    try:
        return store.attach_paper_hypothesis(paper_id, request)
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/papers/{paper_id}/status", response_model=PaperRecord)
def update_paper_status(paper_id: str, body: PaperStatusUpdate) -> PaperRecord:
    """Déplace un papier dans la file de triage (`mort` exige un motif écrit)."""
    try:
        return store.set_paper_status(paper_id, body.status, body.reason)
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PaperRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Données de marché --------------------------------------------------------


@app.get("/api/datasets", response_model=list[DatasetSummary])
def list_datasets() -> list[DatasetSummary]:
    """Les datasets ingérés localement. Les datasets en quarantaine sont inclus, jamais masqués."""
    return store.list_datasets()


@app.get("/api/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str) -> DatasetDetail:
    """Détail d'un dataset, rapport d'intégrité complet inclus."""
    try:
        return store.get_dataset(dataset_id)
    except UnknownDatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/instruments")
def list_instruments() -> list[dict[str, str]]:
    """Les instruments d'EdgeLab pouvant recevoir un dataset (univers `broad_12`)."""
    return store.list_instruments()


@app.get("/api/provider/catalog", response_model=list[ProviderInstrument])
def provider_catalog(
    category: str | None = None, search: str | None = None
) -> list[ProviderInstrument]:
    """Catalogue London Strategic Edge (déclencheur de job : exige `LSE_API_KEY`)."""
    try:
        return store.run_provider_catalog(category, search)
    except LseDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/provider/download", response_model=DownloadResult)
def download_dataset(request: DownloadRequest) -> DownloadResult:
    """Télécharge, contrôle et ingère un instrument (déclencheur de job).

    Un dataset mis en quarantaine renvoie tout de même 200 avec
    `quarantined: true` : il a bien été créé et reste consultable pour
    diagnostic, c'est le backtester qui le refusera.
    """
    try:
        return store.run_download(request)
    except LseDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/datasets/holdout", response_model=HoldoutResult)
def open_holdout(request: HoldoutRequest) -> HoldoutResult:
    """Ouvre le holdout d'un dataset (I3) : raison écrite obligatoire, accès compté à vie."""
    try:
        return store.run_holdout(request)
    except UnknownDatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HoldoutAccessDeniedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (QuarantinedDatasetError, EmptySplitError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# --- Réglages (clés API) ------------------------------------------------------
#
# Aucune route ici ne renvoie de secret : `SettingsResponse` ne porte que des
# valeurs masquées, et il n'existe pas d'endpoint de lecture d'une clé.

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _require_loopback(request: Request) -> None:
    """Refuse une écriture de clé venant d'ailleurs que de la machine locale.

    L'API n'a aucune authentification : c'est acceptable pour un outil de
    recherche personnel servi sur la boucle locale, et inacceptable dès qu'il
    écoute sur une interface publique. Plutôt que de faire confiance à
    l'utilisateur pour ne jamais lancer `--host 0.0.0.0`, la seule route qui
    accepte un secret vérifie elle-même d'où vient l'appel.

    Raises:
        HTTPException: 403 si le client n'est pas sur la boucle locale.
    """
    host = request.client.host if request.client else ""
    if host not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=403,
            detail=(
                "l'écriture d'une clé API n'est autorisée que depuis la machine locale ; "
                "l'API n'a pas d'authentification et ne doit pas écouter sur une "
                "interface publique"
            ),
        )


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """État des emplacements de clés, masqué. Ne renvoie jamais une clé en clair."""
    return store.settings_status()


@app.put("/api/settings/{env_var}", response_model=SettingsResponse)
def put_credential(env_var: str, body: CredentialUpdate, request: Request) -> SettingsResponse:
    """Enregistre une clé dans le fichier local (0600). La réponse est masquée."""
    _require_loopback(request)
    try:
        return store.set_credential(env_var, body.value)
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/settings/{env_var}", response_model=SettingsResponse)
def delete_credential(env_var: str, request: Request) -> SettingsResponse:
    """Supprime une clé du fichier local. Une variable d'environnement n'est jamais touchée."""
    _require_loopback(request)
    try:
        return store.unset_credential(env_var)
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
