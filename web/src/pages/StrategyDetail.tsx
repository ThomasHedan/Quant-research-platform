import { Link, useParams } from "react-router-dom"
import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import { edgeContributionPPass } from "@/lib/derived"
import { ErrorState, LoadingState } from "@/components/DataState"
import { KillCard } from "@/components/KillCard"
import { StatCell, formatNumber, formatPct } from "@/components/StatCell"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { EquityCurveChart } from "@/pages/strategy-detail/EquityCurveChart"
import { MonteCarloFanChart } from "@/pages/strategy-detail/MonteCarloFanChart"
import { CIStatTable } from "@/pages/strategy-detail/CIStatTable"
import { WalkForwardTable } from "@/pages/strategy-detail/WalkForwardTable"
import { isSignificantPValue, isLowPbo, isRobustDsr } from "@/pages/strategy-detail/significance"

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {description ? <p className="text-xs text-muted-foreground mt-0.5">{description}</p> : null}
      </div>
      {children}
    </section>
  )
}

/**
 * Fiche stratégie (CLAUDE.md §4, Phase 8, vue 2). La kill card est
 * délibérément le premier élément rendu, avant toute courbe d'equity :
 * "la question n'est pas « combien ça gagne » mais « qu'est-ce qui la
 * tuerait, et est-ce arrivé »."
 */
export function StrategyDetail() {
  const { strategyId } = useParams<{ strategyId: string }>()
  const bundle = useApi(() => api.getStrategy(strategyId ?? ""), [strategyId])
  const trials = useApi(() => api.getStrategyTrials(strategyId ?? ""), [strategyId])

  if (bundle.loading) return <LoadingState label="Chargement de la fiche stratégie…" />
  if (bundle.error) return <ErrorState error={bundle.error} />
  if (!bundle.data) return null

  const b = bundle.data

  return (
    <div className="flex flex-col gap-8 max-w-[900px]">
      <div>
        <p className="text-xs text-muted-foreground">
          {b.family} — {b.universe}
        </p>
        <h1 className="text-lg font-semibold tracking-tight num">{b.strategy_id}</h1>
      </div>

      {/* Compteur d'accès holdout (I3) : à côté de chaque stratégie, drapeau rouge à 3 accès. */}
      <div
        className={cn(
          "text-xs border rounded-md px-3 py-2 w-fit",
          b.holdout_flagged
            ? "border-destructive/50 bg-destructive/[0.06] text-destructive"
            : "border-border text-muted-foreground",
        )}
      >
        Accès holdout :{" "}
        <span className="num font-medium">{b.holdout_access_count}</span>
        {b.holdout_flagged ? " — seuil de 3 accès dépassé, drapeau rouge (I3)" : ""}
      </div>

      <KillCard hypothesis={b.hypothesis} verdict={b.kill_criteria_verdict} status={b.status} />

      <Section title="Courbe d'equity" description="Rendement cumulé, par trade.">
        <EquityCurveChart equityCurve={b.equity_curve} />
      </Section>

      <Section title="MAE / MFE" description="Excursions moyennes, calibrent le SL/TP — jamais un choix a priori.">
        <div className="grid grid-cols-2 gap-4 max-w-xs">
          <StatCell label="MAE moyenne" value={formatNumber(b.mae_mfe_mean_mae, 3)} />
          <StatCell label="MFE moyenne" value={formatNumber(b.mae_mfe_mean_mfe, 3)} />
        </div>
      </Section>

      <Section title="Stabilité par sous-période" description="Chronologique, quatre segments.">
        <CIStatTable
          labelHeader="Sous-période"
          rows={b.subperiod_stats.map((s) => ({
            key: s.label,
            label: s.label,
            stats: s.stats,
            t_stat: s.t_stat,
          }))}
        />
      </Section>

      <Section
        title="Régimes de volatilité réalisée"
        description="Pour comprendre, pas pour filtrer : un edge présent dans un seul régime est une hypothèse affaiblie."
      >
        <CIStatTable
          labelHeader="Tercile"
          rows={b.vol_regime_stats.map((v) => ({
            key: v.tercile,
            label: v.tercile,
            stats: v.stats,
            t_stat: v.t_stat,
          }))}
        />
      </Section>

      <Section title="Fan chart Monte Carlo" description="Percentiles p10 / p50 / p90 de trajectoire simulée (bootstrap par blocs).">
        <MonteCarloFanChart fan={b.monte_carlo_fan} />
      </Section>

      <Section
        title="Fenêtres de walk-forward"
        description="Paramètre sélectionné in-sample, performance mesurée uniquement sur la fenêtre suivante."
      >
        <WalkForwardTable result={b.walk_forward} />
      </Section>

      <Section
        title="Comparaison à la règle naïve de contrôle"
        description="Même information sans le déclencheur — si le déclencheur n'améliore pas significativement la naïve, ce résultat doit le dire."
      >
        <div className="grid grid-cols-2 gap-4 max-w-lg">
          <StatCell label="Déclencheur" value={formatNumber(b.naive_comparison.triggered.mean, 3)} ci={b.naive_comparison.triggered} />
          <StatCell label="Naïve (sans déclencheur)" value={formatNumber(b.naive_comparison.naive.mean, 3)} ci={b.naive_comparison.naive} />
        </div>
        <p className="text-xs">
          delta ={" "}
          <span className="num">{formatNumber(b.naive_comparison.mean_diff, 3)}</span>, p ={" "}
          <span
            className={cn(
              "num",
              isSignificantPValue(b.naive_comparison.p_value) && "text-signal-foreground bg-signal/70 px-1 rounded-sm",
            )}
          >
            {formatNumber(b.naive_comparison.p_value, 3)}
          </span>{" "}
          —{" "}
          {b.naive_comparison.improves_on_naive
            ? "améliore significativement la naïve"
            : "n'améliore pas significativement la naïve"}
        </p>
      </Section>

      <Section title="Décomposition par instrument de l'univers">
        <CIStatTable
          labelHeader="Instrument"
          rows={b.instrument_breakdown.map((i) => ({
            key: i.symbol,
            label: i.symbol,
            stats: i.stats,
            t_stat: i.t_stat,
            hitRate: i.hit_rate,
          }))}
        />
      </Section>

      <Separator />

      <Section
        title="Validation statistique"
        description="Bootstrap par blocs vs iid, permutation, DSR, PBO, sensibilité à la date de départ, coûts x2."
      >
        <div className="grid grid-cols-2 gap-x-8 gap-y-4">
          <div>
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Bootstrap : blocs vs iid
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <StatCell label="Max DD p95 (blocs)" value={formatNumber(b.bootstrap_comparison.block_max_drawdown_p95, 3)} />
              <StatCell label="Max DD p95 (iid)" value={formatNumber(b.bootstrap_comparison.iid_max_drawdown_p95, 3)} />
              <StatCell
                label="Ratio de sous-estimation (DD)"
                value={formatNumber(b.bootstrap_comparison.drawdown_underestimation_ratio, 2)}
              />
              <StatCell
                label="Ratio de sous-estimation (série de pertes)"
                value={formatNumber(b.bootstrap_comparison.streak_underestimation_ratio, 2)}
              />
            </div>
          </div>
          <div>
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Permutation &amp; robustesse
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <StatCell
                label="p-value permutation"
                value={formatNumber(b.permutation.p_value, 3)}
                significant={isSignificantPValue(b.permutation.p_value)}
              />
              <StatCell
                label="DSR"
                value={formatNumber(b.dsr.deflated_sharpe_ratio, 4)}
                significant={isRobustDsr(b.dsr.deflated_sharpe_ratio)}
              />
              <StatCell label="n_trials (registre)" value={b.dsr.n_trials} />
              <StatCell
                label="PBO"
                value={formatPct(b.pbo.probability_of_overfitting, 1)}
                significant={isLowPbo(b.pbo.probability_of_overfitting)}
              />
              <StatCell
                label="Coûts x2 : survit ?"
                value={b.costs_stress.survives_2x_costs ? "oui" : "non"}
              />
              <StatCell
                label="Écart-type sensibilité date de départ"
                value={formatNumber(b.start_date_sensitivity.std_final_return, 3)}
              />
            </div>
          </div>
        </div>
      </Section>

      <Section
        title="Propsim"
        description="P(passage) et baseline sans edge, jamais masquable — seule mesure honnête de la contribution réelle de l'edge."
      >
        <div className="grid grid-cols-2 gap-4 max-w-lg">
          <StatCell
            label={`P(passage) — ${b.propsim.strategy.firm_name}`}
            value={formatPct(b.propsim.strategy.p_pass, 1)}
          />
          <StatCell label="P(passage) baseline sans edge" value={formatPct(b.propsim.baseline.p_pass, 1)} />
        </div>
        <p className="text-xs">
          contribution de l'edge (delta P(passage)) ={" "}
          <span className="num text-signal-foreground bg-signal/70 px-1 rounded-sm">
            {formatPct(edgeContributionPPass(b.propsim), 1)}
          </span>
        </p>
        <p className="text-xs">
          <Link to={`/risk-surface?strategy=${b.strategy_id}`} className="underline underline-offset-2">
            voir la surface de risque complète →
          </Link>
        </p>
      </Section>

      <Separator />

      <Section title="Journal des essais liés" description="Registre append-only (I1) — rien n'est jamais supprimé.">
        {trials.loading ? (
          <LoadingState label="Chargement des essais…" />
        ) : trials.error ? (
          <ErrorState error={trials.error} />
        ) : trials.data && trials.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>id</TableHead>
                <TableHead>type</TableHead>
                <TableHead>créé</TableHead>
                <TableHead>lineage</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trials.data.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="num text-xs">{t.id}</TableCell>
                  <TableCell className="text-xs">{t.trial_type}</TableCell>
                  <TableCell className="num text-xs">
                    {new Date(t.created_at).toLocaleString("fr-FR")}
                  </TableCell>
                  <TableCell className="num text-xs text-muted-foreground">
                    {t.lineage_hash.slice(0, 10)}…
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">Aucun essai lié.</p>
        )}
      </Section>
    </div>
  )
}
