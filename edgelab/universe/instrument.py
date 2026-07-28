"""Un instrument : son calendrier de session et son modèle de coût attachés.

Décision de design : un `Instrument` sans `CostModel` n'existe pas dans ce
module. `costs.CostModel` est une classe (spread/commission/slippage
paramétrés, pas des primitives Pydantic), donc `Instrument` est un
dataclass plutôt qu'un `BaseModel` — il n'a pas vocation à traverser une
frontière API telle quelle.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from edgelab.costs.models import CostModel
from edgelab.universe.calendar import SessionCalendar


class AssetClass(enum.StrEnum):
    """Classe d'actif d'un instrument, utilisée pour composer les univers."""

    FX = "fx"
    INDEX_FUTURE = "index_future"
    ENERGY = "energy"
    METAL = "metal"


@dataclass(frozen=True)
class Instrument:
    """Un instrument tradable : identité, session, coûts, convention de prix."""

    symbol: str
    name: str
    asset_class: AssetClass
    session_calendar: SessionCalendar
    cost_model: CostModel
    price_decimals: int
    pip_size: float

    def __post_init__(self) -> None:
        if self.price_decimals < 0:
            raise ValueError("price_decimals must be non-negative")
        if self.pip_size <= 0:
            raise ValueError("pip_size must be positive")
