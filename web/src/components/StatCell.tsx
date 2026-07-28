import { cn } from "@/lib/utils"
import type { ConfidenceInterval } from "@/lib/types"

/** Formatte un nombre en chasse fixe, décimales alignées. */
export function formatNumber(value: number, digits = 2): string {
  return value.toLocaleString("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatPct(value: number, digits = 1): string {
  return `${formatNumber(value * 100, digits)} %`
}

/**
 * Une valeur numérique avec, quand elle existe, son intervalle de confiance
 * à 95 % affiché en dessous. « Un point sans barre d'erreur ne doit pas
 * exister dans cette UI » (CLAUDE.md §4, Phase 8, contraintes de fond).
 */
export function StatCell({
  label,
  value,
  digits = 2,
  ci,
  significant,
  className,
}: {
  label?: string
  value: string | number
  digits?: number
  ci?: ConfidenceInterval
  significant?: boolean
  className?: string
}) {
  const display = typeof value === "number" ? formatNumber(value, digits) : value
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      {label ? (
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      ) : null}
      <span
        className={cn(
          "num text-sm font-medium",
          significant === true && "text-signal-foreground bg-signal/70 px-1 rounded-sm w-fit",
          significant === false && "text-muted-foreground",
        )}
      >
        {display}
      </span>
      {ci ? (
        <span className="num text-[11px] text-muted-foreground">
          [{formatNumber(ci.ci_low, digits)}, {formatNumber(ci.ci_high, digits)}] (n={ci.n})
        </span>
      ) : null}
    </div>
  )
}

/** Point + intervalle horizontal, pour superposer une moyenne et son IC sur un graphique ou une ligne dense. */
export function InlineStat({
  value,
  digits = 2,
  ci,
  suffix,
}: {
  value: number
  digits?: number
  ci?: ConfidenceInterval
  suffix?: string
}) {
  return (
    <span className="num text-sm">
      {formatNumber(value, digits)}
      {suffix}
      {ci ? (
        <span className="text-muted-foreground text-xs">
          {" "}
          [{formatNumber(ci.ci_low, digits)}, {formatNumber(ci.ci_high, digits)}]
        </span>
      ) : null}
    </span>
  )
}
