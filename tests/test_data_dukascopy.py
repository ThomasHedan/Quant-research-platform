"""Tests de edgelab.data.dukascopy (ingestion Dukascopy, Phase 1)."""

import lzma
import struct
from datetime import UTC, date, datetime, timedelta

import pytest
from edgelab.data.dukascopy import (
    aggregate_ticks_to_bars,
    build_tick_url,
    fetch_day_ticks,
    fetch_ticks,
    parse_bi5,
)

_TICK_STRUCT = struct.Struct(">IIIff")


def _compress(records: list[tuple[int, int, int, float, float]]) -> bytes:
    raw = b"".join(_TICK_STRUCT.pack(*r) for r in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def test_build_tick_url_encodes_month_zero_indexed() -> None:
    """Dukascopy encode le mois en base 0 : janvier apparaît comme `00` dans l'URL."""
    url = build_tick_url("EURUSD", date(2024, 1, 8), 10)

    assert "/2024/00/08/10h_ticks.bi5" in url


def test_build_tick_url_rejects_invalid_hour() -> None:
    """Une heure hors [0, 23] n'a pas de sens."""
    with pytest.raises(ValueError, match="hour"):
        build_tick_url("EURUSD", date(2024, 1, 8), 24)


def test_parse_bi5_decodes_records_relative_to_hour_start() -> None:
    """Chaque enregistrement est décalé en millisecondes depuis `hour_start`."""
    hour_start = datetime(2024, 1, 8, 10, tzinfo=UTC)
    compressed = _compress([(0, 108500, 108480, 1.5, 2.0), (15_000, 108520, 108500, 1.2, 1.8)])

    ticks = parse_bi5(compressed, hour_start=hour_start, point_value=100_000.0)

    assert ticks.height == 2
    assert ticks["timestamp"][0] == hour_start
    assert ticks["timestamp"][1] == hour_start + timedelta(seconds=15)


def test_parse_bi5_applies_point_value_to_raw_prices() -> None:
    """Le prix brut entier est divisé par `point_value` pour donner le prix réel."""
    hour_start = datetime(2024, 1, 8, 10, tzinfo=UTC)
    compressed = _compress([(0, 108500, 108480, 1.0, 1.0)])

    ticks = parse_bi5(compressed, hour_start=hour_start, point_value=100_000.0)

    assert ticks["ask"][0] == pytest.approx(1.085)
    assert ticks["bid"][0] == pytest.approx(1.0848)


def test_parse_bi5_handles_an_empty_hour() -> None:
    """Dukascopy renvoie un corps vide pour une heure sans tick — pas un flux LZMA valide."""
    ticks = parse_bi5(b"", hour_start=datetime(2024, 1, 8, 10, tzinfo=UTC), point_value=100_000.0)

    assert ticks.height == 0


def test_parse_bi5_rejects_a_corrupt_payload() -> None:
    """Un flux dont la taille n'est pas un multiple d'un enregistrement est corrompu."""
    corrupt = lzma.compress(b"not twenty bytes", format=lzma.FORMAT_ALONE)

    with pytest.raises(ValueError, match="corrupt"):
        parse_bi5(corrupt, hour_start=datetime(2024, 1, 8, 10, tzinfo=UTC), point_value=100_000.0)


def test_fetch_ticks_builds_url_and_delegates_to_the_injected_fetcher() -> None:
    """`fetch_ticks` construit l'URL et parse ce que renvoie le fetcher injecté."""
    compressed = _compress([(0, 108500, 108480, 1.0, 1.0)])
    seen_urls = []

    def fake_fetcher(url: str) -> bytes:
        seen_urls.append(url)
        return compressed

    ticks = fetch_ticks("EURUSD", date(2024, 1, 8), 10, point_value=100_000.0, fetcher=fake_fetcher)

    assert ticks.height == 1
    assert seen_urls == [build_tick_url("EURUSD", date(2024, 1, 8), 10)]


def test_fetch_day_ticks_concatenates_24_hourly_fetches() -> None:
    """`fetch_day_ticks` récupère et concatène les 24 fichiers horaires d'un jour."""
    compressed = _compress([(0, 108500, 108480, 1.0, 1.0)])
    call_count = 0

    def fake_fetcher(url: str) -> bytes:
        nonlocal call_count
        call_count += 1
        return compressed

    ticks = fetch_day_ticks("EURUSD", date(2024, 1, 8), point_value=100_000.0, fetcher=fake_fetcher)

    assert call_count == 24
    assert ticks.height == 24


def test_aggregate_ticks_to_bars_builds_ohlcv_from_mid_price() -> None:
    """L'agrégation en barres utilise le prix moyen (mid) et somme les volumes ask+bid."""
    hour_start = datetime(2024, 1, 8, 10, tzinfo=UTC)
    compressed = _compress(
        [
            (0, 108500, 108480, 1.0, 1.0),  # mid = 1.08490
            (10_000, 108600, 108580, 1.0, 1.0),  # mid = 1.08590 (high)
            (20_000, 108400, 108380, 1.0, 1.0),  # mid = 1.08390 (low)
            (30_000, 108550, 108530, 1.0, 1.0),  # mid = 1.08540 (close)
        ]
    )
    ticks = parse_bi5(compressed, hour_start=hour_start, point_value=100_000.0)

    bars = aggregate_ticks_to_bars(ticks, timedelta(minutes=1))

    assert bars.height == 1
    row = bars.row(0, named=True)
    assert row["open"] == pytest.approx(1.0849)
    assert row["high"] == pytest.approx(1.0859)
    assert row["low"] == pytest.approx(1.0839)
    assert row["close"] == pytest.approx(1.0854)
    assert row["volume"] == pytest.approx(8.0)


def test_aggregate_ticks_to_bars_rejects_non_positive_frequency() -> None:
    """Une fréquence nulle ou négative n'a pas de sens pour une agrégation en barres."""
    ticks = parse_bi5(
        _compress([(0, 108500, 108480, 1.0, 1.0)]),
        hour_start=datetime(2024, 1, 8, 10, tzinfo=UTC),
        point_value=100_000.0,
    )

    with pytest.raises(ValueError, match="frequency"):
        aggregate_ticks_to_bars(ticks, timedelta(0))
