import { useMemo, useState } from "react"
import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import { ErrorState, LoadingState } from "@/components/DataState"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { PaperCard } from "@/pages/papers/PaperCard"
import { PaperIntakeCard } from "@/pages/papers/PaperIntakeCard"

const ALL_VALUE = "__all__"

function distinctSorted(values: string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b))
}

/**
 * Bibliothèque de papiers (Phase 7). Le pipeline papier -> hypothèse
 * s'arrête volontairement à un brouillon d'hypothèse falsifiable (I2) :
 * transformer ce brouillon en stratégie réellement testable et lancer un
 * backtest reste une action CLI distincte, non construite ici — voir
 * `edgelab/papers/README.md`.
 */
export function PapersLibrary() {
  const [refreshKey, setRefreshKey] = useState(0)
  const papers = useApi(() => api.listPapers(), [refreshKey])
  const refresh = () => setRefreshKey((k) => k + 1)

  const [language, setLanguage] = useState(ALL_VALUE)
  const [family, setFamily] = useState(ALL_VALUE)
  const [assetClass, setAssetClass] = useState(ALL_VALUE)
  const [sortByTestability, setSortByTestability] = useState(false)

  const records = useMemo(() => papers.data ?? [], [papers.data])

  const languages = useMemo(
    () => distinctSorted(records.map((r) => r.sheet.language_source)),
    [records],
  )
  const families = useMemo(
    () => distinctSorted(records.map((r) => r.sheet.anomaly_family)),
    [records],
  )
  const assetClasses = useMemo(
    () => distinctSorted(records.map((r) => r.sheet.asset_class)),
    [records],
  )

  const filtered = useMemo(() => {
    let rows = records.filter(
      (r) =>
        (language === ALL_VALUE || r.sheet.language_source === language) &&
        (family === ALL_VALUE || r.sheet.anomaly_family === family) &&
        (assetClass === ALL_VALUE || r.sheet.asset_class === assetClass),
    )
    if (sortByTestability) {
      rows = [...rows].sort((a, b) => b.testability_score - a.testability_score)
    }
    return rows
  }, [records, language, family, assetClass, sortByTestability])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Bibliothèque de papiers</h1>
        <p className="text-sm text-muted-foreground max-w-[70ch]">
          Ingestion déléguée à une IA externe via des prompts copiables (pas d'extraction PDF ni
          de traduction construites en interne dans ce premier jet), score de testabilité, file de
          triage. Le texte intégral d'un papier n'est jamais stocké.
        </p>
      </div>

      <PaperIntakeCard onCreated={refresh} />

      {papers.loading && <LoadingState />}
      {papers.error && <ErrorState error={papers.error} />}

      {!papers.loading && !papers.error && records.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Aucun papier enregistré. Colle un JSON ci-dessus pour commencer.
        </p>
      ) : null}

      {records.length > 0 ? (
        <div className="flex flex-wrap items-end gap-3">
          <FilterSelect label="Langue" value={language} onChange={setLanguage} options={languages} />
          <FilterSelect label="Famille" value={family} onChange={setFamily} options={families} />
          <FilterSelect
            label="Classe d'actifs"
            value={assetClass}
            onChange={setAssetClass}
            options={assetClasses}
          />
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={sortByTestability}
              onChange={(e) => setSortByTestability(e.target.checked)}
            />
            trier par score de testabilité
          </label>
        </div>
      ) : null}

      <div className="flex flex-col gap-4">
        {filtered.map((record) => (
          <PaperCard key={record.sheet.id} record={record} onChanged={refresh} />
        ))}
      </div>
    </div>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: string[]
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-8 w-40 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>toutes</SelectItem>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
