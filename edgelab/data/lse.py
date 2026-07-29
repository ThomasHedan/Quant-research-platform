"""Fournisseur London Strategic Edge : catalogue, barres paginées, export Parquet.

Le SDK officiel `lse-data` fait déjà le travail réseau (auth par `x-api-key`,
jobs d'export Parquet côté serveur, téléchargement avec reprise). Ce module ne
le réimplémente pas : il en isole le contrat derrière le protocole `LseClient`,
qui est le seul point de contact avec le réseau et donc le seul point à injecter
dans les tests — même frontière que `Fetcher` pour Dukascopy (CLAUDE.md §6).

Tout ce qui est en dessous de cette frontière est pur et testable sans réseau :
la normalisation des lignes du vault vers le schéma de barres d'EdgeLab, et la
pagination qui contourne le plafond de 5 000 lignes par appel de l'API.

Avertissement de fiabilité : le contrat exact du vault (noms de colonnes des
lignes renvoyées, format des horodatages) n'a **pas** été vérifié contre un
serveur réel — aucune clé API n'était disponible à la construction de ce module.
`normalise_candles` accepte donc plusieurs alias de colonnes plutôt que de
supposer un schéma unique, et lève une erreur explicite si aucun ne correspond.
Le premier appel avec une vraie clé est la vérification qui manque.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol, cast

import polars as pl

from edgelab.settings import resolve

logger = logging.getLogger(__name__)

API_KEY_ENV_VAR: Final = "LSE_API_KEY"
"""Nom de l'emplacement de clé. Résolu par `edgelab.settings` : variable d'environnement
d'abord, puis fichier local en 0600 — jamais versionné, jamais renvoyé par l'API."""

MAX_ROWS_PER_CALL: Final = 5_000
"""Plafond dur de l'endpoint `/vault/candles`. Au-delà, il faut paginer."""

TIMEFRAMES: Final[dict[str, timedelta]] = {
    "1s": timedelta(seconds=1),
    "5s": timedelta(seconds=5),
    "15s": timedelta(seconds=15),
    "30s": timedelta(seconds=30),
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1mo": timedelta(days=30),
}
"""Les quatorze résolutions du vault, associées à leur pas nominal.

`1mo` est approximé à 30 jours : c'est un pas nominal servant à la pagination et
au contrôle d'intégrité, pas un calendrier. Une barre mensuelle n'a pas de pas
constant et n'a de toute façon aucun usage en recherche intraday ici.
"""

_EPOCH_MILLISECONDS_THRESHOLD: Final = 1e11
"""Au-delà, un epoch numérique est en millisecondes : lu en secondes il tomberait après 2286."""

_TIMESTAMP_ALIASES: Final = ("timestamp", "ts", "time", "datetime", "bar_time")
_OHLCV_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "volume": ("volume", "v"),
}


class LseDataError(RuntimeError):
    """Levée quand une réponse du fournisseur ne peut pas être interprétée comme des barres."""


class LseClient(Protocol):
    """Le sous-ensemble de `lse.LSE` dont EdgeLab dépend.

    Déclaré comme protocole et non importé du SDK pour deux raisons : le SDK
    reste une dépendance optionnelle, et les tests injectent un client factice
    sans jamais toucher au réseau.
    """

    def catalog(self, category: str | None = None) -> list[dict[str, Any]]:
        """Un dict par (dataset, symbole) présent dans le vault."""
        ...

    def candles(  # noqa: PLR0913, PLR0917 — la signature est celle du SDK, pas un choix d'EdgeLab
        self,
        symbol: str,
        timeframe: str = "1m",
        start: str | None = None,
        end: str | None = None,
        limit: int = MAX_ROWS_PER_CALL,
        order: str = "asc",
        dataset: str | None = None,
    ) -> list[dict[str, Any]]:
        """Barres OHLCV, au plus `limit` lignes (plafonnées à 5 000 côté serveur)."""
        ...

    def history(  # noqa: PLR0913 — la signature est celle du SDK, pas un choix d'EdgeLab
        self,
        symbol: str | None = None,
        *,
        dataset: str | None = None,
        timeframe: str = "tick",
        start: str | None = None,
        end: str | None = None,
        dest: str | None = None,
        dataframe: bool = True,
    ) -> Any:  # noqa: ANN401 — renvoie un DataFrame pandas ou un chemin selon `dataframe`
        """Job d'export Parquet côté serveur, puis téléchargement avec reprise."""
        ...


class _TranslatingClient:
    """Enveloppe le client du SDK pour convertir ses erreurs en `LseDataError`.

    Le SDK lève `lse.LSEError` sur tout non-2xx (clé invalide, quota dépassé,
    limite de débit, table interdite). Sans cette traduction, une clé expirée
    remonterait en traceback brut jusqu'au CLI, alors que le reste du module a
    déjà un type d'erreur que chaque appelant sait présenter proprement. La
    conversion vit ici, à la frontière réseau, et nulle part ailleurs.
    """

    def __init__(self, inner: object, error_type: type[Exception]) -> None:
        self._inner = inner
        self._error_type = error_type

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 — proxy transparent
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def _call(*args: object, **kwargs: object) -> Any:  # noqa: ANN401 — proxy transparent
            try:
                return attribute(*args, **kwargs)
            except self._error_type as exc:
                raise LseDataError(f"London Strategic Edge a refusé l'appel : {exc}") from exc

        return _call


def open_client(api_key: str | None = None) -> LseClient:
    """Construit un vrai client LSE. Seule fonction du module qui touche au réseau.

    L'import du SDK est paresseux pour que `lse-data` reste une dépendance
    optionnelle : tout le reste d'EdgeLab, y compris les tests de ce module,
    fonctionne sans qu'il soit installé.

    La clé vient, dans l'ordre : l'argument, la variable d'environnement, puis le
    fichier de clés local (`edgelab.settings`). Aucune de ces valeurs n'est
    journalisée.

    Raises:
        LseDataError: si `lse-data` n'est pas installé, ou si aucune clé n'est
            trouvée par aucune de ces trois voies.
    """
    try:
        from lse import (  # noqa: PLC0415 — import paresseux : dépendance optionnelle
            LSE,
            LSEError,
        )
    except ImportError as exc:
        raise LseDataError(
            "le SDK London Strategic Edge n'est pas installé : `uv sync --extra lse`"
        ) from exc
    try:
        # Le SDK est typé (py.typed) quand il est installé ; sans lui, mypy voit Any
        # à travers l'override ignore_missing_imports. Le cast couvre les deux cas.
        client = LSE(api_key=api_key or resolve(API_KEY_ENV_VAR))
    except (ValueError, RuntimeError) as exc:
        raise LseDataError(
            f"clé API London Strategic Edge manquante : renseigner {API_KEY_ENV_VAR} "
            "dans la page Réglages ou via `edgelab config set` "
            "(clé gratuite sur londonstrategicedge.com/data)"
        ) from exc
    return cast(LseClient, _TranslatingClient(client, LSEError))


def _pick_column(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    return next((name for name in aliases if name in row), None)


def _parse_timestamp(value: Any) -> datetime:  # noqa: ANN401 — le vault mélange str et epoch
    """Interprète un horodatage du vault comme un `datetime` UTC conscient du fuseau.

    Le vault renvoie des chaînes ISO-8601 (le SDK y ajoute un `Z`), mais certains
    endpoints exposent des epochs. Les deux sont acceptés pour ne pas casser sur
    un détail de sérialisation qu'on ne peut pas vérifier sans clé.
    """
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        seconds = value / 1000.0 if value > _EPOCH_MILLISECONDS_THRESHOLD else float(value)
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T", 1))
        except ValueError as exc:
            raise LseDataError(
                f"horodatage illisible dans la réponse du vault : {value!r}"
            ) from exc
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise LseDataError(f"horodatage illisible dans la réponse du vault : {value!r}")


def normalise_candles(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Convertit des lignes du vault en barres au schéma d'EdgeLab, triées et dédupliquées.

    Fonction pure : c'est ici que le schéma incertain du fournisseur est réduit
    au schéma stable `REQUIRED_BAR_COLUMNS`. Le volume est mis à zéro quand il
    est absent — le FX du vault ne porte pas de volume consolidé, et un zéro
    explicite laisse le contrôle d'intégrité le signaler plutôt que de le cacher.

    Raises:
        LseDataError: si une colonne OHLC ou d'horodatage est introuvable.
    """
    if not rows:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        )

    head = rows[0]
    time_key = _pick_column(head, _TIMESTAMP_ALIASES)
    if time_key is None:
        raise LseDataError(
            f"aucune colonne d'horodatage dans la réponse du vault (colonnes : {sorted(head)})"
        )
    price_keys: dict[str, str] = {}
    for field, aliases in _OHLCV_ALIASES.items():
        key = _pick_column(head, aliases)
        if key is None and field != "volume":
            raise LseDataError(
                f"colonne '{field}' absente de la réponse du vault (colonnes : {sorted(head)})"
            )
        if key is not None:
            price_keys[field] = key

    records = [
        {
            "timestamp": _parse_timestamp(row[time_key]),
            "open": float(row[price_keys["open"]]),
            "high": float(row[price_keys["high"]]),
            "low": float(row[price_keys["low"]]),
            "close": float(row[price_keys["close"]]),
            "volume": float(row.get(price_keys.get("volume", ""), 0.0) or 0.0),
        }
        for row in rows
    ]
    return (
        pl.DataFrame(records)
        .with_columns(pl.col("timestamp").dt.convert_time_zone("UTC"))
        .unique(subset="timestamp", keep="first")
        .sort("timestamp")
    )


def fetch_candles(  # noqa: PLR0913 — chaque paramètre est une décision explicite requise
    client: LseClient,
    symbol: str,
    *,
    timeframe: str,
    start: datetime,
    end: datetime,
    dataset: str | None = None,
    max_calls: int = 500,
) -> pl.DataFrame:
    """Récupère toutes les barres de `start` à `end` en paginant sous le plafond de 5 000.

    L'API renvoie au plus 5 000 lignes par appel : demander « deux ans de M1 »
    en un coup renvoie silencieusement un début de série tronqué. Cette fonction
    boucle en avançant `start` d'un pas après la dernière barre reçue, et
    s'arrête dès qu'une page est incomplète ou que l'horodatage n'avance plus
    (garde-fou contre une boucle infinie si le serveur répète une page).

    `max_calls` borne le nombre de requêtes : un intervalle démesuré pour la
    résolution demandée doit échouer bruyamment, pas marteler l'API.

    Raises:
        ValueError: si `timeframe` n'est pas une résolution du vault ou si
            `start` n'est pas strictement antérieur à `end`.
        LseDataError: si `max_calls` est atteint avant la fin de l'intervalle.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe '{timeframe}' inconnu ; attendu l'un de {sorted(TIMEFRAMES)}")
    if start >= end:
        raise ValueError("start must be strictly before end")

    step = TIMEFRAMES[timeframe]
    cursor = start
    pages: list[pl.DataFrame] = []
    for call in range(max_calls):
        rows = client.candles(
            symbol,
            timeframe=timeframe,
            start=cursor.isoformat(),
            end=end.isoformat(),
            limit=MAX_ROWS_PER_CALL,
            order="asc",
            dataset=dataset,
        )
        page = normalise_candles(rows)
        if page.is_empty():
            break
        pages.append(page)
        last: datetime = page["timestamp"].max()  # type: ignore[assignment]
        next_cursor = last + step
        if len(rows) < MAX_ROWS_PER_CALL or next_cursor <= cursor or next_cursor >= end:
            break
        cursor = next_cursor
        logger.debug("lse candles page %d symbol=%s cursor=%s", call + 1, symbol, cursor)
    else:
        raise LseDataError(
            f"pagination interrompue après {max_calls} appels pour {symbol} en {timeframe} : "
            "restreindre l'intervalle ou passer par download_history (export Parquet)"
        )

    if not pages:
        return normalise_candles([])
    return (
        pl.concat(pages)
        .unique(subset="timestamp", keep="first")
        .sort("timestamp")
        .filter(pl.col("timestamp").is_between(start, end, closed="both"))
    )


def download_history(  # noqa: PLR0913 — chaque paramètre est une décision explicite requise
    client: LseClient,
    symbol: str,
    *,
    timeframe: str,
    start: datetime,
    end: datetime,
    dest: Path,
    dataset: str | None = None,
) -> Path:
    """Déclenche un export Parquet côté vault et renvoie le chemin du fichier téléchargé.

    C'est le chemin à privilégier au-delà de quelques dizaines de milliers de
    barres : le serveur construit le fichier, le client le télécharge avec
    reprise. `fetch_candles` reste le chemin interactif pour une inspection
    rapide.

    Raises:
        LseDataError: si le SDK ne renvoie pas un chemin de fichier existant.
    """
    dest.mkdir(parents=True, exist_ok=True)
    result = client.history(
        symbol,
        dataset=dataset,
        timeframe=timeframe,
        start=start.isoformat(),
        end=end.isoformat(),
        dest=str(dest),
        dataframe=False,
    )
    path = Path(str(result))
    if not path.is_file():
        raise LseDataError(f"l'export du vault n'a produit aucun fichier lisible : {result!r}")
    logger.info("lse export downloaded symbol=%s timeframe=%s path=%s", symbol, timeframe, path)
    return path


def load_history_parquet(path: Path) -> pl.DataFrame:
    """Relit un Parquet exporté par le vault et le ramène au schéma de barres d'EdgeLab."""
    frame = pl.read_parquet(path)
    return normalise_candles(frame.to_dicts())
