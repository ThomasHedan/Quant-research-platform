"""Règles de fill par type d'ordre (Phase 3).

Un ordre marché soumis pendant le traitement de la barre `t` se remplit à
l'ouverture de la barre `t+1` — jamais à la clôture de `t`, ce qui serait un
look-ahead déguisé (la stratégie a vu la clôture de `t` pour décider, elle ne
peut pas aussi y être remplie). Un ordre limite ou stop se remplit à son
niveau, ou à l'ouverture de la barre si celle-ci ouvre déjà au-delà (gap) —
jamais à un prix plus optimiste que ce que le marché offrait réellement.

Politique déclarée pour le cas ambigu (une position dont le stop ET le
take-profit sont tous deux dans le range d'une même barre) : le stop est
réputé toucher en premier — hypothèse conservatrice assumée par
construction, jamais un choix implicite favorable (CLAUDE.md §7). Elle est
appliquée par l'appelant (`backtest/engine.py`), pas par ce module : les
fonctions ici ne connaissent qu'un seul ordre à la fois.
"""

from __future__ import annotations

from edgelab.backtest.models import BarView, OrderSide


def fill_market_order(bar: BarView) -> float:
    """Un ordre marché soumis avant cette barre se remplit à son ouverture."""
    return bar.open


def fill_limit_order(bar: BarView, *, side: OrderSide, limit_price: float) -> float | None:
    """Fill au prix limite, ou à l'ouverture si la barre ouvre déjà au-delà (prix obtenu meilleur).

    `None` si le range de la barre ne touche jamais le prix limite : l'ordre
    reste en attente.
    """
    if side is OrderSide.BUY:
        if bar.low > limit_price:
            return None
        return min(bar.open, limit_price)
    if bar.high < limit_price:
        return None
    return max(bar.open, limit_price)


def fill_stop_order(bar: BarView, *, side: OrderSide, stop_price: float) -> float | None:
    """Fill au niveau stop, ou à l'ouverture si la barre ouvre déjà au-delà (gap, prix obtenu pire).

    `None` si le range de la barre ne touche jamais le niveau stop.
    """
    if side is OrderSide.BUY:
        if bar.high < stop_price:
            return None
        return max(bar.open, stop_price)
    if bar.low > stop_price:
        return None
    return min(bar.open, stop_price)
