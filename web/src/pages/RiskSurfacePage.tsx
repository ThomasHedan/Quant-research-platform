import { useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import { bestRiskSurfacePoint, firstPhaseName } from "@/lib/derived"
import type { LeaderboardRow, RulesetSummary } from "@/lib/types"
import { ErrorState, LoadingState } from "@/components/DataState"
import { formatNumber, formatPct, StatCell } from "@/components/StatCell"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

/** Étiquette d'une stratégie dans le sélecteur : famille lisible + id technique. */
function strategyLabel(row: LeaderboardRow): string {
  return `${row.family} — ${row.strategy_id}`
}

/** Étiquette d'un ruleset, portant le statut de vérification en évidence dans la liste elle-même. */
function rulesetLabel(ruleset: RulesetSummary): string {
  const suffix = ruleset.is_verified ? "" : " — non vérifié"
  return `${ruleset.firm_name} — ${ruleset.ruleset_name}${suffix}`
}

/**
 * Vue « Surface de risque » (CLAUDE.md §4, Phase 8, vue 3).
 *
 * Le résultat que cette page rend visible est celui que Phase 5 désigne
 * comme le plus important produit par la plateforme : la courbe de
 * P(passage) en fonction du risque par trade est en cloche, et son optimum
 * se situe très en dessous du critère de Kelly, parce que la contrainte de
 * drawdown domine. La ligne Kelly est donc délibérément tracée même quand
 * elle sort largement du domaine où le risque a été balayé (0,25 %–2 %) —
 * c'est cet écart visuel qui est le message.
 */
export function RiskSurfacePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const strategyId = searchParams.get("strategy") ?? ""
  const rulesetId = searchParams.get("ruleset") ?? ""

  const strategies = useApi(() => api.listStrategies(), [])
  const rulesets = useApi(() => api.listRulesets(), [])

  // Pas de valeur par défaut choisie en silence : dès que les listes arrivent,
  // on fixe un choix explicite dans l'URL pour que la vue reste linkable.
  useEffect(() => {
    if (strategyId || !strategies.data || strategies.data.length === 0) return
    const next = new URLSearchParams(searchParams)
    next.set("strategy", strategies.data[0].strategy_id)
    setSearchParams(next, { replace: true })
  }, [strategyId, strategies.data, searchParams, setSearchParams])

  useEffect(() => {
    if (rulesetId || !rulesets.data || rulesets.data.length === 0) return
    // FTMO est le seul ruleset vérifié livré à ce jour (voir edgelab/propsim/rulesets) ;
    // les autres restent `unverified` et l'affichent quel que soit le défaut retenu.
    const preferred = rulesets.data.find((r) => r.id === "ftmo") ?? rulesets.data[0]
    const next = new URLSearchParams(searchParams)
    next.set("ruleset", preferred.id)
    setSearchParams(next, { replace: true })
  }, [rulesetId, rulesets.data, searchParams, setSearchParams])

  const selectedRuleset = rulesets.data?.find((r) => r.id === rulesetId)
  const phase = selectedRuleset ? firstPhaseName(selectedRuleset) : undefined
  const canFetchSurface = Boolean(strategyId && rulesetId && phase)

  const riskSurface = useApi(
    () =>
      canFetchSurface
        ? api.getRiskSurface(strategyId, rulesetId, phase)
        : Promise.resolve(undefined),
    [strategyId, rulesetId, phase, canFetchSurface],
  )

  function updateParam(key: "strategy" | "ruleset", value: string) {
    const next = new URLSearchParams(searchParams)
    next.set(key, value)
    setSearchParams(next)
  }

  const noStrategies = !strategies.loading && !strategies.error && strategies.data?.length === 0

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Surface de risque</h1>
        <p className="text-sm text-muted-foreground max-w-[70ch]">
          P(passage) en fonction du risque par trade, balayé de 0,25 % à 2 %. Le point Kelly est
          affiché pour rendre visible l'écart avec l'optimum réel — la contrainte de drawdown
          domine toujours le critère de Kelly.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Stratégie
          </span>
          {strategies.loading ? (
            <LoadingState label="Chargement des stratégies…" />
          ) : strategies.error ? (
            <ErrorState error={strategies.error} />
          ) : (
            <Select
              value={strategyId || undefined}
              onValueChange={(value) => updateParam("strategy", value)}
              disabled={!strategies.data || strategies.data.length === 0}
            >
              <SelectTrigger className="min-w-64">
                <SelectValue placeholder="Sélectionner une stratégie" />
              </SelectTrigger>
              <SelectContent>
                {strategies.data?.map((row) => (
                  <SelectItem key={row.strategy_id} value={row.strategy_id}>
                    {strategyLabel(row)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Ruleset
          </span>
          {rulesets.loading ? (
            <LoadingState label="Chargement des rulesets…" />
          ) : rulesets.error ? (
            <ErrorState error={rulesets.error} />
          ) : (
            <Select
              value={rulesetId || undefined}
              onValueChange={(value) => updateParam("ruleset", value)}
              disabled={!rulesets.data || rulesets.data.length === 0}
            >
              <SelectTrigger className="min-w-72">
                <SelectValue placeholder="Sélectionner un ruleset" />
              </SelectTrigger>
              <SelectContent>
                {rulesets.data?.map((ruleset) => (
                  <SelectItem key={ruleset.id} value={ruleset.id}>
                    {rulesetLabel(ruleset)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {selectedRuleset && !selectedRuleset.is_verified ? (
          <Badge variant="destructive" className="mb-[3px]">
            ruleset non vérifié — source non confirmée
          </Badge>
        ) : null}
      </div>

      {noStrategies ? (
        <p className="text-sm text-muted-foreground">
          Aucune stratégie enregistrée. Lance un backtest via le CLI pour en faire apparaître ici.
        </p>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Courbe P(passage) vs risque par trade</CardTitle>
            <CardDescription>
              {selectedRuleset
                ? `${selectedRuleset.firm_name} — ${selectedRuleset.ruleset_name}, palier « ${phase} »`
                : "Sélectionne une stratégie et un ruleset."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            {!canFetchSurface ? (
              <p className="text-sm text-muted-foreground">
                En attente d'une stratégie et d'un ruleset sélectionnés.
              </p>
            ) : riskSurface.loading ? (
              <LoadingState label="Calcul de la surface de risque…" />
            ) : riskSurface.error ? (
              <ErrorState error={riskSurface.error} />
            ) : riskSurface.data ? (
              <RiskSurfaceChartAndStats result={riskSurface.data} />
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function RiskSurfaceChartAndStats({
  result,
}: {
  result: { points: { risk_per_trade_pct: number; p_pass: number }[]; kelly_fraction: number }
}) {
  const best = bestRiskSurfacePoint(result)
  const maxPointRisk = result.points.reduce(
    (m, p) => Math.max(m, p.risk_per_trade_pct),
    0,
  )
  // Le domaine X inclut délibérément le point de Kelly même s'il tombe très
  // au-delà du balayage 0,25 %-2 % : c'est l'écart visuel qui porte le message.
  const xMax = Math.max(maxPointRisk, result.kelly_fraction) * 1.08
  const kellyOutOfSweep = result.kelly_fraction > maxPointRisk

  return (
    <div className="flex flex-col gap-6">
      <div style={{ width: "100%", height: 360 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={result.points} margin={{ top: 24, right: 24, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              type="number"
              dataKey="risk_per_trade_pct"
              domain={[0, xMax]}
              tickFormatter={(v: number) => formatPct(v, 2)}
              stroke="var(--color-muted-foreground)"
              tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
              label={{
                value: "risque par trade",
                position: "insideBottom",
                offset: -4,
                fontSize: 11,
                fill: "var(--color-muted-foreground)",
              }}
            />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v: number) => formatPct(v, 0)}
              stroke="var(--color-muted-foreground)"
              tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
              width={56}
              label={{
                value: "P(passage)",
                angle: -90,
                position: "insideLeft",
                fontSize: 11,
                fill: "var(--color-muted-foreground)",
              }}
            />
            <Tooltip
              formatter={(value) => formatPct(Number(value), 2)}
              labelFormatter={(label) => `risque par trade : ${formatPct(Number(label), 2)}`}
              contentStyle={{
                background: "var(--color-popover)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-sm)",
                fontSize: 12,
              }}
            />
            <ReferenceLine
              x={result.kelly_fraction}
              stroke="var(--color-muted-foreground)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: "Kelly",
                position: "top",
                fontSize: 11,
                fill: "var(--color-muted-foreground)",
              }}
            />
            <ReferenceDot
              x={best.risk_per_trade_pct}
              y={best.p_pass}
              r={5}
              fill="var(--color-foreground)"
              stroke="var(--color-background)"
              strokeWidth={2}
              label={{
                value: "optimum réel",
                position: "top",
                fontSize: 11,
                fill: "var(--color-foreground)",
              }}
            />
            <Line
              type="monotone"
              dataKey="p_pass"
              stroke="var(--color-foreground)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--color-foreground)" }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {kellyOutOfSweep ? (
        <p className="text-xs text-muted-foreground">
          Le critère de Kelly ({formatPct(result.kelly_fraction, 1)}) tombe hors du balayage
          testé (jusqu'à {formatPct(maxPointRisk, 2)}) : la ligne pointillée marque sa position
          réelle sur l'axe, bien au-delà de tout point mesuré — c'est l'écart que cette vue existe
          pour montrer.
        </p>
      ) : null}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-border pt-4">
        <StatCell label="Optimum réel — risque/trade" value={formatPct(best.risk_per_trade_pct, 2)} />
        <StatCell label="Optimum réel — P(passage)" value={formatPct(best.p_pass, 1)} />
        <StatCell label="Critère de Kelly (naïf)" value={formatPct(result.kelly_fraction, 1)} />
        <StatCell
          label="Optimum / Kelly"
          value={`${formatNumber((best.risk_per_trade_pct / result.kelly_fraction) * 100, 1)} %`}
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
              <th className="py-1.5 pr-4 font-medium">risque par trade</th>
              <th className="py-1.5 pr-4 font-medium">P(passage)</th>
            </tr>
          </thead>
          <tbody>
            {result.points.map((point) => {
              const isBest = point === best
              return (
                <tr
                  key={point.risk_per_trade_pct}
                  className={
                    isBest
                      ? "border-l-2 border-foreground bg-secondary/50"
                      : "border-l-2 border-transparent"
                  }
                >
                  <td className="num py-1 pr-4 pl-2">{formatPct(point.risk_per_trade_pct, 2)}</td>
                  <td className="num py-1 pr-4">{formatPct(point.p_pass, 2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
