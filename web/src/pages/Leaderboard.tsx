import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ArrowUpDown, TriangleAlert } from "lucide-react"

import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import type { LeaderboardRow } from "@/lib/types"
import { ErrorState, LoadingState } from "@/components/DataState"
import { formatNumber, formatPct } from "@/components/StatCell"
import { StatusBadge, DeadWrap } from "@/components/StatusBadge"
import { cn } from "@/lib/utils"

// Deux colonnes de la spec sont volontairement omises plutôt que peuplées de
// données inventées :
//   - "papier source" : le module papiers (Phase 7) n'existe pas encore.
//   - "corrélation au portefeuille courant" : aucun "portefeuille courant"
//     n'est persistant dans cette livraison — la corrélation ne se calcule
//     que sur une sélection explicite, sur la vue Combinaisons.

function numCol(digits: number) {
  return (value: number) => <span className="num">{formatNumber(value, digits)}</span>
}

function pctCol(digits = 1) {
  return (value: number) => <span className="num">{formatPct(value, digits)}</span>
}

const columns: ColumnDef<LeaderboardRow>[] = [
  {
    accessorKey: "strategy_id",
    header: "Stratégie",
    cell: ({ row }) => (
      <DeadWrap dead={row.original.status === "dead"} className="whitespace-nowrap">
        <Link
          to={`/strategies/${row.original.strategy_id}`}
          className="font-medium underline-offset-2 hover:underline"
        >
          {row.original.strategy_id}
        </Link>
      </DeadWrap>
    ),
  },
  { accessorKey: "family", header: "Famille" },
  { accessorKey: "universe", header: "Univers" },
  {
    accessorKey: "n_trades",
    header: "N trades",
    cell: (c) => <span className="num">{c.getValue<number>()}</span>,
  },
  {
    accessorKey: "net_expectancy_bps",
    header: "Espérance nette (bps)",
    cell: (c) => numCol(1)(c.getValue<number>()),
  },
  {
    accessorKey: "t_stat",
    header: "t-stat",
    cell: (c) => numCol(2)(c.getValue<number>()),
  },
  {
    accessorKey: "dsr",
    header: "DSR",
    cell: (c) => numCol(3)(c.getValue<number>()),
  },
  {
    accessorKey: "pbo",
    header: "PBO",
    cell: (c) => pctCol(1)(c.getValue<number>()),
  },
  {
    accessorKey: "p_pass",
    header: "P(passage)",
    cell: (c) => (
      <span className="num font-semibold">{formatPct(c.getValue<number>(), 1)}</span>
    ),
  },
  {
    accessorKey: "delta_vs_baseline_p_pass",
    header: "Δ vs baseline",
    cell: (c) => pctCol(1)(c.getValue<number>()),
  },
  {
    accessorKey: "max_dd_p95",
    header: "Max DD p95",
    cell: (c) => numCol(3)(c.getValue<number>()),
  },
  {
    accessorKey: "worst_day_p95",
    header: "Pire jour p95",
    cell: (c) => pctCol(2)(c.getValue<number>()),
  },
  {
    accessorKey: "worst_streak_p95",
    header: "Série de pertes max p95",
    cell: (c) => numCol(1)(c.getValue<number>()),
  },
  {
    accessorKey: "holdout_access_count",
    header: "Accès holdout",
    cell: ({ row }) => (
      <span
        className={cn(
          "num inline-flex items-center gap-1",
          row.original.holdout_flagged && "text-destructive font-medium",
        )}
      >
        {row.original.holdout_flagged ? <TriangleAlert className="size-3.5" /> : null}
        {row.original.holdout_access_count}
      </span>
    ),
  },
  {
    accessorKey: "status",
    header: "Statut",
    cell: (c) => <StatusBadge status={c.getValue<LeaderboardRow["status"]>()} />,
  },
  {
    // Présent, jamais colonne de tri par défaut (spec Phase 8, vue 1).
    accessorKey: "win_rate",
    header: "Win rate",
    cell: (c) => pctCol(1)(c.getValue<number>()),
  },
]

export function Leaderboard() {
  const { data, error, loading } = useApi(() => api.listStrategies(), [])
  // Tri par défaut : P(passage) décroissant — c'est la fonction objectif (I5),
  // jamais le Sharpe ni le win rate.
  const [sorting, setSorting] = useState<SortingState>([{ id: "p_pass", desc: true }])

  const rows = useMemo(() => data ?? [], [data])

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Leaderboard</h1>
        <p className="text-sm text-muted-foreground">
          Tri par défaut : P(passage) — jamais le Sharpe, jamais le win rate.
        </p>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState error={error} />}

      {!loading && !error && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">Aucune stratégie enregistrée.</p>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto border border-border rounded-md">
          <table className="w-full text-xs border-collapse">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className="border-b border-border bg-secondary/50">
                  {headerGroup.headers.map((header) => {
                    const sorted = header.column.getIsSorted()
                    return (
                      <th
                        key={header.id}
                        className="px-2.5 py-2 text-left font-medium text-muted-foreground whitespace-nowrap select-none"
                      >
                        {header.isPlaceholder ? null : (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 hover:text-foreground"
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {sorted === "asc" ? (
                              <ArrowUp className="size-3" />
                            ) : sorted === "desc" ? (
                              <ArrowDown className="size-3" />
                            ) : (
                              <ArrowUpDown className="size-3 opacity-30" />
                            )}
                          </button>
                        )}
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn(
                    "border-b border-border/60 last:border-b-0",
                    row.original.status === "dead" && "border-l-2 border-l-destructive/70 bg-destructive/[0.04]",
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-2.5 py-2 whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
