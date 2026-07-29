"""Interface primaire d'EdgeLab.

Toute la logique métier vit dans les sous-packages de `edgelab/` ; ce module
ne fait qu'exposer des commandes Typer qui les orchestrent. L'API HTTP
(`edgelab/api/`) ne fait que relire les artefacts que ce CLI produit — elle
ne recalcule jamais rien.

Les commandes sont ajoutées phase par phase (voir `CLAUDE.md`). Aucune
commande n'est livrée avant que le module qu'elle orchestre existe et soit
testé.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from pydantic import ValidationError

from edgelab.config import (
    DEFAULT_BARS_DIR,
    DEFAULT_CREDENTIALS_FILE,
    DEFAULT_DATASET_CATALOG,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_LOCKBOX_DB,
    DEFAULT_PAPERS_DB,
    DEFAULT_REGISTRY_DB,
)
from edgelab.data import (
    RED_FLAG_THRESHOLD,
    DatasetPartition,
    DatasetStatus,
    DatasetStore,
    DataSplit,
    EmptySplitError,
    HoldoutAccessDeniedError,
    HoldoutLockbox,
    LseDataError,
    QuarantinedDatasetError,
    UnknownDatasetError,
    describe_splits,
    ingest_lse_candles,
    ingest_lse_export,
    load_holdout,
    open_client,
    split_bounds,
)
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
from edgelab.settings import CredentialError, CredentialStore, describe, mask
from edgelab.universe import find_instrument

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


data_app = typer.Typer(
    help="Données de marché : catalogue London Strategic Edge, téléchargement, splits."
)
app.add_typer(data_app, name="data")

CatalogPathOption = Annotated[
    Path, typer.Option("--catalog-path", help="Catalogue DuckDB des manifestes de dataset.")
]
BarsDirOption = Annotated[Path, typer.Option("--bars-dir", help="Répertoire des barres Parquet.")]


def _open_store(catalog_path: Path, bars_dir: Path) -> DatasetStore:
    return DatasetStore(catalog_path, bars_dir)


def _parse_utc(value: str) -> datetime:
    """Interprète une date ISO-8601 comme un instant UTC.

    Une date sans fuseau est lue comme de l'UTC plutôt que comme l'heure locale
    de la machine : un même téléchargement doit donner le même dataset quel que
    soit le poste, sinon le hash de manifeste (I1) ne veut plus rien dire.

    Raises:
        typer.BadParameter: si la chaîne n'est pas une date ISO-8601.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"date ISO-8601 attendue, reçu {value!r}") from exc
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@data_app.command("catalog")
def data_catalog(
    category: Annotated[
        str | None,
        typer.Option("--category", help="fx, stocks, crypto, index, commodity, etf, bonds…"),
    ] = None,
    search: Annotated[
        str | None, typer.Option("--search", help="Filtre sur le symbole ou le nom.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Nombre maximum de lignes affichées.")] = 40,
) -> None:
    """Liste les instruments disponibles chez London Strategic Edge.

    Nécessite une clé API (`LSE_API_KEY`) : le catalogue est lu sur le vault
    en direct, avec la profondeur d'historique réelle de chaque symbole.
    """
    try:
        client = open_client()
        rows = client.catalog(category)
    except LseDataError as exc:
        typer.echo(f"Erreur London Strategic Edge : {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if search:
        needle = search.lower()
        rows = [
            r
            for r in rows
            if needle in str(r.get("symbol", "")).lower()
            or needle in str(r.get("name", "")).lower()
        ]
    if not rows:
        typer.echo("Aucun instrument ne correspond.")
        return
    for row in rows[:limit]:
        typer.echo(
            f"{row.get('symbol', '')!s:<16} {row.get('category', '')!s:<14} "
            f"{str(row.get('first', ''))[:10]} → {str(row.get('last', ''))[:10]}  "
            f"{row.get('ticks') or '?'} ticks  {row.get('name', '')}"
        )
    if len(rows) > limit:
        typer.echo(f"… {len(rows) - limit} autres (augmenter --limit)")


@data_app.command("download")
def data_download(  # noqa: PLR0913, PLR0917 — chaque paramètre est une décision explicite requise
    symbol: Annotated[str, typer.Argument(help="Symbole chez le fournisseur, ex. 'EUR/USD'.")],
    instrument_symbol: Annotated[
        str, typer.Option("--instrument", help="Instrument EdgeLab, ex. 'EURUSD'.")
    ],
    timeframe: Annotated[str, typer.Option("--timeframe", help="1m, 5m, 1h, 1d…")],
    start: Annotated[str, typer.Option("--start", help="Début UTC (ISO-8601).")],
    end: Annotated[str, typer.Option("--end", help="Fin UTC (ISO-8601).")],
    research_end: Annotated[
        str, typer.Option("--research-end", help="Fin du split research (exclue, ISO-8601).")
    ],
    validation_end: Annotated[
        str, typer.Option("--validation-end", help="Fin du split validation (exclue, ISO-8601).")
    ],
    bulk: Annotated[
        bool,
        typer.Option("--bulk", help="Passer par l'export Parquet du vault plutôt que l'API JSON."),
    ] = False,
    catalog_path: CatalogPathOption = DEFAULT_DATASET_CATALOG,
    bars_dir: BarsDirOption = DEFAULT_BARS_DIR,
    download_dir: Annotated[
        Path, typer.Option("--download-dir", help="Où déposer les Parquet bruts (--bulk).")
    ] = DEFAULT_DOWNLOAD_DIR,
) -> None:
    """Télécharge des barres LSE, les contrôle, et les ingère dans le store.

    Les bornes de partition n'ont volontairement pas de défaut : où s'arrête la
    recherche et où commence le holdout est la décision qui protège l'utilisateur
    de lui-même (I3), pas un détail de confort.
    """
    try:
        instrument = find_instrument(instrument_symbol)
        partition = DatasetPartition(
            research_end=_parse_utc(research_end), validation_end=_parse_utc(validation_end)
        )
        window_start, window_end = _parse_utc(start), _parse_utc(end)
        client = open_client()
    except (KeyError, ValueError, LseDataError) as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=1) from exc

    with _open_store(catalog_path, bars_dir) as store:
        try:
            if bulk:
                manifest = ingest_lse_export(
                    client,
                    symbol,
                    timeframe=timeframe,
                    start=window_start,
                    end=window_end,
                    instrument=instrument,
                    partition=partition,
                    store=store,
                    download_dir=download_dir,
                )
            else:
                manifest = ingest_lse_candles(
                    client,
                    symbol,
                    timeframe=timeframe,
                    start=window_start,
                    end=window_end,
                    instrument=instrument,
                    partition=partition,
                    store=store,
                )
        except (LseDataError, ValueError) as exc:
            typer.echo(f"Téléchargement échoué : {exc}", err=True)
            raise typer.Exit(code=1) from exc
        counts = describe_splits(store, manifest.dataset_id)

    typer.echo(f"dataset_id      {manifest.dataset_id}")
    typer.echo(f"instrument      {manifest.instrument_symbol}  ({manifest.source})")
    typer.echo(f"période         {manifest.start:%Y-%m-%d %H:%M} → {manifest.end:%Y-%m-%d %H:%M}")
    typer.echo(f"statut          {manifest.status.value}")
    typer.echo(f"intégrité       {manifest.integrity_report.summary()}")
    typer.echo(
        "splits          " + "  ".join(f"{split.value}={counts[split]}" for split in DataSplit)
    )
    if manifest.status is DatasetStatus.QUARANTINE:
        typer.echo("\nCe dataset est en QUARANTAINE : le moteur de backtest le refusera.", err=True)
        raise typer.Exit(code=2)


@data_app.command("list")
def data_list(
    instrument_symbol: Annotated[
        str | None, typer.Option("--instrument", help="Filtrer sur un instrument.")
    ] = None,
    catalog_path: CatalogPathOption = DEFAULT_DATASET_CATALOG,
    bars_dir: BarsDirOption = DEFAULT_BARS_DIR,
) -> None:
    """Liste les datasets ingérés localement, du plus récent au plus ancien."""
    with _open_store(catalog_path, bars_dir) as store:
        manifests = store.list_manifests(instrument_symbol=instrument_symbol)
    if not manifests:
        typer.echo("Aucun dataset ingéré.")
        return
    for manifest in manifests:
        typer.echo(
            f"{manifest.dataset_id[:12]}  {manifest.instrument_symbol:<8} "
            f"{manifest.status.value:<10} {manifest.start:%Y-%m-%d} → {manifest.end:%Y-%m-%d}  "
            f"{manifest.source}"
        )


@data_app.command("show")
def data_show(
    dataset_id: Annotated[str, typer.Argument(help="Identifiant du dataset.")],
    catalog_path: CatalogPathOption = DEFAULT_DATASET_CATALOG,
    bars_dir: BarsDirOption = DEFAULT_BARS_DIR,
) -> None:
    """Affiche le manifeste complet, le rapport d'intégrité et la taille de chaque split."""
    with _open_store(catalog_path, bars_dir) as store:
        manifest = store.load_manifest(dataset_id)
        if manifest is None:
            typer.echo(f"Dataset introuvable : {dataset_id}", err=True)
            raise typer.Exit(code=1)
        counts = describe_splits(store, dataset_id)
    typer.echo(manifest.model_dump_json(indent=2))
    typer.echo("")
    for split in DataSplit:
        bounds = split_bounds(manifest, split)
        typer.echo(
            f"{split.value:<11} {counts[split]:>8} barres  "
            f"{bounds.start:%Y-%m-%d %H:%M} → {bounds.end:%Y-%m-%d %H:%M}"
        )


@data_app.command("holdout")
def data_holdout(  # noqa: PLR0913, PLR0917 — chaque paramètre est une décision explicite requise (I3)
    dataset_id: Annotated[str, typer.Argument(help="Identifiant du dataset.")],
    strategy_id: Annotated[str, typer.Option("--strategy-id", help="Stratégie qui ouvre.")],
    reason: Annotated[str, typer.Option("--reason", help="Raison écrite, obligatoire (I3).")],
    catalog_path: CatalogPathOption = DEFAULT_DATASET_CATALOG,
    bars_dir: BarsDirOption = DEFAULT_BARS_DIR,
    lockbox_path: Annotated[
        Path, typer.Option("--lockbox-path", help="Journal d'accès holdout.")
    ] = DEFAULT_LOCKBOX_DB,
) -> None:
    """Ouvre le holdout d'un dataset. L'accès est permanent, compté, et jamais annulable (I3)."""
    with _open_store(catalog_path, bars_dir) as store, HoldoutLockbox(lockbox_path) as lockbox:
        try:
            selection = load_holdout(
                store, dataset_id, strategy_id=strategy_id, reason=reason, lockbox=lockbox
            )
        except (UnknownDatasetError, HoldoutAccessDeniedError) as exc:
            typer.echo(f"Accès refusé : {exc}", err=True)
            raise typer.Exit(code=1) from exc
        except (QuarantinedDatasetError, EmptySplitError) as exc:
            typer.echo(
                f"Accès consommé mais dataset inutilisable : {exc}\n"
                f"Compteur d'accès de '{strategy_id}' : {lockbox.access_count(strategy_id)}",
                err=True,
            )
            raise typer.Exit(code=2) from exc
        count = lockbox.access_count(strategy_id)
        flagged = lockbox.is_flagged(strategy_id)

    typer.echo(f"Holdout ouvert : {selection.n_bars} barres, {selection.instrument_symbol}")
    typer.echo(f"Accès holdout de '{strategy_id}' : {count}")
    if flagged:
        typer.echo(
            f"DRAPEAU ROUGE : {count} accès au holdout (seuil {RED_FLAG_THRESHOLD}). "
            "Chaque accès supplémentaire rend toute significativité mesurée sur ce "
            "holdout moins crédible.",
            err=True,
        )


config_app = typer.Typer(help="Clés API locales : stockage en 0600, hors du dépôt.")
app.add_typer(config_app, name="config")

CredentialsFileOption = Annotated[
    Path, typer.Option("--credentials-file", help="Fichier de clés local.")
]


@config_app.command("list")
def config_list(credentials_file: CredentialsFileOption = DEFAULT_CREDENTIALS_FILE) -> None:
    """Liste les emplacements de clés et leur provenance. N'affiche jamais une clé en clair."""
    store = CredentialStore(credentials_file)
    typer.echo(f"fichier : {store.path}\n")
    for status in describe(store):
        state = status.hint if status.configured else "—"
        wired = "" if status.wired else "  (lue par aucun module)"
        typer.echo(
            f"{status.env_var:<24} {state:<28} source={status.source:<12}{wired}\n"
            f"{'':<24} {status.label} — {status.description}"
        )


@config_app.command("set")
def config_set(
    env_var: Annotated[str, typer.Argument(help="Nom de la clé, ex. LSE_API_KEY.")],
    value: Annotated[
        str,
        typer.Option(
            "--value",
            prompt="Clé (masquée)",
            hide_input=True,
            help="Omis, la valeur est demandée sans être affichée ni conservée dans l'historique.",
        ),
    ],
    credentials_file: CredentialsFileOption = DEFAULT_CREDENTIALS_FILE,
) -> None:
    """Enregistre une clé dans le fichier local.

    `--value` est demandé en saisie masquée quand il n'est pas fourni : le
    passer en argument le laisserait dans l'historique du shell.
    """
    store = CredentialStore(credentials_file)
    try:
        store.set(env_var, value)
    except CredentialError as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"{env_var.strip()} enregistrée dans {store.path} ({mask(value.strip())})")
    if os.environ.get(env_var.strip(), "").strip():
        typer.echo(
            f"Attention : la variable d'environnement {env_var.strip()} est définie et "
            "gardera la priorité sur le fichier.",
            err=True,
        )


@config_app.command("unset")
def config_unset(
    env_var: Annotated[str, typer.Argument(help="Nom de la clé à supprimer.")],
    credentials_file: CredentialsFileOption = DEFAULT_CREDENTIALS_FILE,
) -> None:
    """Supprime une clé du fichier local. La variable d'environnement n'est pas touchée."""
    store = CredentialStore(credentials_file)
    try:
        removed = store.unset(env_var)
    except CredentialError as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not removed:
        typer.echo(f"{env_var} n'était pas enregistrée dans {store.path}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{env_var} supprimée de {store.path}")
