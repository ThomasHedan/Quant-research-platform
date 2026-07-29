"""Tests des commandes `edgelab data *` (catalogue LSE, téléchargement, splits, holdout)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from edgelab import cli
from edgelab.cli import app
from edgelab.data.lse import LseDataError
from edgelab.universe import Instrument
from typer.testing import CliRunner

from tests.test_constants import RED_FLAG_ACCESS_COUNT
from tests.test_data_lse import FakeLseClient

runner = CliRunner()

_START = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture
def store_paths(tmp_path: Path) -> list[str]:
    """Les options de chemin de store à passer à chaque commande `data`."""
    return [
        "--catalog-path",
        str(tmp_path / "catalog.duckdb"),
        "--bars-dir",
        str(tmp_path / "bars"),
    ]


@pytest.fixture
def make_vault_bars(
    make_clean_bars: Callable[..., pl.DataFrame], eurusd: Instrument
) -> Callable[..., list[dict[str, Any]]]:
    """Factory produisant les lignes que le vault renverrait pour un EURUSD horaire propre.

    Les horodatages viennent du calendrier de session de l'instrument : le
    dataset passe le contrôle d'intégrité par construction. `drop_from`/`drop_to`
    creusent un trou de session pour exercer la quarantaine.
    """

    def _make(
        *,
        days: int = 20,
        drop_from: int | None = None,
        drop_to: int | None = None,
    ) -> list[dict[str, Any]]:
        bars = make_clean_bars(
            eurusd,
            start=_START,
            end=_START + timedelta(days=days),
            frequency=timedelta(hours=1),
        )
        if drop_from is not None and drop_to is not None:
            bars = pl.concat([bars[:drop_from], bars[drop_to:]])
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

    return _make


@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[object], None]:
    """Remplace la frontière réseau du CLI par un client factice."""

    def _patch(client: object) -> None:
        monkeypatch.setattr(cli, "open_client", lambda *_a, **_k: client)

    return _patch


# --- catalog -----------------------------------------------------------------


def test_data_catalog_lists_instruments_with_their_history_span(
    patch_client: Callable[[object], None],
) -> None:
    """`data catalog` montre la profondeur d'historique réelle de chaque symbole."""
    patch_client(
        FakeLseClient(
            catalog_rows=[
                {
                    "symbol": "EUR/USD",
                    "name": "Euro / US Dollar",
                    "category": "Forex",
                    "first": "2009-01-01T00:00:00Z",
                    "last": "2026-07-01T00:00:00Z",
                    "ticks": 1_234_567,
                }
            ]
        )
    )

    result = runner.invoke(app, ["data", "catalog"])

    assert result.exit_code == 0
    assert "EUR/USD" in result.stdout
    assert "2009-01-01" in result.stdout


def test_data_catalog_filters_on_the_search_term(
    patch_client: Callable[[object], None],
) -> None:
    """`--search` filtre sur le symbole comme sur le nom."""
    patch_client(
        FakeLseClient(
            catalog_rows=[
                {"symbol": "EUR/USD", "name": "Euro", "category": "Forex"},
                {"symbol": "BTC/USD", "name": "Bitcoin", "category": "Crypto"},
            ]
        )
    )

    result = runner.invoke(app, ["data", "catalog", "--search", "bitcoin"])

    assert result.exit_code == 0
    assert "BTC/USD" in result.stdout
    assert "EUR/USD" not in result.stdout


def test_data_catalog_reports_a_missing_api_key_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans clé API, la commande explique quoi faire et sort en erreur propre."""

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise LseDataError("clé API London Strategic Edge manquante : renseigner LSE_API_KEY")

    monkeypatch.setattr(cli, "open_client", _raise)

    result = runner.invoke(app, ["data", "catalog"])

    assert result.exit_code == 1
    assert "LSE_API_KEY" in result.output


# --- download ----------------------------------------------------------------


def _download_args(store_paths: list[str], *, days: int = 20) -> list[str]:
    end = _START + timedelta(days=days)
    return [
        "data",
        "download",
        "EUR/USD",
        "--instrument",
        "EURUSD",
        "--timeframe",
        "1h",
        "--start",
        _START.isoformat(),
        "--end",
        end.isoformat(),
        "--research-end",
        (_START + timedelta(days=days * 6 // 10)).isoformat(),
        "--validation-end",
        (_START + timedelta(days=days * 8 // 10)).isoformat(),
        *store_paths,
    ]


def test_data_download_ingests_bars_and_reports_every_split(
    patch_client: Callable[[object], None],
    make_vault_bars: Callable[..., list[dict[str, Any]]],
    store_paths: list[str],
) -> None:
    """Un téléchargement rapporte le dataset créé, son statut et la taille de chaque split."""
    patch_client(FakeLseClient([make_vault_bars()]))

    result = runner.invoke(app, _download_args(store_paths))

    assert result.exit_code == 0
    assert "dataset_id" in result.stdout
    assert "research=" in result.stdout
    assert "validation=" in result.stdout
    assert "holdout=" in result.stdout


def test_data_download_flags_a_quarantined_dataset_as_a_failure(
    patch_client: Callable[[object], None],
    make_vault_bars: Callable[..., list[dict[str, Any]]],
    store_paths: list[str],
) -> None:
    """Un trou de session dans les barres reçues part en quarantaine, et le CLI le dit.

    Le code de sortie 2 distingue « téléchargé mais inutilisable » de « échoué » :
    le dataset reste consultable pour diagnostic mais le backtester le refusera.
    """
    patch_client(FakeLseClient([make_vault_bars(drop_from=50, drop_to=90)]))

    result = runner.invoke(app, _download_args(store_paths))

    assert result.exit_code == 2
    assert "QUARANTAINE" in result.output


def test_data_download_rejects_an_unknown_instrument(store_paths: list[str]) -> None:
    """Un instrument absent des univers livrés est refusé avant tout appel réseau."""
    args = _download_args(store_paths)
    args[args.index("EURUSD")] = "DOGECOIN"

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert "inconnu" in result.output


def test_data_download_rejects_an_inverted_partition(
    patch_client: Callable[[object], None], store_paths: list[str]
) -> None:
    """Une fin de recherche postérieure à la fin de validation est refusée."""
    patch_client(FakeLseClient())
    args = _download_args(store_paths)
    args[args.index("--research-end") + 1] = (_START + timedelta(days=19)).isoformat()

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert "validation_end" in result.output


# --- list / show / holdout ---------------------------------------------------


@pytest.fixture
def ingested_dataset_id(
    patch_client: Callable[[object], None],
    make_vault_bars: Callable[..., list[dict[str, Any]]],
    store_paths: list[str],
) -> str:
    """Ingère un dataset propre via le CLI et renvoie son `dataset_id`."""
    patch_client(FakeLseClient([make_vault_bars()]))
    result = runner.invoke(app, _download_args(store_paths))
    line = next(row for row in result.stdout.splitlines() if row.startswith("dataset_id"))
    return line.split()[-1]


def test_data_list_shows_the_ingested_dataset(
    ingested_dataset_id: str, store_paths: list[str]
) -> None:
    """`data list` montre le dataset ingéré avec son statut."""
    result = runner.invoke(app, ["data", "list", *store_paths])

    assert result.exit_code == 0
    assert ingested_dataset_id[:12] in result.stdout


def test_data_list_reports_an_empty_store(store_paths: list[str]) -> None:
    """Un store vide le dit, plutôt que d'afficher un tableau sans ligne."""
    result = runner.invoke(app, ["data", "list", *store_paths])

    assert result.exit_code == 0
    assert "Aucun dataset" in result.stdout


def test_data_show_prints_the_manifest_and_the_split_boundaries(
    ingested_dataset_id: str, store_paths: list[str]
) -> None:
    """`data show` imprime le manifeste complet puis les bornes de chaque split."""
    result = runner.invoke(app, ["data", "show", ingested_dataset_id, *store_paths])

    assert result.exit_code == 0
    assert "integrity_report" in result.stdout
    assert "holdout" in result.stdout


def test_data_show_reports_an_unknown_dataset(store_paths: list[str]) -> None:
    """Un `dataset_id` inconnu sort en erreur nommée."""
    result = runner.invoke(app, ["data", "show", "n-existe-pas", *store_paths])

    assert result.exit_code == 1
    assert "introuvable" in result.output


def test_data_holdout_refuses_an_empty_reason(
    ingested_dataset_id: str, store_paths: list[str], tmp_path: Path
) -> None:
    """I3 : ouvrir le holdout sans raison écrite est refusé, et rien n'est compté."""
    result = runner.invoke(
        app,
        [
            "data",
            "holdout",
            ingested_dataset_id,
            "--strategy-id",
            "s1",
            "--reason",
            "   ",
            *store_paths,
            "--lockbox-path",
            str(tmp_path / "lockbox.sqlite3"),
        ],
    )

    assert result.exit_code == 1
    assert "refusé" in result.output


def test_data_holdout_opens_the_holdout_and_reports_the_counter(
    ingested_dataset_id: str, store_paths: list[str], tmp_path: Path
) -> None:
    """Une ouverture légitime du holdout affiche le nombre de barres et le compteur d'accès."""
    result = runner.invoke(
        app,
        [
            "data",
            "holdout",
            ingested_dataset_id,
            "--strategy-id",
            "s1",
            "--reason",
            "je veux voir",
            *store_paths,
            "--lockbox-path",
            str(tmp_path / "lockbox.sqlite3"),
        ],
    )

    assert result.exit_code == 0
    assert "Holdout ouvert" in result.stdout
    assert "Accès holdout de 's1' : 1" in result.stdout


def test_data_holdout_raises_the_red_flag_after_three_accesses(
    tmp_path: Path, store_paths: list[str], ingested_dataset_id: str
) -> None:
    """Trois accès au holdout déclenchent le drapeau rouge annoncé par I3."""
    dataset_id = ingested_dataset_id
    lockbox_args = ["--lockbox-path", str(tmp_path / "lockbox.sqlite3")]

    for i in range(RED_FLAG_ACCESS_COUNT):
        result = runner.invoke(
            app,
            [
                "data",
                "holdout",
                dataset_id,
                "--strategy-id",
                "s1",
                "--reason",
                f"accès {i}",
                *store_paths,
                *lockbox_args,
            ],
        )

    assert result.exit_code == 0
    assert "DRAPEAU ROUGE" in result.output
