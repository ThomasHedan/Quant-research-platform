import { cn } from "@/lib/utils"
import { formatNumber, formatPct } from "@/components/StatCell"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ConfidenceInterval } from "@/lib/types"
import { isSignificantTStat } from "./significance"

export interface CIStatRow {
  key: string
  label: string
  stats: ConfidenceInterval
  t_stat: number
  hitRate?: number
}

/**
 * Table générique pour toute ligne "moyenne + IC 95 % + t-stat" : stabilité
 * par sous-période, régimes de volatilité, décomposition par instrument.
 * L'IC accompagne systématiquement la moyenne (jamais un point seul), et la
 * couleur signal marque |t| élevé — jamais un signe positif/négatif.
 */
export function CIStatTable({ rows, labelHeader }: { rows: CIStatRow[]; labelHeader: string }) {
  const hasHitRate = rows.some((r) => r.hitRate !== undefined)
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{labelHeader}</TableHead>
          <TableHead className="text-right">Espérance (IC 95 %)</TableHead>
          <TableHead className="text-right">n</TableHead>
          <TableHead className="text-right">t-stat</TableHead>
          {hasHitRate ? <TableHead className="text-right">hit rate</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const significant = isSignificantTStat(row.t_stat)
          return (
            <TableRow key={row.key}>
              <TableCell className="font-medium">{row.label}</TableCell>
              <TableCell className="text-right">
                <span className="num">
                  {formatNumber(row.stats.mean, 3)}{" "}
                  <span className="text-muted-foreground text-xs">
                    [{formatNumber(row.stats.ci_low, 3)}, {formatNumber(row.stats.ci_high, 3)}]
                  </span>
                </span>
              </TableCell>
              <TableCell className="num text-right text-muted-foreground">{row.stats.n}</TableCell>
              <TableCell className="text-right">
                <span
                  className={cn(
                    "num",
                    significant && "text-signal-foreground bg-signal/70 px-1 rounded-sm",
                  )}
                >
                  {formatNumber(row.t_stat, 2)}
                </span>
              </TableCell>
              {hasHitRate ? (
                <TableCell className="num text-right text-muted-foreground">
                  {row.hitRate !== undefined ? formatPct(row.hitRate, 1) : "—"}
                </TableCell>
              ) : null}
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
