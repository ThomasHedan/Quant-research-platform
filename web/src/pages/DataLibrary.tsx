import { useMemo, useState } from "react"
import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import { ErrorState, LoadingState } from "@/components/DataState"
import { StatCell } from "@/components/StatCell"
import { DatasetCard } from "@/pages/data/DatasetCard"
import { DownloadPanel } from "@/pages/data/DownloadPanel"

/**
 * Bibliothèque de données. Deux choses vivent ici : faire entrer des barres
 * dans la plateforme, et voir exactement ce qui est sélectionnable pour un
 * backtest.
 *
 * La page affiche d'abord ce qui refuse : combien de datasets sont en
 * quarantaine, et quelle part de chaque dataset est scellée en holdout. Un
 * inventaire de données qui ne montrerait que le volume disponible inviterait
 * à confondre « j'ai beaucoup de données » avec « j'ai beaucoup de données
 * utilisables ».
 */
export function DataLibrary() {
  const [refreshKey, setRefreshKey] = useState(0)
  const datasets = useApi(() => api.listDatasets(), [refreshKey])
  const rows = useMemo(() => datasets.data ?? [], [datasets.data])

  const quarantined = rows.filter((d) => d.status === "quarantine").length
  const usableBars = rows
    .filter((d) => d.status === "ok")
    .reduce(
      (sum, d) => sum + d.splits.filter((s) => s.split !== "holdout").reduce((a, s) => a + s.n_bars, 0),
      0,
    )
  const sealedBars = rows
    .filter((d) => d.status === "ok")
    .reduce((sum, d) => sum + (d.splits.find((s) => s.split === "holdout")?.n_bars ?? 0), 0)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Données</h1>
        <p className="max-w-[80ch] text-sm text-muted-foreground">
          Catalogue London Strategic Edge, téléchargement, contrôle d'intégrité et partitionnement.
          Un backtest ne lit jamais un dataset entier : il lit un split nommé d'un dataset non
          quarantainé, et le holdout exige un chemin distinct qui compte les accès.
        </p>
      </div>

      <DownloadPanel onDownloaded={() => setRefreshKey((k) => k + 1)} />

      {datasets.loading && <LoadingState />}
      {datasets.error && <ErrorState error={datasets.error} />}

      {!datasets.loading && !datasets.error ? (
        rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucun dataset ingéré. Télécharge un instrument ci-dessus, ou utilise{" "}
            <span className="num">edgelab data download</span> depuis le CLI.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-8 border-y border-border py-3">
              <StatCell label="datasets" value={rows.length} digits={0} />
              <StatCell
                label="en quarantaine"
                value={quarantined}
                digits={0}
                tone="destructive"
                significant={quarantined > 0}
              />
              <StatCell label="barres exploitables" value={usableBars} digits={0} />
              <StatCell label="barres scellées (holdout)" value={sealedBars} digits={0} />
            </div>

            <div className="flex flex-col gap-4">
              {rows.map((dataset) => (
                <DatasetCard key={dataset.dataset_id} dataset={dataset} />
              ))}
            </div>
          </>
        )
      ) : null}
    </div>
  )
}
