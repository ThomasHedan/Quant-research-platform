import { formatNumber } from "@/components/StatCell"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { WalkForwardResult } from "@/lib/types"
import { nWalkForwardWindows } from "@/lib/derived"

/**
 * Fenêtres de walk-forward : le paramètre est sélectionné in-sample, la
 * performance n'est mesurée que sur la fenêtre suivante, jamais vue au
 * moment de la sélection — le seul résultat d'optimisation crédible.
 */
export function WalkForwardTable({ result }: { result: WalkForwardResult }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        N fenêtres : <span className="num text-foreground">{nWalkForwardWindows(result)}</span> — retour
        OOS moyen :{" "}
        <span className="num text-foreground">{formatNumber(result.out_of_sample_mean_return, 3)}</span> — retour
        OOS total : <span className="num text-foreground">{formatNumber(result.out_of_sample_total_return, 3)}</span>
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Fenêtre</TableHead>
            <TableHead className="text-right">Paramètre sélectionné (in-sample)</TableHead>
            <TableHead className="text-right">Score in-sample</TableHead>
            <TableHead className="text-right">Retour out-of-sample</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result.windows.map((w) => (
            <TableRow key={w.window_index}>
              <TableCell className="num">{w.window_index}</TableCell>
              <TableCell className="num text-right">{w.selected_param}</TableCell>
              <TableCell className="num text-right">{formatNumber(w.in_sample_score, 3)}</TableCell>
              <TableCell className="num text-right">{formatNumber(w.out_of_sample_return, 3)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
