"""FastAPI en lecture seule sur les artefacts produits par le CLI (Phase 8).

Chaque route délègue à `edgelab.api.store` : ce module n'encode aucune règle
de tri, de seuil ou de décision — il marshalle des requêtes HTTP vers des
lectures d'artefacts ou des appels directs aux modules de calcul (voir la
distinction documentée dans `store.py`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from edgelab.api import store
from edgelab.api.schemas import LeaderboardRow, PapersStatus, StrategyBundle, TrialLink
from edgelab.portfolio.models import CombinationResult, CorrelationMatrix
from edgelab.propsim.models import RiskSurfaceResult
from edgelab.registry.models import Trial

app = FastAPI(
    title="EdgeLab API",
    description="Vue en lecture sur les artefacts d'EdgeLab. Aucune logique métier.",
    version="0.1.0",
)

_MIN_STRATEGIES_FOR_CORRELATION = 2

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
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
    """P(passage) du portefeuille, corrélation et contribution marginale par stratégie (I5)."""
    weight = 1.0 / len(strategy_ids)
    weights = dict.fromkeys(strategy_ids, weight)
    try:
        return store.run_combination(strategy_ids, weights, ruleset, phase)
    except store.StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/papers", response_model=PapersStatus)
def get_papers_status() -> PapersStatus:
    """Statut du module papiers. Phase 7 n'est pas livrée : dit explicitement, jamais masqué."""
    return PapersStatus(
        implemented=False,
        message=(
            "Phase 7 (module papiers) n'est pas encore livrée. "
            "Cette vue attend l'ingestion PDF et la fiche papier multilingue."
        ),
    )
