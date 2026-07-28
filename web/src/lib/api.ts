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
  PaperRecord,
  PromptResponse,
  RiskSurfaceResult,
  RulesetSummary,
  StrategyBundle,
  TriageStatus,
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

/**
 * FastAPI renvoie `detail` en chaîne pour une `HTTPException` levée à la
 * main, mais en liste d'objets `{loc, msg, type}` pour une 422 de validation
 * Pydantic native — le cas attendu quand un JSON collé par l'utilisateur ne
 * respecte pas le schéma. Les deux formes doivent rester lisibles.
 */
function extractErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            const loc = "loc" in item && Array.isArray(item.loc) ? item.loc.join(".") : ""
            return loc ? `${loc}: ${String(item.msg)}` : String(item.msg)
          }
          return String(item)
        })
        .join(" ; ")
    }
  }
  return fallback
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
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, extractErrorMessage(body, response.statusText))
  }
  return response.json() as Promise<T>
}

/**
 * POST/PATCH avec un corps JSON. `body` est délibérément `unknown` : les
 * insertions du module papiers acceptent le JSON tel que collé par
 * l'utilisateur, non re-validé côté front — c'est `edgelab.papers` (via
 * l'API) qui porte la validation, jamais un schéma dupliqué ici.
 */
async function requestWithBody<T>(
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
): Promise<T> {
  const url = new URL(path, API_BASE)
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const responseBody = await response.json().catch(() => null)
    throw new ApiError(response.status, extractErrorMessage(responseBody, response.statusText))
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

  listPapers: () => request<PaperRecord[]>("/api/papers"),
  getPaper: (paperId: string) => request<PaperRecord>(`/api/papers/${encodeURIComponent(paperId)}`),
  createPaper: (payload: unknown) => requestWithBody<PaperRecord>("/api/papers", "POST", payload),
  getPaperAnalysisPrompt: () => request<PromptResponse>("/api/papers/prompt"),
  getPaperHypothesisPrompt: (paperId: string) =>
    request<PromptResponse>(`/api/papers/${encodeURIComponent(paperId)}/hypothesis-prompt`),
  attachPaperHypothesis: (paperId: string, payload: unknown) =>
    requestWithBody<PaperRecord>(
      `/api/papers/${encodeURIComponent(paperId)}/hypothesis`,
      "POST",
      payload,
    ),
  setPaperStatus: (paperId: string, status: TriageStatus, reason?: string) =>
    requestWithBody<PaperRecord>(`/api/papers/${encodeURIComponent(paperId)}/status`, "PATCH", {
      status,
      reason: reason ?? "",
    }),
}
