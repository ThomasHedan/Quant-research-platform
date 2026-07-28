"""Ingestion Dukascopy (tick FX).

Le format `.bi5` est un détail d'implémentation Dukascopy, pas un protocole
stable : `parse_bi5` est une fonction pure (bytes -> DataFrame), testée sur
des flux synthétiques construits avec la même struct, sans jamais toucher au
réseau. Le seul point de contact réseau est `fetcher: Fetcher`, injecté en
paramètre — c'est la frontière d'effet de bord, tenue à l'écart du cœur pur
et testable (voir CLAUDE.md §6).
"""

from __future__ import annotations

import lzma
import struct
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import polars as pl

Fetcher = Callable[[str], bytes]
"""Récupère le contenu brut d'une URL. Point d'injection pour les tests."""

_TICK_STRUCT = struct.Struct(">IIIff")
"""time_delta_ms, ask_raw, bid_raw, ask_volume, bid_volume — big-endian, 20 octets."""

_MAX_HOUR = 23


def build_tick_url(symbol: str, day: date, hour: int) -> str:
    """URL du fichier `.bi5` Dukascopy pour `symbol`, `day`, `hour` (0-23, UTC).

    Dukascopy encode le mois en base 0 dans ses URLs (janvier = `00`) — un
    piège documenté de leur API, pas une erreur de ce module.
    """
    if not 0 <= hour <= _MAX_HOUR:
        raise ValueError(f"hour must be in [0, 23], got {hour}")
    return (
        f"https://datafeed.dukascopy.com/datafeed/{symbol}/"
        f"{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/{hour:02d}h_ticks.bi5"
    )


def parse_bi5(compressed: bytes, *, hour_start: datetime, point_value: float) -> pl.DataFrame:
    """Décompresse et parse un fichier `.bi5` en ticks (timestamp, ask, bid, volumes).

    `hour_start` est le début UTC de l'heure couverte par ce fichier : chaque
    enregistrement encode un décalage en millisecondes depuis ce point, pas
    un epoch absolu. `point_value` convertit les prix entiers bruts en prix
    réels (ex. `100000` pour un instrument à 5 décimales, `1000` pour un
    instrument à 3 décimales comme l'USDJPY).

    Raises:
        ValueError: si le flux décompressé n'est pas un multiple de la
            taille d'un enregistrement (20 octets) — fichier corrompu.
    """
    raw = lzma.decompress(compressed, format=lzma.FORMAT_ALONE) if compressed else b""
    if len(raw) % _TICK_STRUCT.size != 0:
        raise ValueError(
            f"corrupt bi5 payload: {len(raw)} bytes is not a multiple of {_TICK_STRUCT.size}"
        )

    rows = [
        (
            hour_start + timedelta(milliseconds=time_ms),
            ask_raw / point_value,
            bid_raw / point_value,
            float(ask_volume),
            float(bid_volume),
        )
        for time_ms, ask_raw, bid_raw, ask_volume, bid_volume in _TICK_STRUCT.iter_unpack(raw)
    ]
    return pl.DataFrame(
        rows,
        schema=["timestamp", "ask", "bid", "ask_volume", "bid_volume"],
        orient="row",
    )


def http_fetcher(url: str, *, timeout: float = 10.0) -> bytes:
    """Fetcher HTTP par défaut (stdlib `urllib`, aucune dépendance réseau ajoutée)."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()  # type: ignore[no-any-return]


def fetch_ticks(
    symbol: str, day: date, hour: int, *, point_value: float, fetcher: Fetcher
) -> pl.DataFrame:
    """Récupère et parse les ticks Dukascopy d'une heure donnée.

    `fetcher` est le point d'injection réseau : passer `http_fetcher` en
    production, une fonction de test qui renvoie des octets construits à la
    main en test.
    """
    url = build_tick_url(symbol, day, hour)
    compressed = fetcher(url)
    hour_start = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
    return parse_bi5(compressed, hour_start=hour_start, point_value=point_value)


def fetch_day_ticks(
    symbol: str, day: date, *, point_value: float, fetcher: Fetcher
) -> pl.DataFrame:
    """Récupère et concatène les ticks Dukascopy des 24 heures de `day` (UTC)."""
    frames = [
        fetch_ticks(symbol, day, hour, point_value=point_value, fetcher=fetcher)
        for hour in range(24)
    ]
    return pl.concat(frames)


def aggregate_ticks_to_bars(ticks: pl.DataFrame, frequency: timedelta) -> pl.DataFrame:
    """Agrège des ticks (ask/bid) en barres OHLCV au prix moyen (mid), pas `frequency`.

    Le volume de barre est la somme des volumes ask + bid des ticks agrégés.
    """
    if frequency <= timedelta(0):
        raise ValueError("frequency must be positive")
    every = f"{int(frequency.total_seconds())}s"
    return (
        ticks.with_columns(
            ((pl.col("ask") + pl.col("bid")) / 2).alias("_mid"),
            (pl.col("ask_volume") + pl.col("bid_volume")).alias("_volume"),
        )
        .sort("timestamp")
        .group_by_dynamic("timestamp", every=every)
        .agg(
            pl.col("_mid").first().alias("open"),
            pl.col("_mid").max().alias("high"),
            pl.col("_mid").min().alias("low"),
            pl.col("_mid").last().alias("close"),
            pl.col("_volume").sum().alias("volume"),
        )
    )
