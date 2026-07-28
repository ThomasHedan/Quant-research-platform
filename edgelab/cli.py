"""Interface primaire d'EdgeLab.

Toute la logique métier vit dans les sous-packages de `edgelab/` ; ce module
ne fait qu'exposer des commandes Typer qui les orchestrent. L'API HTTP
(`edgelab/api/`) ne fait que relire les artefacts que ce CLI produit — elle
ne recalcule jamais rien.

Les commandes sont ajoutées phase par phase (voir `CLAUDE.md`). Aucune
commande n'est livrée avant que le module qu'elle orchestre existe et soit
testé.
"""

import sys
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from pydantic import ValidationError

from edgelab.config import DEFAULT_PAPERS_DB, DEFAULT_REGISTRY_DB
from edgelab.papers import (
    HypothesisDraftRequest,
    PaperAnalysisRequest,
    PaperNotFoundError,
    PaperRepository,
    PaperRepositoryError,
    TriageStatus,
)
from edgelab.papers.prompts import PAPER_ANALYSIS_PROMPT, hypothesis_draft_prompt_for
from edgelab.registry import TrialRepository

app = typer.Typer(
    name="edgelab",
    help="EdgeLab — recherche quantitative rigoureuse : registre, event study, propsim.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """EdgeLab — recherche quantitative rigoureuse : registre, event study, propsim."""


trial_app = typer.Typer(help="Consulter le registre d'essais (lecture seule, append-only).")
app.add_typer(trial_app, name="trial")

DbPathOption = Annotated[Path, typer.Option("--db-path", help="Chemin du registre SQLite.")]


@trial_app.command("list")
def trial_list(db_path: DbPathOption = DEFAULT_REGISTRY_DB) -> None:
    """Liste les essais du registre, du plus récent au plus ancien."""
    with TrialRepository(db_path) as repo:
        trials = repo.list_trials()
    if not trials:
        typer.echo("Aucun essai enregistré.")
        return
    for trial in trials:
        typer.echo(
            f"{trial.id}  {trial.created_at:%Y-%m-%d %H:%M}  {trial.trial_type.value:<14} "
            f"{trial.strategy_id:<24} lineage={trial.lineage_hash[:10]}"
        )


@trial_app.command("show")
def trial_show(
    trial_id: Annotated[str, typer.Argument(help="Identifiant de l'essai.")],
    db_path: DbPathOption = DEFAULT_REGISTRY_DB,
) -> None:
    """Affiche le détail complet d'un essai."""
    with TrialRepository(db_path) as repo:
        trial = repo.get(trial_id)
    if trial is None:
        typer.echo(f"Essai introuvable : {trial_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(trial.model_dump_json(indent=2))


api_app = typer.Typer(help="Servir l'API HTTP en lecture seule (Phase 8).")
app.add_typer(api_app, name="api")


@api_app.command("serve")
def api_serve(
    host: Annotated[str, typer.Option(help="Adresse d'écoute.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port d'écoute.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Recharger à chaud (développement).")] = False,
) -> None:
    """Lance `edgelab.api.main:app` avec uvicorn. L'API ne fait que lire des artefacts."""
    uvicorn.run("edgelab.api.main:app", host=host, port=port, reload=reload)


paper_app = typer.Typer(
    help="Bibliothèque de papiers : fiches, testabilité, file de triage (Phase 7)."
)
app.add_typer(paper_app, name="paper")

PapersDbPathOption = Annotated[
    Path, typer.Option("--db-path", help="Chemin du stockage papiers SQLite.")
]


def _read_json_input(source: str) -> str:
    """Lit un JSON depuis un fichier, ou depuis stdin si `source` vaut '-'."""
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


@paper_app.command("prompt")
def paper_prompt() -> None:
    """Affiche le prompt copiable « Analyse de papier de recherche »."""
    typer.echo(PAPER_ANALYSIS_PROMPT)


@paper_app.command("add")
def paper_add(
    json_source: Annotated[
        str, typer.Argument(help="Chemin vers le JSON de la fiche, ou '-' pour stdin.")
    ],
    db_path: PapersDbPathOption = DEFAULT_PAPERS_DB,
) -> None:
    """Crée une fiche papier à partir du JSON renvoyé par le prompt d'analyse."""
    try:
        request = PaperAnalysisRequest.model_validate_json(_read_json_input(json_source))
    except ValidationError as exc:
        typer.echo(f"JSON invalide : {exc}", err=True)
        raise typer.Exit(code=1) from exc
    with PaperRepository(db_path) as repo:
        record = repo.create(request)
    typer.echo(
        f"papier créé : {record.sheet.id}  {record.sheet.title!r}  "
        f"testabilité={record.testability_score:.2f}  statut={record.status.value}"
    )


@paper_app.command("list")
def paper_list(db_path: PapersDbPathOption = DEFAULT_PAPERS_DB) -> None:
    """Liste les papiers, du plus récemment mis à jour au plus ancien."""
    with PaperRepository(db_path) as repo:
        records = repo.list_papers()
    if not records:
        typer.echo("Aucun papier enregistré.")
        return
    for record in records:
        typer.echo(
            f"{record.sheet.id}  [{record.status.value:<16}] "
            f"testabilité={record.testability_score:.2f}  {record.sheet.title}"
        )


@paper_app.command("show")
def paper_show(
    paper_id: Annotated[str, typer.Argument(help="Identifiant du papier.")],
    db_path: PapersDbPathOption = DEFAULT_PAPERS_DB,
) -> None:
    """Affiche le détail complet d'un papier, brouillon d'hypothèse inclus s'il existe."""
    with PaperRepository(db_path) as repo:
        record = repo.get(paper_id)
    if record is None:
        typer.echo(f"Papier introuvable : {paper_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(record.model_dump_json(indent=2))


@paper_app.command("hypothesis-prompt")
def paper_hypothesis_prompt(
    paper_id: Annotated[str, typer.Argument(help="Identifiant du papier.")],
    db_path: PapersDbPathOption = DEFAULT_PAPERS_DB,
) -> None:
    """Affiche le prompt copiable « Générer une hypothèse falsifiable » pour ce papier."""
    with PaperRepository(db_path) as repo:
        record = repo.get(paper_id)
    if record is None:
        typer.echo(f"Papier introuvable : {paper_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(hypothesis_draft_prompt_for(record.sheet))


@paper_app.command("hypothesis")
def paper_hypothesis(
    paper_id: Annotated[str, typer.Argument(help="Identifiant du papier.")],
    json_source: Annotated[
        str, typer.Argument(help="Chemin vers le JSON du brouillon, ou '-' pour stdin.")
    ],
    db_path: PapersDbPathOption = DEFAULT_PAPERS_DB,
) -> None:
    """Rattache un brouillon d'hypothèse (I2) au papier, fait avancer son statut."""
    try:
        request = HypothesisDraftRequest.model_validate_json(_read_json_input(json_source))
    except ValidationError as exc:
        typer.echo(f"JSON invalide : {exc}", err=True)
        raise typer.Exit(code=1) from exc
    with PaperRepository(db_path) as repo:
        try:
            record = repo.attach_hypothesis(paper_id, request)
        except PaperNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ValidationError as exc:
            # `HypothesisSheet` applique la règle de falsifiabilité (I2) à la
            # construction : une hypothèse qui ne prédit son échec nulle part
            # atterrit ici, pas dans le JSON invalide plus haut.
            typer.echo(f"hypothèse refusée (I2) : {exc}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"hypothèse rattachée : {record.sheet.id}  statut={record.status.value}")


@paper_app.command("set-status")
def paper_set_status(
    paper_id: Annotated[str, typer.Argument(help="Identifiant du papier.")],
    status: Annotated[TriageStatus, typer.Argument(help="Nouveau statut de triage.")],
    reason: Annotated[str, typer.Option(help="Motif — obligatoire pour le statut 'mort'.")] = "",
    db_path: PapersDbPathOption = DEFAULT_PAPERS_DB,
) -> None:
    """Déplace un papier dans la file de triage."""
    with PaperRepository(db_path) as repo:
        try:
            record = repo.set_status(paper_id, status, reason)
        except (PaperNotFoundError, PaperRepositoryError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"statut mis à jour : {record.sheet.id}  statut={record.status.value}")


if __name__ == "__main__":  # pragma: no cover
    app()
