import { cn } from "@/lib/utils"
import type { PaperRecord, TriageStatus } from "@/lib/types"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { formatPct, StatCell } from "@/components/StatCell"
import { HypothesisDraftView, HypothesisIntake } from "@/pages/papers/HypothesisIntake"
import { STATUS_LABELS, StatusChanger } from "@/pages/papers/StatusChanger"

function TriageBadge({ status }: { status: TriageStatus }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-sm border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        status === "mort" && "border-destructive/50 text-destructive line-through decoration-2",
        status === "valide" && "border-foreground/30 bg-foreground text-background",
        status !== "mort" && status !== "valide" && "border-border text-muted-foreground",
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

/**
 * Une fiche papier complète : métadonnées, score de testabilité, puis
 * l'étape suivante pertinente pour son statut — générer une hypothèse, ou
 * afficher celle déjà rattachée. `mort` reste un état de premier ordre,
 * visible et barré, jamais masqué (même principe que les stratégies).
 */
export function PaperCard({ record, onChanged }: { record: PaperRecord; onChanged: () => void }) {
  const { sheet } = record
  const dead = record.status === "mort"

  return (
    <Card
      className={cn(
        "rounded-none",
        dead && "border-destructive/60 border-l-4 border-l-destructive bg-destructive/[0.06]",
      )}
    >
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className={cn("flex flex-col gap-1", dead && "text-destructive/90")}>
          <h3 className={cn("text-sm font-semibold", dead && "line-through decoration-2")}>
            {sheet.title}
          </h3>
          <p className="text-xs text-muted-foreground">
            {sheet.authors.join(", ")} — {sheet.publication_year} — {sheet.venue} — langue source :{" "}
            <span className="num">{sheet.language_source}</span>
          </p>
          <p className="text-xs text-muted-foreground">
            {sheet.anomaly_family} · {sheet.asset_class} · {sheet.frequency} · {sheet.sample_period}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <StatCell label="testabilité" value={formatPct(record.testability_score, 0)} />
          <TriageBadge status={record.status} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm">{sheet.economic_hypothesis}</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
          <span>Sharpe/hit rate revendiqué : {sheet.claimed_sharpe_or_hit_rate}</span>
          <span>coûts intégrés : {sheet.costs_considered}</span>
          <span>difficulté de réplication : {sheet.replication_difficulty}</span>
          <span>données nécessaires : {sheet.data_needed}</span>
          {sheet.source_url_or_doi ? <span>source : {sheet.source_url_or_doi}</span> : null}
        </div>
        {sheet.personal_notes ? (
          <p className="text-xs text-muted-foreground italic">{sheet.personal_notes}</p>
        ) : null}

        {dead && record.dead_reason ? (
          <p className="text-xs text-destructive">
            <span className="font-medium">Motif de mort : </span>
            {record.dead_reason}
          </p>
        ) : null}

        {record.hypothesis_draft ? (
          <HypothesisDraftView draft={record.hypothesis_draft} />
        ) : (
          <HypothesisIntake paperId={sheet.id} onAttached={onChanged} />
        )}

        <StatusChanger paperId={sheet.id} currentStatus={record.status} onChanged={onChanged} />
      </CardContent>
    </Card>
  )
}
