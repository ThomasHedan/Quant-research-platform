"""Futures continus : raccord de contrats successifs, méthode explicite obligatoire.

`roll_method` n'a pas de valeur par défaut dans `splice_continuous_future` :
un appelant qui ne choisit pas explicitement RATIO, DIFFERENCE ou NONE
n'obtient pas de comportement — il obtient une `TypeError` à l'appel. C'est
volontaire (CLAUDE.md Phase 1 : « paramètre obligatoire, pas de défaut
silencieux »), la méthode de raccord change matériellement la série de prix
et donc tout backtest construit dessus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import pairwise

import polars as pl

from edgelab.data.manifest import RollMethod

_ADJUSTED_COLUMNS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class FuturesContract:
    """Un contrat individuel contribuant à un future continu.

    `roll_date` est la dernière date (incluse) où ce contrat alimente la
    série continue ; au-delà, le contrat suivant prend le relais. `bars` est
    l'historique complet et non tronqué du contrat — la troncature aux
    bornes de roll est calculée par `splice_continuous_future`, qui a aussi
    besoin des bars *hors* de ces bornes pour lire le prix de recouvrement.
    """

    expiry: date
    roll_date: date
    bars: pl.DataFrame


def splice_continuous_future(
    contracts: list[FuturesContract], *, roll_method: RollMethod
) -> pl.DataFrame:
    """Raccorde une suite de contrats en une série continue selon `roll_method`.

    `contracts` doit être trié par `roll_date` strictement croissante, et
    chaque contrat doit avoir une barre à sa propre `roll_date` (le jour où
    l'ancien et le nouveau contrat sont tous deux cotés, utilisé pour
    calculer l'ajustement). `RATIO` et `DIFFERENCE` back-ajustent tout
    l'historique antérieur à chaque roll pour éliminer le saut de prix au
    changement de contrat (méthode Panama) ; `NONE` concatène les contrats
    tels quels, sauts inclus.

    Raises:
        ValueError: si `contracts` est vide, mal trié, ou si une `roll_date`
            n'a pas de barre correspondante dans l'ancien ou le nouveau
            contrat.
    """
    if not contracts:
        raise ValueError("contracts must not be empty")
    for previous, current in pairwise(contracts):
        if previous.roll_date >= current.roll_date:
            raise ValueError("contracts must be sorted by strictly increasing roll_date")

    n = len(contracts)
    segments: list[pl.DataFrame] = []
    for i, contract in enumerate(contracts):
        segment = contract.bars
        if i > 0:
            segment = segment.filter(pl.col("timestamp").dt.date() > contracts[i - 1].roll_date)
        if i < n - 1:
            segment = segment.filter(pl.col("timestamp").dt.date() <= contract.roll_date)
        segments.append(segment)

    if roll_method is RollMethod.NONE:
        return pl.concat(segments)

    adjusted_segments = [segments[-1]]
    cumulative = 1.0 if roll_method is RollMethod.RATIO else 0.0
    for i in range(n - 2, -1, -1):
        roll_date = contracts[i].roll_date
        old_at_roll = contracts[i].bars.filter(pl.col("timestamp").dt.date() == roll_date)
        new_at_roll = contracts[i + 1].bars.filter(pl.col("timestamp").dt.date() == roll_date)
        if old_at_roll.is_empty() or new_at_roll.is_empty():
            raise ValueError(
                f"no overlapping bar on roll_date {roll_date} to compute the roll adjustment"
            )
        old_close = float(old_at_roll["close"][-1])
        new_close = float(new_at_roll["close"][0])

        if roll_method is RollMethod.RATIO:
            if old_close == 0:
                raise ValueError("cannot compute a ratio adjustment against a zero close price")
            cumulative *= new_close / old_close
            adjusted = segments[i].with_columns(
                [(pl.col(c) * cumulative) for c in _ADJUSTED_COLUMNS]
            )
        else:  # RollMethod.DIFFERENCE
            cumulative += new_close - old_close
            adjusted = segments[i].with_columns(
                [(pl.col(c) + cumulative) for c in _ADJUSTED_COLUMNS]
            )
        adjusted_segments.insert(0, adjusted)

    return pl.concat(adjusted_segments)
