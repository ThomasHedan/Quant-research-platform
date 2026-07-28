/**
 * Types miroir des schémas Pydantic servis par edgelab/api (Phase 8).
 *
 * FastAPI + Pydantic v2 sérialise les champs tels quels (snake_case, pas de
 * conversion camelCase) : ces types collent exactement aux noms de champs
 * Python. Les `@property` Python (`any_triggered`, `delta`, `best_point`,
 * `edge_contribution_p_pass`, `n_windows`, `is_verified` sur les modèles
 * bruts, `.correlation()`) ne sont PAS sérialisées par `model_dump` — elles
 * sont recalculées côté front dans `lib/derived.ts`, jamais dupliquées ici.
 */

export type StrategyStatus = "candidate" | "dead" | "validated"
export type TrialType = "event_study" | "backtest" | "walk_forward" | "optimization"
export type Comparison = "less_than" | "greater_than"
export type PredictedDirection = "long" | "short" | "both"

export interface Trial {
  id: string
  created_at: string
  trial_type: TrialType
  strategy_id: string
  code_hash: string
  params: Record<string, unknown>
  params_hash: string
  dataset_hash: string
  lineage_hash: string
  metrics: Record<string, number>
  artifacts_path: string | null
  note: string
}

export interface TrialLink {
  id: string
  trial_type: string
  created_at: string
  lineage_hash: string
}

export interface KillCriterion {
  name: string
  metric: string
  comparison: Comparison
  threshold: number
  recorded_at: string
}

export interface HypothesisSheet {
  strategy_id: string
  economic_hypothesis: string
  predicted_direction: PredictedDirection
  predicted_amplitude_atr: number
  predicted_hit_rate: number
  predicted_horizon_bars: number
  where_it_should_not_work: string
  kill_criteria: KillCriterion[]
  parent_strategy_id: string | null
  created_at: string
}

export interface KillCriterionVerdict {
  criterion: KillCriterion
  measured_value: number | null
  triggered: boolean
}

export interface KillCriteriaVerdict {
  strategy_id: string
  criteria: KillCriterionVerdict[]
}

export interface ConfidenceInterval {
  mean: number
  ci_low: number
  ci_high: number
  n: number
}

export interface SubperiodPoint {
  label: string
  stats: ConfidenceInterval
  t_stat: number
}

export interface VolRegimePoint {
  tercile: "low" | "mid" | "high"
  stats: ConfidenceInterval
  t_stat: number
}

export interface InstrumentBreakdown {
  symbol: string
  stats: ConfidenceInterval
  t_stat: number
  hit_rate: number
}

export interface NaiveComparison {
  triggered: ConfidenceInterval
  naive: ConfidenceInterval
  mean_diff: number
  p_value: number
  improves_on_naive: boolean
}

export interface MonteCarloFan {
  trade_index: number[]
  p10: number[]
  p50: number[]
  p90: number[]
}

export interface BootstrapComparison {
  block_size: number
  n_resamples: number
  block_max_drawdown_p95: number
  iid_max_drawdown_p95: number
  drawdown_underestimation_ratio: number
  block_worst_streak_p95: number
  iid_worst_streak_p95: number
  streak_underestimation_ratio: number
}

export interface PermutationTestResult {
  observed_mean: number
  n_permutations: number
  p_value: number
}

export interface WalkForwardWindow {
  window_index: number
  selected_param: string
  in_sample_score: number
  out_of_sample_return: number
}

export interface WalkForwardResult {
  windows: WalkForwardWindow[]
  in_sample_size: number
  out_of_sample_size: number
  out_of_sample_mean_return: number
  out_of_sample_total_return: number
}

export interface DeflatedSharpeResult {
  observed_sharpe: number
  n_observations: number
  skewness: number
  kurtosis: number
  n_trials: number
  expected_max_sharpe_under_null: number
  sharpe_std_error: number
  deflated_sharpe_ratio: number
}

export interface PBOResult {
  n_partitions: number
  n_combinations: number
  probability_of_overfitting: number
  logits: number[]
}

export interface StartDateSensitivityResult {
  n_start_dates: number
  window_length: number
  final_returns: number[]
  mean_final_return: number
  std_final_return: number
  min_final_return: number
  max_final_return: number
}

export interface CostsStressResult {
  mean_return_net: number
  mean_return_stressed: number
  t_stat_net: number
  t_stat_stressed: number
  p_value_stressed: number
  survives_2x_costs: boolean
}

export interface PropSimResult {
  firm_name: string
  phase_name: string
  risk_per_trade_pct: number
  n_paths: number
  p_pass: number
  p_breach_daily_loss: number
  p_breach_max_drawdown: number
  median_days_to_target: number | null
  worst_day_pct_p95: number
}

export interface PropSimComparison {
  strategy: PropSimResult
  baseline: PropSimResult
}

export interface RiskSurfacePoint {
  risk_per_trade_pct: number
  p_pass: number
}

export interface RiskSurfaceResult {
  points: RiskSurfacePoint[]
  kelly_fraction: number
}

export interface LeaderboardRow {
  strategy_id: string
  family: string
  universe: string
  status: StrategyStatus
  n_trades: number
  net_expectancy_bps: number
  t_stat: number
  dsr: number
  pbo: number
  p_pass: number
  delta_vs_baseline_p_pass: number
  max_dd_p95: number
  worst_day_p95: number
  worst_streak_p95: number
  win_rate: number
  holdout_access_count: number
  holdout_flagged: boolean
}

export interface StrategyBundle {
  strategy_id: string
  family: string
  universe: string
  status: StrategyStatus
  lineage: string[]
  hypothesis: HypothesisSheet
  kill_criteria_verdict: KillCriteriaVerdict
  trade_r_multiples: number[]
  equity_curve: number[]
  mae_mfe_mean_mae: number
  mae_mfe_mean_mfe: number
  subperiod_stats: SubperiodPoint[]
  vol_regime_stats: VolRegimePoint[]
  naive_comparison: NaiveComparison
  instrument_breakdown: InstrumentBreakdown[]
  monte_carlo_fan: MonteCarloFan
  bootstrap_comparison: BootstrapComparison
  permutation: PermutationTestResult
  walk_forward: WalkForwardResult
  dsr: DeflatedSharpeResult
  pbo: PBOResult
  start_date_sensitivity: StartDateSensitivityResult
  costs_stress: CostsStressResult
  propsim: PropSimComparison
  risk_surface: RiskSurfaceResult
  ruleset_name: string
  holdout_access_count: number
  holdout_flagged: boolean
}

export interface RulesetSummary {
  id: string
  firm_name: string
  ruleset_name: string
  is_verified: boolean
  phases: string[]
}

export interface CorrelationMatrix {
  strategy_ids: string[]
  matrix: number[][]
}

export interface MarginalContribution {
  strategy_id: string
  p_pass_with: number
  p_pass_without: number
}

export interface CombinationResult {
  strategy_ids: string[]
  weights: Record<string, number>
  portfolio: PropSimResult
  correlation: CorrelationMatrix
  marginal_contributions: MarginalContribution[]
}

export interface AllocationSearchResult {
  weights: Record<string, number>
  portfolio: PropSimResult
  n_candidates_evaluated: number
}

export interface PapersStatus {
  implemented: boolean
  message: string
}
