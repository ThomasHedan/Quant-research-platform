"""Modèles de coût par instrument et par type d'ordre.

Le slippage dépend explicitement du type d'ordre : un ordre stop se
déclenche intra-barre, dans un mouvement qui vient de franchir son niveau —
il ne se remplit jamais mieux qu'un ordre déclenché à la clôture d'une
barre, qui connaît le prix exact avant d'agir. Confondre les deux rendrait
tout backtest sur stop artificiellement optimiste (voir CLAUDE.md §7).
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class OrderType(enum.StrEnum):
    """Type d'ordre, déterminant la politique de slippage applicable."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass(frozen=True)
class CostBreakdown:
    """Décomposition du coût d'un fill, en unités de prix de l'instrument."""

    spread: float
    commission: float
    slippage: float

    @property
    def total(self) -> float:
        """Coût total du fill, toutes composantes confondues."""
        return self.spread + self.commission + self.slippage


class CostModel(ABC):
    """Modèle de coût explicite par instrument.

    Sous-classer et implémenter `entry_cost` ; `round_trip_cost` en déduit le
    coût aller-retour (entrée + sortie) sans logique additionnelle à
    dupliquer par sous-classe.
    """

    @abstractmethod
    def entry_cost(self, *, order_type: OrderType, timestamp: datetime) -> CostBreakdown:
        """Coût d'un seul fill (entrée ou sortie), au type d'ordre et à l'instant donnés."""

    def round_trip_cost(self, *, order_type: OrderType, timestamp: datetime) -> CostBreakdown:
        """Coût d'un aller-retour complet (entrée + sortie au même type d'ordre)."""
        one_way = self.entry_cost(order_type=order_type, timestamp=timestamp)
        return CostBreakdown(
            spread=one_way.spread * 2,
            commission=one_way.commission * 2,
            slippage=one_way.slippage * 2,
        )


@dataclass(frozen=True)
class SlippageByOrderType:
    """Slippage forfaitaire (en unités de prix) par type d'ordre.

    `market` modélise un fill à la clôture de barre (slippage nul par
    défaut : le prix est connu avant l'action) ; `stop` modélise un
    déclenchement intra-barre dans un mouvement qui vient de franchir le
    niveau, donc un slippage strictement positif par défaut.
    """

    market: float = 0.0
    limit: float = 0.0
    stop: float = 0.0

    def for_order_type(self, order_type: OrderType) -> float:
        """Slippage applicable au type d'ordre donné."""
        return {
            OrderType.MARKET: self.market,
            OrderType.LIMIT: self.limit,
            OrderType.STOP: self.stop,
        }[order_type]


class FixedSpreadCost(CostModel):
    """Spread constant, quelle que soit l'heure de session."""

    def __init__(
        self,
        *,
        spread: float,
        commission: float,
        slippage: SlippageByOrderType,
    ) -> None:
        if spread < 0 or commission < 0:
            raise ValueError("spread and commission must be non-negative")
        self._spread = spread
        self._commission = commission
        self._slippage = slippage

    def entry_cost(self, *, order_type: OrderType, timestamp: datetime) -> CostBreakdown:
        return CostBreakdown(
            spread=self._spread / 2,
            commission=self._commission,
            slippage=self._slippage.for_order_type(order_type),
        )


class SessionSpreadCost(CostModel):
    """Spread modélisé par heure de session (heure UTC, 0-23).

    Les heures creuses (rollover asiatique, ouverture de semaine) élargissent
    typiquement le spread ; `spread_by_hour` doit couvrir les 24 heures,
    sans quoi une heure manquante lève explicitement plutôt que de retomber
    sur un défaut silencieux.
    """

    def __init__(
        self,
        *,
        spread_by_hour: dict[int, float],
        commission: float,
        slippage: SlippageByOrderType,
    ) -> None:
        missing = set(range(24)) - spread_by_hour.keys()
        if missing:
            raise ValueError(f"spread_by_hour missing hours: {sorted(missing)}")
        if any(s < 0 for s in spread_by_hour.values()) or commission < 0:
            raise ValueError("spread and commission must be non-negative")
        self._spread_by_hour = dict(spread_by_hour)
        self._commission = commission
        self._slippage = slippage

    def entry_cost(self, *, order_type: OrderType, timestamp: datetime) -> CostBreakdown:
        spread = self._spread_by_hour[timestamp.hour]
        return CostBreakdown(
            spread=spread / 2,
            commission=self._commission,
            slippage=self._slippage.for_order_type(order_type),
        )


class StressedCost(CostModel):
    """Enveloppe un `CostModel` et multiplie son coût par `multiplier` (défaut x2).

    Utilisé par le test de robustesse coûts x2 (Phase 4) : un edge qui ne
    survit pas à ce multiplicateur est trop fin pour être exploité.
    """

    def __init__(self, base: CostModel, multiplier: float = 2.0) -> None:
        if multiplier < 1:
            raise ValueError("multiplier must be >= 1 for a stress test")
        self._base = base
        self._multiplier = multiplier

    def entry_cost(self, *, order_type: OrderType, timestamp: datetime) -> CostBreakdown:
        base = self._base.entry_cost(order_type=order_type, timestamp=timestamp)
        return CostBreakdown(
            spread=base.spread * self._multiplier,
            commission=base.commission * self._multiplier,
            slippage=base.slippage * self._multiplier,
        )
