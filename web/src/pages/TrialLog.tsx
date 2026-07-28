import { useMemo, useState } from "react"
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"

import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import type { Trial } from "@/lib/types"
import { ErrorState, LoadingState } from "@/components/DataState"
import { Input } from "@/components/ui/input"

const columns: ColumnDef<Trial>[] = [
  { accessorKey: "id", header: "id", cell: (c) => <span className="num text-xs">{c.getValue<string>()}</span> },
  { accessorKey: "trial_type", header: "type" },
  {
    accessorKey: "created_at",
    header: "créé",
    cell: (c) => (
      <span className="num text-xs">{new Date(c.getValue<string>()).toLocaleString("fr-FR")}</span>
    ),
  },
  { accessorKey: "strategy_id", header: "stratégie" },
  {
    accessorKey: "lineage_hash",
    header: "lineage",
    cell: (c) => (
      <span className="num text-xs text-muted-foreground">{c.getValue<string>().slice(0, 10)}…</span>
    ),
  },
  {
    accessorKey: "note",
    header: "note",
    cell: (c) => <span className="text-xs text-muted-foreground">{c.getValue<string>()}</span>,
  },
]

/**
 * Journal d'essais (CLAUDE.md §4, Phase 8, vue 6) : le registre brut,
 * append-only (I1), jamais éditable ni supprimable — aucune action de ce
 * genre n'existe dans cette vue, même pour la forme. Le compteur global doit
 * être l'élément le plus visible de la page : c'est l'entrée du DSR.
 */
export function TrialLog() {
  const trials = useApi(() => api.listTrials(), [])
  const count = useApi(() => api.trialCount(), [])
  const [filter, setFilter] = useState("")

  const filtered = useMemo(() => {
    const all = trials.data ?? []
    const q = filter.trim().toLowerCase()
    if (!q) return all
    return all.filter(
      (t) => t.strategy_id.toLowerCase().includes(q) || t.trial_type.toLowerCase().includes(q),
    )
  }, [trials.data, filter])

  const table = useReactTable({
    data: filtered,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Journal d'essais</h1>
        <p className="text-sm text-muted-foreground max-w-[70ch]">
          Registre brut, append-only (I1). Aucun essai n'est jamais supprimé ou modifié — un essai
          raté reste visible.
        </p>
      </div>

      <div className="border border-border rounded-md px-4 py-3 w-fit">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Compteur global d'essais — entrée du Deflated Sharpe Ratio
        </span>
        <div className="num text-3xl font-semibold leading-tight">
          {count.loading ? "…" : (count.data?.count ?? "—")}
        </div>
      </div>

      {trials.error && <ErrorState error={trials.error} />}
      {trials.loading && <LoadingState />}

      {!trials.loading && !trials.error && (
        <>
          <Input
            placeholder="Filtrer par stratégie ou type d'essai…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="max-w-sm"
          />

          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {trials.data && trials.data.length === 0
                ? "Aucun essai enregistré."
                : "Aucun essai ne correspond au filtre."}
            </p>
          ) : (
            <div className="overflow-x-auto border border-border rounded-md">
              <table className="w-full text-xs border-collapse">
                <thead>
                  {table.getHeaderGroups().map((headerGroup) => (
                    <tr key={headerGroup.id} className="border-b border-border bg-secondary/50">
                      {headerGroup.headers.map((header) => (
                        <th
                          key={header.id}
                          className="px-2.5 py-2 text-left font-medium text-muted-foreground whitespace-nowrap"
                        >
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="border-b border-border/60 last:border-b-0">
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
        </>
      )}
    </div>
  )
}
