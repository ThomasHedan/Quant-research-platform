"""Univers nommés : `fx_majors`, `index_futures`, `energy_metals`, `broad_12`.

Avertissement de calibration : les spreads, commissions et slippages
attachés ici sont des valeurs illustratives choisies pour être plausibles et
plutôt pessimistes (elles ne doivent jamais sous-estimer le coût réel d'un
trade), pas des cotations vérifiées. Elles sont un point de départ à
recalibrer contre un relevé broker/vendeur réel avant tout backtest dont la
conclusion compterait — voir CLAUDE.md §7 (« hypothèse de coût » rendant un
backtest plus optimiste). Les coûts sont exprimés en unités de prix de
l'instrument, pas en devise.

Les calendriers de session simplifient les horaires réels : FX est modélisé
en semaine continue UTC (dimanche 22:00 -> vendredi 22:00) sans la brève
coupure de rollover quotidienne ; les futures CME sont modélisés de façon
analogue en heure locale `America/Chicago` (ce qui leur donne un
comportement DST authentique) sans la pause de maintenance quotidienne.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from edgelab.costs.models import FixedSpreadCost, SlippageByOrderType
from edgelab.universe.calendar import SessionCalendar, SessionWindow
from edgelab.universe.instrument import AssetClass, Instrument


def _continuous_week(timezone: str, *, sunday_open: time, friday_close: time) -> SessionCalendar:
    """Semaine de trading continue : dimanche `sunday_open` -> vendredi `friday_close`."""
    midnight = time(0, 0)
    windows = (
        SessionWindow(weekday=6, open=sunday_open, close=midnight),  # dimanche -> lundi 00:00
        SessionWindow(weekday=0, open=midnight, close=midnight),  # lundi (jour plein)
        SessionWindow(weekday=1, open=midnight, close=midnight),  # mardi (jour plein)
        SessionWindow(weekday=2, open=midnight, close=midnight),  # mercredi (jour plein)
        SessionWindow(weekday=3, open=midnight, close=midnight),  # jeudi (jour plein)
        SessionWindow(weekday=4, open=midnight, close=friday_close),  # vendredi -> clôture
    )
    return SessionCalendar(timezone=timezone, windows=windows)


_FX_CALENDAR = _continuous_week("UTC", sunday_open=time(22, 0), friday_close=time(22, 0))
_CME_CALENDAR = _continuous_week(
    "America/Chicago", sunday_open=time(17, 0), friday_close=time(16, 0)
)


def _fx_instrument(  # noqa: PLR0913 — un instrument a intrinsèquement ces attributs
    symbol: str, name: str, *, pip_size: float, decimals: int, spread: float, stop_slippage: float
) -> Instrument:
    return Instrument(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.FX,
        session_calendar=_FX_CALENDAR,
        cost_model=FixedSpreadCost(
            spread=spread,
            commission=0.0,
            slippage=SlippageByOrderType(market=0.0, limit=0.0, stop=stop_slippage),
        ),
        price_decimals=decimals,
        pip_size=pip_size,
    )


def _future_instrument(  # noqa: PLR0913 — un instrument a intrinsèquement ces attributs
    symbol: str,
    name: str,
    asset_class: AssetClass,
    *,
    tick_size: float,
    decimals: int,
    spread: float,
    commission: float,
    stop_slippage: float,
) -> Instrument:
    return Instrument(
        symbol=symbol,
        name=name,
        asset_class=asset_class,
        session_calendar=_CME_CALENDAR,
        cost_model=FixedSpreadCost(
            spread=spread,
            commission=commission,
            slippage=SlippageByOrderType(market=0.0, limit=0.0, stop=stop_slippage),
        ),
        price_decimals=decimals,
        pip_size=tick_size,
    )


EURUSD = _fx_instrument(
    "EURUSD", "Euro / Dollar US", pip_size=0.0001, decimals=5, spread=0.00010, stop_slippage=0.00005
)
GBPUSD = _fx_instrument(
    "GBPUSD",
    "Livre sterling / Dollar US",
    pip_size=0.0001,
    decimals=5,
    spread=0.00015,
    stop_slippage=0.00007,
)
USDJPY = _fx_instrument(
    "USDJPY",
    "Dollar US / Yen japonais",
    pip_size=0.01,
    decimals=3,
    spread=0.010,
    stop_slippage=0.005,
)
USDCHF = _fx_instrument(
    "USDCHF",
    "Dollar US / Franc suisse",
    pip_size=0.0001,
    decimals=5,
    spread=0.00015,
    stop_slippage=0.00007,
)
AUDUSD = _fx_instrument(
    "AUDUSD",
    "Dollar australien / Dollar US",
    pip_size=0.0001,
    decimals=5,
    spread=0.00012,
    stop_slippage=0.00006,
)
USDCAD = _fx_instrument(
    "USDCAD",
    "Dollar US / Dollar canadien",
    pip_size=0.0001,
    decimals=5,
    spread=0.00015,
    stop_slippage=0.00007,
)

ES = _future_instrument(
    "ES",
    "E-mini S&P 500",
    AssetClass.INDEX_FUTURE,
    tick_size=0.25,
    decimals=2,
    spread=0.25,
    commission=0.05,
    stop_slippage=0.25,
)
NQ = _future_instrument(
    "NQ",
    "E-mini Nasdaq 100",
    AssetClass.INDEX_FUTURE,
    tick_size=0.25,
    decimals=2,
    spread=0.25,
    commission=0.05,
    stop_slippage=0.50,
)
YM = _future_instrument(
    "YM",
    "E-mini Dow Jones",
    AssetClass.INDEX_FUTURE,
    tick_size=1.0,
    decimals=0,
    spread=1.0,
    commission=0.20,
    stop_slippage=2.0,
)

CL = _future_instrument(
    "CL",
    "WTI Crude Oil",
    AssetClass.ENERGY,
    tick_size=0.01,
    decimals=2,
    spread=0.02,
    commission=0.01,
    stop_slippage=0.03,
)
GC = _future_instrument(
    "GC",
    "Gold",
    AssetClass.METAL,
    tick_size=0.10,
    decimals=1,
    spread=0.20,
    commission=0.05,
    stop_slippage=0.30,
)
SI = _future_instrument(
    "SI",
    "Silver",
    AssetClass.METAL,
    tick_size=0.005,
    decimals=3,
    spread=0.010,
    commission=0.005,
    stop_slippage=0.015,
)


@dataclass(frozen=True)
class Universe:
    """Une liste nommée d'instruments, chacun portant son calendrier et son coût."""

    name: str
    instruments: tuple[Instrument, ...]

    def __post_init__(self) -> None:
        symbols = [i.symbol for i in self.instruments]
        if len(symbols) != len(set(symbols)):
            raise ValueError(f"universe '{self.name}' has duplicate instrument symbols")

    @property
    def symbols(self) -> tuple[str, ...]:
        """Symboles des instruments de l'univers, dans l'ordre de définition."""
        return tuple(i.symbol for i in self.instruments)

    def get(self, symbol: str) -> Instrument:
        """L'instrument `symbol` de l'univers.

        Raises:
            KeyError: si `symbol` n'appartient pas à cet univers.
        """
        for instrument in self.instruments:
            if instrument.symbol == symbol:
                return instrument
        raise KeyError(f"'{symbol}' not in universe '{self.name}'")


FX_MAJORS = Universe("fx_majors", (EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD))
INDEX_FUTURES = Universe("index_futures", (ES, NQ, YM))
ENERGY_METALS = Universe("energy_metals", (CL, GC, SI))
BROAD_12 = Universe(
    "broad_12", FX_MAJORS.instruments + INDEX_FUTURES.instruments + ENERGY_METALS.instruments
)

UNIVERSES: dict[str, Universe] = {
    u.name: u for u in (FX_MAJORS, INDEX_FUTURES, ENERGY_METALS, BROAD_12)
}


def get_universe(name: str) -> Universe:
    """L'univers nommé `name`.

    Raises:
        KeyError: si aucun univers ne porte ce nom.
    """
    try:
        return UNIVERSES[name]
    except KeyError as exc:
        available = ", ".join(sorted(UNIVERSES))
        raise KeyError(f"unknown universe '{name}' (available: {available})") from exc


def find_instrument(symbol: str) -> Instrument:
    """L'instrument `symbol`, cherché dans `broad_12` qui couvre tous les univers livrés.

    Sert aux frontières (CLI, API) où l'utilisateur nomme un instrument sans
    nommer d'univers. Le cœur du code, lui, reçoit toujours un `Instrument`
    déjà résolu.

    Raises:
        KeyError: si aucun instrument livré ne porte ce symbole.
    """
    try:
        return BROAD_12.get(symbol)
    except KeyError as exc:
        available = ", ".join(BROAD_12.symbols)
        raise KeyError(f"instrument '{symbol}' inconnu ; disponibles : {available}") from exc
