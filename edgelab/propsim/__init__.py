"""Simulateur de règles de prop firm : P(passage), surface de risque,
garde-fou de perte journalière (I5, fonction objectif du projet)."""

from edgelab.propsim.baseline import simulate_with_baseline, zero_edge_returns
from edgelab.propsim.loader import load_ruleset, load_shipped_rulesets
from edgelab.propsim.models import (
    ChallengePhase,
    DailyLossGuard,
    DrawdownBasis,
    DrawdownType,
    ProfitSplit,
    PropFirmRuleset,
    PropSimComparison,
    PropSimResult,
    Restrictions,
    RiskSurfacePoint,
    RiskSurfaceResult,
)
from edgelab.propsim.risk_surface import kelly_fraction, sweep_risk_surface
from edgelab.propsim.simulator import simulate_challenge, simulate_from_paths

__all__ = [
    "ChallengePhase",
    "DailyLossGuard",
    "DrawdownBasis",
    "DrawdownType",
    "ProfitSplit",
    "PropFirmRuleset",
    "PropSimComparison",
    "PropSimResult",
    "Restrictions",
    "RiskSurfacePoint",
    "RiskSurfaceResult",
    "kelly_fraction",
    "load_ruleset",
    "load_shipped_rulesets",
    "simulate_challenge",
    "simulate_from_paths",
    "simulate_with_baseline",
    "sweep_risk_surface",
    "zero_edge_returns",
]
