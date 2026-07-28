import { cn } from "@/lib/utils"
import type { StrategyStatus } from "@/lib/types"

const LABELS: Record<StrategyStatus, string> = {
  candidate: "candidate",
  dead: "dead",
  validated: "validated",
}

/**
 * `dead` est un état de premier ordre, pas un filtre masqué (CLAUDE.md §4).
 * Rendu en rouge barré — jamais en vert pour un état "positif" : le vert
 * "profitable" n'existe pas dans cette UI.
 */
export function StatusBadge({ status, className }: { status: StrategyStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        status === "dead" && "border-destructive/50 text-destructive line-through decoration-2",
        status === "candidate" && "border-border text-muted-foreground",
        status === "validated" && "border-foreground/30 bg-foreground text-background",
        className,
      )}
    >
      {LABELS[status]}
    </span>
  )
}

/** Applique le traitement "barré" à un bloc entier — la stratégie hérite de l'état de sa fiche. */
export function DeadWrap({
  dead,
  children,
  className,
}: {
  dead: boolean
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        dead && "text-destructive/90 line-through decoration-destructive/60 decoration-2",
        className,
      )}
    >
      {children}
    </div>
  )
}
