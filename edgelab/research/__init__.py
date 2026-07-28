"""Event study sans gestion de position : rendement forward, MAE/MFE,
stabilité, règle naïve de contrôle (I2 en amont du backtest)."""

from edgelab.research.event_study import MONO_INSTRUMENT_WARNING, run_event_study
from edgelab.research.models import (
    CONCENTRATION_MIN_T,
    AggregateHorizonStats,
    ConcentrationStats,
    EventStudyConfig,
    EventStudyReport,
    HorizonComparison,
    HorizonStats,
    InstrumentEventStudyResult,
    LagStats,
    MaeMfeStats,
    SubperiodStats,
    VolTercile,
)

__all__ = [
    "CONCENTRATION_MIN_T",
    "MONO_INSTRUMENT_WARNING",
    "AggregateHorizonStats",
    "ConcentrationStats",
    "EventStudyConfig",
    "EventStudyReport",
    "HorizonComparison",
    "HorizonStats",
    "InstrumentEventStudyResult",
    "LagStats",
    "MaeMfeStats",
    "SubperiodStats",
    "VolTercile",
    "run_event_study",
]
