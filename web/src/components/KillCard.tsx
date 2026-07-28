import { cn } from "@/lib/utils"
import { formatNumber } from "@/components/StatCell"
import type { HypothesisSheet, KillCriteriaVerdict, StrategyStatus } from "@/lib/types"
import { anyCriterionTriggered } from "@/lib/derived"
import { StatusBadge } from "@/components/StatusBadge"

/**
 * L'élément signature d'EdgeLab (CLAUDE.md §4, Phase 8). En tête de chaque
 * fiche stratégie, avant toute courbe d'equity : la question n'est pas
 * « combien ça gagne » mais « qu'est-ce qui la tuerait, et est-ce arrivé ».
 * Chaque critère affiche son seuil, sa valeur mesurée courante et son état ;
 * un critère déclenché est barré en rouge et l'ensemble de la fiche hérite
 * de ce traitement dès qu'un seul l'est.
 */
export function KillCard({
  hypothesis,
  verdict,
  status,
}: {
  hypothesis: HypothesisSheet
  verdict: KillCriteriaVerdict
  status: StrategyStatus
}) {
  const dead = status === "dead" || anyCriterionTriggered(verdict)
  const verdictByMetric = new Map(verdict.criteria.map((v) => [v.criterion.name, v]))

  return (
    <section
      className={cn(
        "border rounded-md p-4",
        dead
          ? "border-destructive/60 border-l-4 border-l-destructive bg-destructive/[0.08]"
          : "border-border bg-card",
      )}
      aria-label="Critères de mort pré-enregistrés"
    >
      <header className="flex items-baseline justify-between gap-4 mb-3">
        <div>
          <h2 className="text-xs uppercase tracking-wide text-muted-foreground">
            Critères de mort — pré-enregistrés
          </h2>
          <p className="text-sm mt-1 max-w-2xl">{hypothesis.economic_hypothesis}</p>
        </div>
        <StatusBadge status={status} className="shrink-0" />
      </header>

      <dl className="grid gap-2">
        {hypothesis.kill_criteria.map((criterion) => {
          const v = verdictByMetric.get(criterion.name)
          const triggered = v?.triggered ?? false
          return (
            <div
              key={criterion.name}
              className={cn(
                "flex items-center justify-between gap-3 border-b border-border/60 py-1.5 last:border-b-0",
                triggered && "text-destructive line-through decoration-2",
              )}
            >
              <dt className="text-sm">{criterion.name}</dt>
              <dd className="num flex items-center gap-3 text-xs text-right shrink-0">
                <span className="text-muted-foreground">
                  {criterion.comparison === "less_than" ? "<" : ">"}{" "}
                  {formatNumber(criterion.threshold, 3)}
                </span>
                <span
                  className={cn(
                    "min-w-16 font-medium",
                    !triggered && v?.measured_value != null && "text-signal-foreground bg-signal/60 rounded-sm px-1",
                  )}
                >
                  {v?.measured_value != null ? formatNumber(v.measured_value, 3) : "—"}
                </span>
                <span
                  className={cn(
                    "rounded-sm px-1.5 py-0.5 text-[10px] uppercase",
                    triggered
                      ? "bg-destructive text-destructive-foreground"
                      : v?.measured_value != null
                        ? "border border-border text-muted-foreground"
                        : "border border-dashed border-border text-muted-foreground",
                  )}
                >
                  {triggered ? "déclenché" : v?.measured_value != null ? "vivant" : "non mesuré"}
                </span>
              </dd>
            </div>
          )
        })}
      </dl>

      <p className="mt-3 text-xs text-muted-foreground">
        <span className="font-medium">Ne doit pas marcher : </span>
        {hypothesis.where_it_should_not_work}
      </p>
    </section>
  )
}
