/**
 * Valeurs dérivées qui, côté Python, sont des `@property` non sérialisées
 * par Pydantic (voir `lib/types.ts`). Chaque fonction ici est le miroir
 * exact d'une propriété du backend — même nom de concept, même formule —
 * pour qu'aucune page ne la recalcule à sa façon et ne diverge des autres.
 */

import type {
  CorrelationMatrix,
  KillCriteriaVerdict,
  MarginalContribution,
  PropSimComparison,
  RiskSurfaceResult,
  RiskSurfacePoint,
  RulesetSummary,
  WalkForwardResult,
} from "./types"

/** Miroir de `KillCriteriaVerdict.any_triggered` (edgelab/validation/models.py). */
export function anyCriterionTriggered(verdict: KillCriteriaVerdict): boolean {
  return verdict.criteria.some((c) => c.triggered)
}

/** Miroir de `MarginalContribution.delta` (edgelab/portfolio/models.py). */
export function marginalDelta(contribution: MarginalContribution): number {
  return contribution.p_pass_with - contribution.p_pass_without
}

/** Miroir de `PropSimComparison.edge_contribution_p_pass` (edgelab/propsim/models.py). */
export function edgeContributionPPass(comparison: PropSimComparison): number {
  return comparison.strategy.p_pass - comparison.baseline.p_pass
}

/** Miroir de `RiskSurfaceResult.best_point` (edgelab/propsim/models.py). */
export function bestRiskSurfacePoint(result: RiskSurfaceResult): RiskSurfacePoint {
  return result.points.reduce((best, p) => (p.p_pass > best.p_pass ? p : best), result.points[0])
}

/** Miroir de `WalkForwardResult.n_windows` (edgelab/validation/models.py). */
export function nWalkForwardWindows(result: WalkForwardResult): number {
  return result.windows.length
}

/** Miroir de `CorrelationMatrix.correlation(a, b)` (edgelab/portfolio/models.py). */
export function correlationBetween(
  matrix: CorrelationMatrix,
  strategyA: string,
  strategyB: string,
): number {
  const i = matrix.strategy_ids.indexOf(strategyA)
  const j = matrix.strategy_ids.indexOf(strategyB)
  if (i === -1 || j === -1) {
    throw new Error(`stratégie inconnue de la matrice : ${strategyA} ou ${strategyB}`)
  }
  return matrix.matrix[i][j]
}

/** Miroir de `PropFirmRuleset.phase(name)` restreint aux noms de palier livrés par l'API. */
export function firstPhaseName(ruleset: RulesetSummary): string {
  return ruleset.phases[0]
}
