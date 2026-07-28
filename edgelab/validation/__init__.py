"""Bootstrap par blocs et iid, permutation, walk-forward, Deflated Sharpe
Ratio, PBO, évaluation des critères de mort."""

from edgelab.validation.bootstrap import (
    compare_block_vs_iid_bootstrap,
    longest_losing_streak,
    max_drawdown,
)
from edgelab.validation.dsr import deflated_sharpe_ratio, deflated_sharpe_ratio_from_registry
from edgelab.validation.kill_criteria import (
    DeadParentNotDeadError,
    StrategyLifecycleRepository,
    UnknownStrategyError,
    evaluate_kill_criteria,
)
from edgelab.validation.models import (
    BootstrapComparison,
    DeflatedSharpeResult,
    KillCriteriaVerdict,
    KillCriterionVerdict,
    PermutationTestResult,
)
from edgelab.validation.permutation import permutation_test

__all__ = [
    "BootstrapComparison",
    "DeadParentNotDeadError",
    "DeflatedSharpeResult",
    "KillCriteriaVerdict",
    "KillCriterionVerdict",
    "PermutationTestResult",
    "StrategyLifecycleRepository",
    "UnknownStrategyError",
    "compare_block_vs_iid_bootstrap",
    "deflated_sharpe_ratio",
    "deflated_sharpe_ratio_from_registry",
    "evaluate_kill_criteria",
    "longest_losing_streak",
    "max_drawdown",
    "permutation_test",
]
