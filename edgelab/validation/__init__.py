"""Bootstrap par blocs et iid, permutation, walk-forward, PBO, Deflated
Sharpe Ratio, sensibilité à la date de départ, coûts x2, évaluation des
critères de mort."""

from edgelab.validation.bootstrap import (
    compare_block_vs_iid_bootstrap,
    longest_losing_streak,
    max_drawdown,
)
from edgelab.validation.costs_stress import costs_stress_test
from edgelab.validation.dsr import deflated_sharpe_ratio, deflated_sharpe_ratio_from_registry
from edgelab.validation.kill_criteria import (
    DeadParentNotDeadError,
    StrategyLifecycleRepository,
    UnknownStrategyError,
    evaluate_kill_criteria,
)
from edgelab.validation.models import (
    BootstrapComparison,
    CostsStressResult,
    DeflatedSharpeResult,
    KillCriteriaVerdict,
    KillCriterionVerdict,
    PBOResult,
    PermutationTestResult,
    StartDateSensitivityResult,
    WalkForwardResult,
    WalkForwardWindow,
)
from edgelab.validation.pbo import probability_of_backtest_overfitting
from edgelab.validation.permutation import permutation_test
from edgelab.validation.start_date_sensitivity import start_date_sensitivity
from edgelab.validation.walk_forward import walk_forward

__all__ = [
    "BootstrapComparison",
    "CostsStressResult",
    "DeadParentNotDeadError",
    "DeflatedSharpeResult",
    "KillCriteriaVerdict",
    "KillCriterionVerdict",
    "PBOResult",
    "PermutationTestResult",
    "StartDateSensitivityResult",
    "StrategyLifecycleRepository",
    "UnknownStrategyError",
    "WalkForwardResult",
    "WalkForwardWindow",
    "compare_block_vs_iid_bootstrap",
    "costs_stress_test",
    "deflated_sharpe_ratio",
    "deflated_sharpe_ratio_from_registry",
    "evaluate_kill_criteria",
    "longest_losing_streak",
    "max_drawdown",
    "permutation_test",
    "probability_of_backtest_overfitting",
    "start_date_sensitivity",
    "walk_forward",
]
