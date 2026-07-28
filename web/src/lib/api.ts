/**
 * Client HTTP contre edgelab/api. Aucune logique métier ici : chaque fonction
 * marshalle un endpoint vers son type de réponse, rien de plus — la même
 * règle que celle que l'API elle-même s'impose vis-à-vis du package Python.
 */

import type {
  AllocationSearchResult,
  CombinationResult,
  CorrelationMatrix,
  LeaderboardRow,
  PapersStatus,
  RiskSurfaceResult,
  RulesetSummary,
  StrategyBundle,
  Trial,
  TrialLink,
} from "./types"

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, params?: Record<string, string | string[]>): Promise<T> {
  const url = new URL(path, API_BASE)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const v of value) url.searchParams.append(key, v)
      } else {
        url.searchParams.set(key, value)
      }
    }
  }
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new ApiError(response.status, body.detail ?? response.statusText)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),

  listTrials: (strategyId?: string) =>
    request<Trial[]>("/api/trials", strategyId ? { strategy_id: strategyId } : undefined),
  trialCount: () => request<{ count: number }>("/api/trials/count"),
  getTrial: (trialId: string) => request<Trial>(`/api/trials/${encodeURIComponent(trialId)}`),

  listStrategies: () => request<LeaderboardRow[]>("/api/strategies"),
  getStrategy: (strategyId: string) =>
    request<StrategyBundle>(`/api/strategies/${encodeURIComponent(strategyId)}`),
  getStrategyTrials: (strategyId: string) =>
    request<TrialLink[]>(`/api/strategies/${encodeURIComponent(strategyId)}/trials`),
  getRiskSurface: (strategyId: string, ruleset?: string, phase?: string) =>
    request<RiskSurfaceResult>(`/api/strategies/${encodeURIComponent(strategyId)}/risk-surface`, {
      ...(ruleset ? { ruleset } : {}),
      ...(phase ? { phase } : {}),
    }),

  listRulesets: () => request<RulesetSummary[]>("/api/rulesets"),

  getPortfolioCorrelation: (strategyIds: string[]) =>
    request<CorrelationMatrix>("/api/portfolio/correlation", { strategy_ids: strategyIds }),
  getPortfolioCombination: (strategyIds: string[], ruleset?: string, phase?: string) =>
    request<CombinationResult>("/api/portfolio/combination", {
      strategy_ids: strategyIds,
      ...(ruleset ? { ruleset } : {}),
      ...(phase ? { phase } : {}),
    }),
  getOptimalAllocation: (strategyIds: string[], ruleset?: string, phase?: string) =>
    request<AllocationSearchResult>("/api/portfolio/optimize", {
      strategy_ids: strategyIds,
      ...(ruleset ? { ruleset } : {}),
      ...(phase ? { phase } : {}),
    }),

  getPapersStatus: () => request<PapersStatus>("/api/papers"),
}
