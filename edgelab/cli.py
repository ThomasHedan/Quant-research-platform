"""Interface primaire d'EdgeLab.

Toute la logique métier vit dans les sous-packages de `edgelab/` ; ce module
ne fait qu'exposer des commandes Typer qui les orchestrent. L'API HTTP
(`edgelab/api/`) ne fait que relire les artefacts que ce CLI produit — elle
ne recalcule jamais rien.

Les commandes sont ajoutées phase par phase (voir `CLAUDE.md`). Aucune
commande n'est livrée avant que le module qu'elle orchestre existe et soit
testé.
"""

import typer

app = typer.Typer(
    name="edgelab",
    help="EdgeLab — recherche quantitative rigoureuse : registre, event study, propsim.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """EdgeLab — recherche quantitative rigoureuse : registre, event study, propsim."""


if __name__ == "__main__":
    app()
