"""Vue des barres qui garantit l'absence de look-ahead par construction (I4).

`bar_at` n'accepte qu'un décalage relatif `offset <= 0` : positif lève
`LookAheadError`, il n'y a donc aucune façon d'exprimer une demande de barre
future à travers cette API, pas seulement une discipline à respecter. Il
n'existe par ailleurs aucune méthode publique retournant le DataFrame complet
sous-jacent — c'est une garantie structurelle, pas une convention.
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from edgelab.backtest.models import BarView


class LookAheadError(Exception):
    """Levée quand du code tente de lire une barre postérieure au temps courant du moteur (I4)."""


class MarketView:
    """Vue des barres, une série par instrument, bornée au timestamp courant du moteur."""

    def __init__(self, bars_by_instrument: Mapping[str, pl.DataFrame]) -> None:
        self._bars = dict(bars_by_instrument)
        self._current_index = -1

    def advance(self, index: int) -> None:
        """Fait progresser l'index courant — appelé par `BacktestEngine` uniquement."""
        self._current_index = index

    @property
    def current_index(self) -> int:
        """Index de la barre courante."""
        return self._current_index

    def current_bar(self, instrument_symbol: str) -> BarView:
        """La barre courante de l'instrument nommé."""
        return self.bar_at(instrument_symbol, offset=0)

    def lookback(self, instrument_symbol: str, n: int) -> pl.DataFrame:
        """Les `n` dernières barres jusqu'à la courante incluse, jamais au-delà.

        Silencieusement bornée à ce qui est disponible si `n` dépasse
        l'historique connu (pas une erreur : le début d'un backtest a
        nécessairement moins de `n` barres derrière lui).

        Raises:
            ValueError: si `n` n'est pas strictement positif.
        """
        if n <= 0:
            raise ValueError("n must be positive")
        start = max(0, self._current_index - n + 1)
        return self._bars[instrument_symbol][start : self._current_index + 1]

    def bar_at(self, instrument_symbol: str, *, offset: int) -> BarView:
        """La barre à `offset` de la courante (0 = courante, négatif = passée).

        Raises:
            LookAheadError: si `offset` est strictement positif (I4).
            IndexError: si l'index résultant est négatif (aucune barre encore connue).
        """
        if offset > 0:
            raise LookAheadError("cannot access a bar with a positive (future) offset")
        index = self._current_index + offset
        if index < 0:
            raise IndexError("no bar available yet at this offset")
        row = self._bars[instrument_symbol].row(index, named=True)
        return BarView.model_validate(row)
