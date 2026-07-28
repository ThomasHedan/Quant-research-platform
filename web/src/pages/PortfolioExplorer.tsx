import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"
import type {
  AllocationSearchResult,
  CombinationResult,
  CorrelationMatrix,
  LeaderboardRow,
  PropSimResult,
} from "@/lib/types"
import { useApi } from "@/hooks/useApi"
import { LoadingState, ErrorState } from "@/components/DataState"
import { formatNumber, formatPct, StatCell } from "@/components/StatCell"
import { DeadWrap } from "@/components/StatusBadge"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"

/** Signe explicite affiché en plus de la valeur — la delta marginale peut être négative et doit rester lisible comme telle, jamais adoucie. */
function formatSigned(value: number, digits = 3): string {
  const magnitude = formatNumber(Math.abs(value), digits)
  if (value > 0) return `+${magnitude}`
  if (value < 0) return `−${magnitude}`
  return magnitude
}

interface PortfolioResults {
  combination: CombinationResult
  allocation: AllocationSearchResult
}

function AllocationCard({
  title,
  description,
  weights,
  portfolio,
  byId,
}: {
  title: string
  description: string
  weights: Record<string, number>
  portfolio: PropSimResult
  byId: Map<string, LeaderboardRow>
}) {
  const entries = Object.entries(weights).sort((a, b) => b[1] - a[1])
  return (
    <Card className="rounded-none shadow-none">
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            P(passage) — {portfolio.firm_name} / {portfolio.phase_name}
          </span>
          <div className="num text-3xl font-semibold leading-tight">
            {formatPct(portfolio.p_pass, 1)}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <StatCell label="P(breach perte journalière)" value={formatPct(portfolio.p_breach_daily_loss)} />
          <StatCell label="P(breach DD max)" value={formatPct(portfolio.p_breach_max_drawdown)} />
          <StatCell
            label="Jours médians -> objectif"
            value={
              portfolio.median_days_to_target === null
                ? "—"
                : formatNumber(portfolio.median_days_to_target, 0)
            }
          />
          <StatCell label="Pire jour p95" value={formatPct(portfolio.worst_day_pct_p95)} />
        </div>
        <div>
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Pondération
          </span>
          <Table>
            <TableBody>
              {entries.map(([id, weight]) => {
                const row = byId.get(id)
                return (
                  <TableRow key={id}>
                    <TableCell className="py-1 pl-0">
                      <DeadWrap dead={row?.status === "dead"} className="text-sm">
                        {row?.family ?? id}
                      </DeadWrap>
                    </TableCell>
                    <TableCell className="num py-1 pr-0 text-right">{formatPct(weight)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function CorrelationMatrixView({
  correlation,
  byId,
}: {
  correlation: CorrelationMatrix
  byId: Map<string, LeaderboardRow>
}) {
  const label = (id: string) => byId.get(id)?.family ?? id
  return (
    <div>
      <h2 className="text-sm font-medium">Matrice de corrélation (par trade)</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Deux stratégies rentables mais corrélées peuvent subir une perte journalière le même jour
        — le propsim de portefeuille ne se substitue jamais à cette lecture.
      </p>
      <div className="mt-3 overflow-x-auto border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="border-r border-b border-border p-2 text-left" />
              {correlation.strategy_ids.map((id) => (
                <th
                  key={id}
                  className="border-b border-border p-2 text-left font-medium whitespace-nowrap"
                >
                  {label(id)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {correlation.matrix.map((row, i) => (
              <tr key={correlation.strategy_ids[i]}>
                <th className="border-r border-border p-2 text-left font-medium whitespace-nowrap">
                  {label(correlation.strategy_ids[i])}
                </th>
                {row.map((value, j) => (
                  <td
                    key={correlation.strategy_ids[j]}
                    className="num p-2 text-right"
                    style={{
                      backgroundColor: `color-mix(in oklch, var(--foreground) ${Math.round(Math.abs(value) * 26)}%, transparent)`,
                    }}
                  >
                    {formatNumber(value, 2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MarginalContributionsView({
  combination,
  byId,
}: {
  combination: CombinationResult
  byId: Map<string, LeaderboardRow>
}) {
  return (
    <div>
      <h2 className="text-sm font-medium">Contribution marginale au P(passage)</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Ajouter une stratégie peut faire baisser le score du portefeuille (poids égaux) — une
        contribution négative est un résultat, pas une anomalie à masquer.
      </p>
      <Table className="mt-3">
        <TableBody>
          <TableRow className="hover:bg-transparent">
            <TableCell className="pl-0 text-[11px] tracking-wide text-muted-foreground uppercase">
              Stratégie
            </TableCell>
            <TableCell className="text-right text-[11px] tracking-wide text-muted-foreground uppercase">
              P(passage) avec
            </TableCell>
            <TableCell className="text-right text-[11px] tracking-wide text-muted-foreground uppercase">
              P(passage) sans
            </TableCell>
            <TableCell className="pr-0 text-right text-[11px] tracking-wide text-muted-foreground uppercase">
              Δ P(passage)
            </TableCell>
          </TableRow>
          {combination.marginal_contributions.map((contribution) => {
            const row = byId.get(contribution.strategy_id)
            const delta = contribution.p_pass_with - contribution.p_pass_without
            return (
              <TableRow key={contribution.strategy_id}>
                <TableCell className="pl-0">
                  <DeadWrap dead={row?.status === "dead"} className="text-sm">
                    {row?.family ?? contribution.strategy_id}
                  </DeadWrap>
                </TableCell>
                <TableCell className="num text-right">
                  {formatPct(contribution.p_pass_with, 1)}
                </TableCell>
                <TableCell className="num text-right">
                  {formatPct(contribution.p_pass_without, 1)}
                </TableCell>
                <TableCell className="num pr-0 text-right font-medium">
                  {formatSigned(delta, 3)}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

export function PortfolioExplorer() {
  const {
    data: strategies,
    error: strategiesError,
    loading: strategiesLoading,
  } = useApi(() => api.listStrategies(), [])
  const {
    data: rulesets,
    error: rulesetsError,
    loading: rulesetsLoading,
  } = useApi(() => api.listRulesets(), [])

  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [rulesetId, setRulesetId] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (rulesetId !== undefined || !rulesets || rulesets.length === 0) return
    const ftmo = rulesets.find((r) => r.id === "ftmo")
    setRulesetId((ftmo ?? rulesets[0]).id)
  }, [rulesets, rulesetId])

  const byId = useMemo(
    () => new Map(strategies?.map((row) => [row.strategy_id, row]) ?? []),
    [strategies],
  )

  const [results, setResults] = useState<PortfolioResults | undefined>(undefined)
  const [resultsError, setResultsError] = useState<Error | undefined>(undefined)
  const [resultsLoading, setResultsLoading] = useState(false)

  useEffect(() => {
    // `explore_combination` exige au moins 2 stratégies (la contribution
    // marginale se mesure par exclusion, ce qui n'a pas de sens pour une
    // seule) — voir edgelab/portfolio/combination.py. En dessous, on
    // n'appelle pas l'API plutôt que de déclencher un 500 côté serveur.
    if (selectedIds.length < 2) {
      setResults(undefined)
      setResultsError(undefined)
      setResultsLoading(false)
      return
    }
    let cancelled = false
    setResultsLoading(true)
    setResultsError(undefined)
    Promise.all([
      api.getPortfolioCombination(selectedIds, rulesetId),
      api.getOptimalAllocation(selectedIds, rulesetId),
    ])
      .then(([combination, allocation]) => {
        if (cancelled) return
        setResults({ combination, allocation })
        setResultsLoading(false)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setResultsError(error instanceof Error ? error : new Error(String(error)))
        setResultsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedIds, rulesetId])

  function toggleStrategy(strategyId: string) {
    setSelectedIds((prev) =>
      prev.includes(strategyId) ? prev.filter((id) => id !== strategyId) : [...prev, strategyId],
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Explorateur de combinaisons</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sélection multiple de stratégies : P(passage) du portefeuille (I5), corrélation
          croisée et contribution marginale de chacune. Le propsim de portefeuille ne s'applique
          jamais aux stratégies isolées.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-4">
          <Card className="rounded-none shadow-none">
            <CardHeader>
              <CardTitle className="text-sm">Stratégies</CardTitle>
              <CardDescription>
                Les stratégies mortes restent sélectionnables — rien n'est jamais masqué.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-1">
              {strategiesLoading ? <LoadingState /> : null}
              {strategiesError ? <ErrorState error={strategiesError} /> : null}
              {strategies?.map((row) => (
                <label
                  key={row.strategy_id}
                  className="flex cursor-pointer items-start gap-2 rounded-sm py-1.5 focus-within:outline focus-within:outline-2 focus-within:outline-signal"
                >
                  <Checkbox
                    className="mt-0.5"
                    checked={selectedIds.includes(row.strategy_id)}
                    onCheckedChange={() => {
                      toggleStrategy(row.strategy_id)
                    }}
                  />
                  <DeadWrap dead={row.status === "dead"} className="flex flex-col">
                    <span className="text-sm">{row.family}</span>
                    <span className="num text-[11px] text-muted-foreground">
                      {row.strategy_id}
                    </span>
                  </DeadWrap>
                </label>
              ))}
            </CardContent>
          </Card>

          <Card className="rounded-none shadow-none">
            <CardHeader>
              <CardTitle className="text-sm">Ruleset</CardTitle>
              <CardDescription>Un ruleset non vérifié reste utilisable, signalé comme tel.</CardDescription>
            </CardHeader>
            <CardContent>
              {rulesetsLoading ? <LoadingState /> : null}
              {rulesetsError ? <ErrorState error={rulesetsError} /> : null}
              {rulesets ? (
                <Select value={rulesetId} onValueChange={setRulesetId}>
                  <SelectTrigger className="w-full rounded-none">
                    <SelectValue placeholder="Choisir un ruleset" />
                  </SelectTrigger>
                  <SelectContent>
                    {rulesets.map((ruleset) => (
                      <SelectItem key={ruleset.id} value={ruleset.id}>
                        {ruleset.firm_name} — {ruleset.ruleset_name}
                        {!ruleset.is_verified ? " (non vérifié)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          {selectedIds.length === 0 ? (
            <div className="border border-border p-8 text-center text-sm text-muted-foreground">
              Sélectionnez au moins une stratégie.
            </div>
          ) : selectedIds.length === 1 ? (
            <div className="border border-border p-8 text-center text-sm text-muted-foreground">
              Sélectionnez au moins une deuxième stratégie : la corrélation croisée et la
              contribution marginale n'ont pas de sens pour une stratégie isolée.
            </div>
          ) : resultsLoading ? (
            <LoadingState label="Simulation du portefeuille…" />
          ) : resultsError ? (
            <ErrorState error={resultsError} />
          ) : results ? (
            <>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <AllocationCard
                  title="Poids égaux"
                  description="Combinaison de référence : pondération identique par stratégie sélectionnée."
                  weights={results.combination.weights}
                  portfolio={results.combination.portfolio}
                  byId={byId}
                />
                <AllocationCard
                  title="Poids optimisés"
                  description={`Recherche de la pondération qui maximise P(passage) — pas le Sharpe ni le rendement espéré (${formatNumber(results.allocation.n_candidates_evaluated, 0)} candidats évalués).`}
                  weights={results.allocation.weights}
                  portfolio={results.allocation.portfolio}
                  byId={byId}
                />
              </div>

              <Separator />

              <CorrelationMatrixView correlation={results.combination.correlation} byId={byId} />

              <Separator />

              <MarginalContributionsView combination={results.combination} byId={byId} />
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
