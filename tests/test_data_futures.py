"""Tests de edgelab.data.futures (raccord de futures continus, Phase 1)."""

from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest
from edgelab.data.futures import FuturesContract, splice_continuous_future
from edgelab.data.manifest import RollMethod


def _daily_bars(
    start_day: int, num_days: int, base_price: float, offset: float = 0.0
) -> pl.DataFrame:
    rows = []
    price = base_price
    for d in range(num_days):
        ts = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=start_day + d)
        price += 1.0
        close = price + offset
        rows.append((ts, close, close + 0.1, close - 0.1, close, 1000.0))
    return pl.DataFrame(
        rows, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row"
    )


def _two_contracts(gap: float) -> list[FuturesContract]:
    """Deux contrats se recouvrant, avec un saut de prix de `gap` au roll."""
    bars_a = _daily_bars(0, 6, 100.0)  # 2024-01-01 .. 2024-01-06
    bars_b = _daily_bars(0, 9, 100.0, offset=gap)  # 2024-01-01 .. 2024-01-09, décalé de `gap`
    return [
        FuturesContract(expiry=date(2024, 1, 20), roll_date=date(2024, 1, 4), bars=bars_a),
        FuturesContract(expiry=date(2024, 2, 20), roll_date=date(2024, 1, 9), bars=bars_b),
    ]


def test_splice_rejects_empty_contract_list() -> None:
    """Une liste de contrats vide n'a pas de série continue possible."""
    with pytest.raises(ValueError, match="empty"):
        splice_continuous_future([], roll_method=RollMethod.NONE)


def test_splice_rejects_unsorted_contracts() -> None:
    """Les contrats doivent être triés par roll_date strictement croissante."""
    contracts = _two_contracts(gap=5.0)
    contracts.reverse()

    with pytest.raises(ValueError, match="sorted"):
        splice_continuous_future(contracts, roll_method=RollMethod.NONE)


def test_splice_none_does_not_adjust_any_price() -> None:
    """`NONE` est une concaténation brute : aucune valeur n'est modifiée."""
    contracts = _two_contracts(gap=5.0)

    spliced = splice_continuous_future(contracts, roll_method=RollMethod.NONE)

    assert spliced["close"][0] == pytest.approx(contracts[0].bars["close"][0])
    assert spliced["close"][-1] == pytest.approx(contracts[1].bars["close"][-1])


def test_splice_produces_no_duplicate_timestamps() -> None:
    """Aucune méthode de raccord ne doit produire d'horodatage dupliqué."""
    contracts = _two_contracts(gap=5.0)

    for method in RollMethod:
        spliced = splice_continuous_future(contracts, roll_method=method)
        assert spliced["timestamp"].n_unique() == spliced.height


def test_splice_ratio_removes_the_price_jump_at_the_roll_boundary() -> None:
    """`RATIO` back-ajuste l'historique : au roll, la série rejoint le niveau du nouveau contrat."""
    contracts = _two_contracts(gap=5.0)
    roll_date = contracts[0].roll_date

    spliced = splice_continuous_future(contracts, roll_method=RollMethod.RATIO)

    adjusted_at_roll = spliced.filter(pl.col("timestamp").dt.date() == roll_date)["close"][-1]
    new_raw_at_roll = contracts[1].bars.filter(pl.col("timestamp").dt.date() == roll_date)["close"][
        0
    ]
    assert adjusted_at_roll == pytest.approx(new_raw_at_roll)


def test_splice_difference_removes_the_price_jump_at_the_roll_boundary() -> None:
    """`DIFFERENCE` back-ajuste l'historique par une constante additive."""
    contracts = _two_contracts(gap=5.0)
    roll_date = contracts[0].roll_date

    spliced = splice_continuous_future(contracts, roll_method=RollMethod.DIFFERENCE)

    adjusted_at_roll = spliced.filter(pl.col("timestamp").dt.date() == roll_date)["close"][-1]
    new_raw_at_roll = contracts[1].bars.filter(pl.col("timestamp").dt.date() == roll_date)["close"][
        0
    ]
    assert adjusted_at_roll == pytest.approx(new_raw_at_roll)


def test_splice_ratio_applies_known_adjustment_to_older_history() -> None:
    """L'ajustement ratio appliqué à l'historique ancien correspond au calcul attendu."""
    contracts = _two_contracts(gap=5.0)
    roll_date = contracts[0].roll_date
    old_raw_first_close = contracts[0].bars["close"][0]
    old_close_at_roll = contracts[0].bars.filter(pl.col("timestamp").dt.date() == roll_date)[
        "close"
    ][-1]
    new_close_at_roll = contracts[1].bars.filter(pl.col("timestamp").dt.date() == roll_date)[
        "close"
    ][0]
    expected_ratio = new_close_at_roll / old_close_at_roll

    spliced = splice_continuous_future(contracts, roll_method=RollMethod.RATIO)

    adjusted_first_close = spliced["close"][0]
    assert adjusted_first_close == pytest.approx(old_raw_first_close * expected_ratio)


def test_splice_requires_an_overlapping_bar_on_the_roll_date() -> None:
    """Sans barre commune à la roll_date, l'ajustement ne peut pas être calculé."""
    bars_a = _daily_bars(0, 4, 100.0)  # 2024-01-01 .. 2024-01-04
    bars_b = _daily_bars(10, 4, 100.0)  # 2024-01-11 .. 2024-01-14 : pas de recouvrement
    contracts = [
        FuturesContract(expiry=date(2024, 1, 20), roll_date=date(2024, 1, 11), bars=bars_a),
        FuturesContract(expiry=date(2024, 2, 20), roll_date=date(2024, 2, 1), bars=bars_b),
    ]

    with pytest.raises(ValueError, match="overlapping"):
        splice_continuous_future(contracts, roll_method=RollMethod.RATIO)


def test_splice_ratio_chains_adjustments_across_three_contracts() -> None:
    """Le raccord ratio à trois contrats reste continu aux deux rolls, ajustement cumulé.

    Au premier roll (A -> B), la série doit rejoindre le niveau que B aurait
    lui-même après son propre ajustement au second roll (B -> C) — pas le
    prix brut de B, qui n'est lui-même pas encore au niveau de l'ancre C.
    """
    bars_a = _daily_bars(0, 4, 100.0)  # roll au jour 4 (2024-01-04)
    bars_b = _daily_bars(0, 7, 100.0, offset=2.0)  # roll au jour 7 (2024-01-07)
    bars_c = _daily_bars(0, 9, 100.0, offset=5.0)
    contracts = [
        FuturesContract(expiry=date(2024, 1, 20), roll_date=date(2024, 1, 4), bars=bars_a),
        FuturesContract(expiry=date(2024, 2, 20), roll_date=date(2024, 1, 7), bars=bars_b),
        FuturesContract(expiry=date(2024, 3, 20), roll_date=date(2024, 1, 9), bars=bars_c),
    ]

    spliced = splice_continuous_future(contracts, roll_method=RollMethod.RATIO)

    first_roll, second_roll = contracts[0].roll_date, contracts[1].roll_date
    b_raw_at_second_roll = contracts[1].bars.filter(pl.col("timestamp").dt.date() == second_roll)[
        "close"
    ][-1]
    c_raw_at_second_roll = contracts[2].bars.filter(pl.col("timestamp").dt.date() == second_roll)[
        "close"
    ][0]
    ratio_b_to_c = c_raw_at_second_roll / b_raw_at_second_roll

    adjusted_at_second_roll = spliced.filter(pl.col("timestamp").dt.date() == second_roll)["close"][
        -1
    ]
    assert adjusted_at_second_roll == pytest.approx(c_raw_at_second_roll)

    adjusted_at_first_roll = spliced.filter(pl.col("timestamp").dt.date() == first_roll)["close"][
        -1
    ]
    b_raw_at_first_roll = contracts[1].bars.filter(pl.col("timestamp").dt.date() == first_roll)[
        "close"
    ][0]
    assert adjusted_at_first_roll == pytest.approx(b_raw_at_first_roll * ratio_b_to_c)
