"""Tests de edgelab.data.lse (fournisseur London Strategic Edge)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest
from edgelab.data.lse import (
    MAX_ROWS_PER_CALL,
    TIMEFRAMES,
    LseDataError,
    download_history,
    fetch_candles,
    load_history_parquet,
    normalise_candles,
    open_client,
)

from tests.test_constants import LSE_TIMEFRAME_COUNT


class FakeLseClient:
    """Client LSE factice : renvoie des pages préparées, sans jamais toucher au réseau."""

    def __init__(
        self,
        pages: list[list[dict[str, Any]]] | None = None,
        *,
        catalog_rows: list[dict[str, Any]] | None = None,
        export_path: Path | None = None,
    ) -> None:
        self.pages = pages or []
        self.catalog_rows = catalog_rows or []
        self.export_path = export_path
        self.calls: list[dict[str, Any]] = []

    def catalog(self, category: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self.catalog_rows if category is None or r.get("category") == category]

    def candles(self, symbol: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"symbol": symbol, **kwargs})
        index = len(self.calls) - 1
        return self.pages[index] if index < len(self.pages) else []

    def history(self, symbol: str | None = None, **kwargs: Any) -> Any:
        self.calls.append({"symbol": symbol, **kwargs})
        return str(self.export_path) if self.export_path else ""


@pytest.fixture
def make_vault_rows() -> Callable[..., list[dict[str, Any]]]:
    """Factory produisant des lignes de barres au schéma nominal du vault."""

    def _make(
        n: int,
        *,
        start: datetime = datetime(2024, 1, 1, tzinfo=UTC),
        step: timedelta = timedelta(hours=1),
        base: float = 100.0,
    ) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": (start + i * step).isoformat().replace("+00:00", "Z"),
                "open": base + i,
                "high": base + i + 0.5,
                "low": base + i - 0.5,
                "close": base + i + 0.2,
                "volume": 1_000.0,
            }
            for i in range(n)
        ]

    return _make


# --- normalise_candles -------------------------------------------------------


def test_normalise_candles_maps_the_nominal_vault_schema(
    make_vault_rows: Callable[..., list[dict[str, Any]]],
) -> None:
    """Le schéma nominal du vault se réduit exactement au schéma de barres d'EdgeLab."""
    rows = make_vault_rows(3)

    frame = normalise_candles(rows)

    assert frame.columns == ["timestamp", "open", "high", "low", "close", "volume"]
    assert frame.height == 3
    assert frame["timestamp"][0] == datetime(2024, 1, 1, tzinfo=UTC)


def test_normalise_candles_accepts_short_column_aliases() -> None:
    """Un vault qui renverrait `ts`/`o`/`h`/`l`/`c`/`v` est lu sans supposer un schéma unique."""
    rows = [{"ts": "2024-01-01 00:00:00", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10.0}]

    frame = normalise_candles(rows)

    assert frame["close"][0] == 1.5
    assert frame["timestamp"][0] == datetime(2024, 1, 1, tzinfo=UTC)


def test_normalise_candles_defaults_missing_volume_to_zero() -> None:
    """Le FX du vault ne porte pas de volume : un zéro explicite laisse l'intégrité le signaler."""
    rows = [
        {"timestamp": "2024-01-01T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}
    ]

    frame = normalise_candles(rows)

    assert frame["volume"][0] == 0.0


def test_normalise_candles_sorts_and_deduplicates_by_timestamp(
    make_vault_rows: Callable[..., list[dict[str, Any]]],
) -> None:
    """Deux pages qui se chevauchent ne doivent pas produire de barre en double."""
    rows = make_vault_rows(3)

    frame = normalise_candles([rows[2], rows[0], rows[1], rows[0]])

    assert frame.height == 3
    assert frame["timestamp"].is_sorted()


def test_normalise_candles_returns_a_typed_empty_frame_for_no_rows() -> None:
    """Zéro ligne renvoie un DataFrame vide mais typé, pas un DataFrame sans schéma."""
    frame = normalise_candles([])

    assert frame.is_empty()
    assert frame.columns == ["timestamp", "open", "high", "low", "close", "volume"]


def test_normalise_candles_rejects_rows_without_a_timestamp() -> None:
    """Une réponse sans colonne d'horodatage est une erreur explicite, pas un silence."""
    with pytest.raises(LseDataError, match="horodatage"):
        normalise_candles([{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}])


def test_normalise_candles_rejects_rows_without_a_close() -> None:
    """Une colonne OHLC manquante est nommée dans le message d'erreur."""
    with pytest.raises(LseDataError, match="'close' absente"):
        normalise_candles(
            [{"timestamp": "2024-01-01T00:00:00Z", "open": 1.0, "high": 2.0, "low": 1.0}]
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-01-01T00:00:00Z", datetime(2024, 1, 1, tzinfo=UTC)),
        ("2024-01-01 00:00:00", datetime(2024, 1, 1, tzinfo=UTC)),
        (1_704_067_200, datetime(2024, 1, 1, tzinfo=UTC)),
        (1_704_067_200_000, datetime(2024, 1, 1, tzinfo=UTC)),
        (datetime(2024, 1, 1), datetime(2024, 1, 1, tzinfo=UTC)),
    ],
)
def test_normalise_candles_reads_every_timestamp_encoding(raw: object, expected: datetime) -> None:
    """Chaînes ISO, epochs en secondes et en millisecondes donnent le même instant UTC."""
    frame = normalise_candles(
        [{"timestamp": raw, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0}]
    )

    assert frame["timestamp"][0] == expected


def test_normalise_candles_rejects_an_unreadable_timestamp() -> None:
    """Un horodatage illisible lève plutôt que de produire une barre à une date inventée."""
    with pytest.raises(LseDataError, match="illisible"):
        normalise_candles(
            [{"timestamp": "pas une date", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]
        )


def test_normalise_candles_rejects_a_timestamp_of_an_unexpected_type() -> None:
    """Un horodatage d'un type inattendu lève au lieu d'être converti au hasard."""
    with pytest.raises(LseDataError, match="illisible"):
        normalise_candles(
            [{"timestamp": ["2024"], "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]
        )


# --- fetch_candles : pagination ---------------------------------------------


def test_fetch_candles_returns_a_single_short_page_without_a_second_call(
    make_vault_rows: Callable[..., list[dict[str, Any]]],
) -> None:
    """Une page incomplète signifie « fin de série » : inutile de redemander."""
    client = FakeLseClient([make_vault_rows(10)])

    frame = fetch_candles(
        client,
        "EUR/USD",
        timeframe="1h",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 5, tzinfo=UTC),
    )

    assert frame.height == 10
    assert len(client.calls) == 1


def test_fetch_candles_pages_past_the_five_thousand_row_cap(
    make_vault_rows: Callable[..., list[dict[str, Any]]],
) -> None:
    """Au-delà du plafond de 5 000 lignes, la pagination reprend après la dernière barre reçue.

    C'est le piège de cette API : sans pagination, demander deux ans de M1
    renvoie silencieusement une série tronquée qui passerait pour complète.
    """
    start = datetime(2024, 1, 1, tzinfo=UTC)
    first_page = make_vault_rows(MAX_ROWS_PER_CALL, start=start)
    second_start = start + timedelta(hours=MAX_ROWS_PER_CALL)
    client = FakeLseClient([first_page, make_vault_rows(42, start=second_start)])

    frame = fetch_candles(
        client,
        "EUR/USD",
        timeframe="1h",
        start=start,
        end=start + timedelta(hours=MAX_ROWS_PER_CALL + 100),
    )

    assert len(client.calls) == 2
    assert frame.height == MAX_ROWS_PER_CALL + 42
    assert client.calls[1]["start"] == second_start.isoformat()


def test_fetch_candles_stops_when_the_cursor_stops_advancing(
    make_vault_rows: Callable[..., list[dict[str, Any]]],
) -> None:
    """Un serveur qui répète la même page pleine ne doit pas produire de boucle infinie."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    repeated = make_vault_rows(MAX_ROWS_PER_CALL, start=start)
    client = FakeLseClient([repeated] * 10)

    frame = fetch_candles(
        client,
        "EUR/USD",
        timeframe="1h",
        start=start,
        end=start + timedelta(days=3650),
    )

    assert len(client.calls) == 2
    assert frame.height == MAX_ROWS_PER_CALL


def test_fetch_candles_raises_when_the_call_budget_is_exhausted(
    make_vault_rows: Callable[..., list[dict[str, Any]]],
) -> None:
    """Un intervalle démesuré échoue bruyamment plutôt que de marteler l'API."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    pages = [
        make_vault_rows(MAX_ROWS_PER_CALL, start=start + timedelta(hours=MAX_ROWS_PER_CALL * i))
        for i in range(4)
    ]
    client = FakeLseClient(pages)

    with pytest.raises(LseDataError, match="pagination interrompue"):
        fetch_candles(
            client,
            "EUR/USD",
            timeframe="1h",
            start=start,
            end=start + timedelta(days=3650),
            max_calls=3,
        )


def test_fetch_candles_returns_an_empty_frame_when_the_vault_has_nothing() -> None:
    """Un symbole sans historique sur la période renvoie un DataFrame vide, pas une erreur."""
    client = FakeLseClient([[]])

    frame = fetch_candles(
        client,
        "EUR/USD",
        timeframe="1h",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
    )

    assert frame.is_empty()


def test_fetch_candles_rejects_an_unknown_timeframe() -> None:
    """Une résolution qui n'existe pas dans le vault est refusée avant tout appel réseau."""
    client = FakeLseClient()

    with pytest.raises(ValueError, match="timeframe '7m' inconnu"):
        fetch_candles(
            client,
            "EUR/USD",
            timeframe="7m",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )

    assert client.calls == []


def test_fetch_candles_rejects_an_inverted_interval() -> None:
    """Un intervalle inversé est une erreur d'appel, pas une plage vide."""
    with pytest.raises(ValueError, match="strictly before"):
        fetch_candles(
            FakeLseClient(),
            "EUR/USD",
            timeframe="1h",
            start=datetime(2024, 1, 2, tzinfo=UTC),
            end=datetime(2024, 1, 1, tzinfo=UTC),
        )


def test_the_vault_exposes_fourteen_resolutions() -> None:
    """Les quatorze résolutions documentées par le fournisseur sont toutes déclarées."""
    assert len(TIMEFRAMES) == LSE_TIMEFRAME_COUNT


# --- export Parquet ----------------------------------------------------------


def test_download_history_returns_the_downloaded_parquet_path(
    tmp_path: Path, make_vault_rows: Callable[..., list[dict[str, Any]]]
) -> None:
    """L'export bulk renvoie le chemin du fichier construit côté serveur."""
    artifact = tmp_path / "eurusd.parquet"
    normalise_candles(make_vault_rows(5)).write_parquet(artifact)
    client = FakeLseClient(export_path=artifact)

    path = download_history(
        client,
        "EUR/USD",
        timeframe="1h",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
        dest=tmp_path / "downloads",
    )

    assert path == artifact
    assert client.calls[0]["dataframe"] is False


def test_download_history_raises_when_the_export_produced_nothing(tmp_path: Path) -> None:
    """Un export qui ne produit aucun fichier est une erreur, pas un chemin fantôme."""
    client = FakeLseClient(export_path=tmp_path / "absent.parquet")

    with pytest.raises(LseDataError, match="aucun fichier"):
        download_history(
            client,
            "EUR/USD",
            timeframe="1h",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
            dest=tmp_path,
        )


def test_load_history_parquet_round_trips_a_vault_export(
    tmp_path: Path, make_vault_rows: Callable[..., list[dict[str, Any]]]
) -> None:
    """Un Parquet du vault se relit au schéma de barres d'EdgeLab, colonnes courtes comprises."""
    artifact = tmp_path / "raw.parquet"
    pl.DataFrame(
        [{"ts": datetime(2024, 1, 1, tzinfo=UTC), "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5}]
    ).write_parquet(artifact)

    frame = load_history_parquet(artifact)

    assert frame.columns == ["timestamp", "open", "high", "low", "close", "volume"]
    assert frame["close"][0] == 1.5


# --- frontière réseau --------------------------------------------------------


def test_open_client_reports_a_missing_sdk_as_an_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans le SDK optionnel, l'erreur dit quoi installer plutôt que de remonter une ImportError.

    `sys.modules["lse"] = None` fait échouer l'import comme si le paquet était
    absent, sans dépendre de l'état d'installation de l'environnement de test.
    """
    monkeypatch.setitem(sys.modules, "lse", None)

    with pytest.raises(LseDataError, match="uv sync --extra lse"):
        open_client()


def test_open_client_reports_a_missing_api_key_as_an_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le SDK refuse de se construire sans clé : l'erreur nomme la variable à renseigner."""

    class _SdkError(Exception):
        pass

    class _KeylessSdk:
        def __init__(self, **_kwargs: object) -> None:
            raise ValueError("no api key")

    monkeypatch.setitem(sys.modules, "lse", SimpleNamespace(LSE=_KeylessSdk, LSEError=_SdkError))

    with pytest.raises(LseDataError, match="LSE_API_KEY"):
        open_client()


def test_open_client_translates_provider_errors_into_lse_data_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une clé refusée par le vault remonte en `LseDataError`, jamais en traceback du SDK.

    Sans cette traduction à la frontière réseau, une clé expirée ferait exploser
    le CLI avec l'exception interne du SDK, que rien en amont ne sait présenter.
    """

    class _SdkError(Exception):
        pass

    class _RefusingSdk:
        tier = "free"

        def __init__(self, **_kwargs: object) -> None:
            pass

        def catalog(self, category: str | None = None) -> list[dict[str, Any]]:
            raise _SdkError("[401] invalid api key")

    monkeypatch.setitem(sys.modules, "lse", SimpleNamespace(LSE=_RefusingSdk, LSEError=_SdkError))

    client = open_client(api_key="peu-importe")

    with pytest.raises(LseDataError, match="invalid api key"):
        client.catalog()


def test_open_client_passes_non_callable_attributes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L'enveloppe reste transparente : un attribut simple du SDK est lisible tel quel."""

    class _SdkError(Exception):
        pass

    class _Sdk:
        tier = "premium"

        def __init__(self, **_kwargs: object) -> None:
            pass

    monkeypatch.setitem(sys.modules, "lse", SimpleNamespace(LSE=_Sdk, LSEError=_SdkError))

    client = open_client(api_key="peu-importe")

    assert client.tier == "premium"  # type: ignore[attr-defined]
