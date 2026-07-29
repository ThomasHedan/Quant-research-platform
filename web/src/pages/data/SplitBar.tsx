import { cn } from "@/lib/utils"
import type { SplitSummary } from "@/lib/types"
import { formatNumber } from "@/components/StatCell"

const SPLIT_LABELS: Record<string, string> = {
  research: "research",
  validation: "validation",
  holdout: "holdout",
}

/**
 * Le partitionnement d'un dataset, rendu à l'échelle du nombre de barres.
 *
 * Le holdout est traité différemment des deux autres — hachuré et libellé
 * « scellé » — parce qu'il l'est : le voir dans l'UI ne coûte rien, l'ouvrir
 * incrémente un compteur permanent (I3). La barre existe précisément pour que
 * l'utilisateur sache combien de données il garde en réserve avant de décider
 * d'y toucher.
 */
export function SplitBar({ splits }: { splits: SplitSummary[] }) {
  const total = splits.reduce((sum, s) => sum + s.n_bars, 0)
  if (total === 0) return null

  return (
    <div className="flex flex-col gap-1.5">
      <div
        className="flex h-6 w-full overflow-hidden rounded-sm border border-border"
        role="img"
        aria-label={splits
          .map((s) => `${SPLIT_LABELS[s.split]} ${s.n_bars} barres`)
          .join(", ")}
      >
        {splits.map((split) => {
          const share = split.n_bars / total
          if (share === 0) return null
          return (
            <div
              key={split.split}
              className={cn(
                "flex items-center justify-center overflow-hidden border-r border-border last:border-r-0",
                split.split === "research" && "bg-foreground/[0.14]",
                split.split === "validation" && "bg-foreground/[0.28]",
                split.split === "holdout" &&
                  "bg-[repeating-linear-gradient(45deg,transparent,transparent_4px,var(--color-destructive)_4px,var(--color-destructive)_5px)] bg-destructive/[0.10]",
              )}
              style={{ width: `${share * 100}%` }}
            >
              {share > 0.12 ? (
                <span className="num truncate rounded-[2px] bg-background/85 px-1 text-[10px] text-muted-foreground">
                  {formatNumber(share * 100, 0)} %
                </span>
              ) : null}
            </div>
          )
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {splits.map((split) => (
          <span key={split.split} className="flex items-center gap-1.5">
            <span
              className={cn(
                "inline-block h-2 w-2 shrink-0 rounded-[1px] border border-border",
                split.split === "research" && "bg-foreground/[0.14]",
                split.split === "validation" && "bg-foreground/[0.28]",
                split.split === "holdout" && "border-destructive/60 bg-destructive/20",
              )}
            />
            <span className={cn(split.split === "holdout" && "text-destructive/90")}>
              {SPLIT_LABELS[split.split]}
              {split.split === "holdout" ? " (scellé)" : ""}
            </span>
            <span className="num">{split.n_bars}</span>
            <span className="text-muted-foreground/70">
              {split.start.slice(0, 10)} → {split.end.slice(0, 10)}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
