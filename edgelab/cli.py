"""Interface primaire d'EdgeLab.

Toute la logique métier vit dans les sous-packages de `edgelab/` ; ce module
ne fait qu'exposer des commandes Typer qui les orchestrent. L'API HTTP
(`edgelab/api/`) ne fait que relire les artefacts que ce CLI produit — elle
ne recalcule jamais rien.

Les commandes sont ajoutées phase par phase (voir `CLAUDE.md`). Aucune
commande n'est livrée avant que le module qu'elle orchestre existe et soit
testé.
"""

from pathlib import Path
from typing import Annotated

import typer

from edgelab.config import DEFAULT_REGISTRY_DB
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


if __name__ == "__main__":  # pragma: no cover
    app()
