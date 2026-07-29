import { useMemo, useState } from "react"
import { api, ApiError } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import type { DownloadResult, ProviderInstrument } from "@/lib/types"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

/** Les quatorze résolutions du vault, dans l'ordre du fournisseur. */
const TIMEFRAMES = [
  "1s",
  "5s",
  "15s",
  "30s",
  "1m",
  "3m",
  "5m",
  "15m",
  "30m",
  "1h",
  "4h",
  "1d",
  "1w",
  "1mo",
]

const CATEGORIES = [
  "forex",
  "stocks",
  "crypto",
  "index",
  "commodity",
  "etf",
  "futures",
  "bonds",
]

const ALL_VALUE = "__all__"

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/**
 * Découpe suggérée 60 / 20 / 20 en temps calendaire.
 *
 * C'est une suggestion affichée dans des champs modifiables, jamais un défaut
 * silencieux : où s'arrête la recherche et où commence le holdout est la
 * décision qui protège l'utilisateur de lui-même (I3), et il doit la voir.
 */
function suggestPartition(start: string, end: string): { research: string; validation: string } {
  const from = new Date(start).getTime()
  const to = new Date(end).getTime()
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) {
    return { research: "", validation: "" }
  }
  const span = to - from
  return {
    research: isoDay(new Date(from + span * 0.6)),
    validation: isoDay(new Date(from + span * 0.8)),
  }
}

/**
 * Recherche dans le catalogue London Strategic Edge, puis téléchargement vers
 * le store local. Le formulaire n'accepte aucun raccourci : instrument EdgeLab,
 * résolution, période et bornes de partition sont tous explicites.
 */
export function DownloadPanel({ onDownloaded }: { onDownloaded: () => void }) {
  const instruments = useApi(() => api.listInstruments(), [])

  const [category, setCategory] = useState(ALL_VALUE)
  const [search, setSearch] = useState("")
  const [catalog, setCatalog] = useState<ProviderInstrument[] | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogBusy, setCatalogBusy] = useState(false)

  const [providerSymbol, setProviderSymbol] = useState("")
  const [instrumentSymbol, setInstrumentSymbol] = useState("")
  const [timeframe, setTimeframe] = useState("1h")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [researchEnd, setResearchEnd] = useState("")
  const [validationEnd, setValidationEnd] = useState("")
  const [bulk, setBulk] = useState(false)

  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<DownloadResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const suggestion = useMemo(() => suggestPartition(start, end), [start, end])

  async function loadCatalog() {
    setCatalogBusy(true)
    setCatalogError(null)
    try {
      setCatalog(
        await api.getProviderCatalog(
          category === ALL_VALUE ? undefined : category,
          search || undefined,
        ),
      )
    } catch (err) {
      setCatalog(null)
      setCatalogError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setCatalogBusy(false)
    }
  }

  async function submit() {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const downloaded = await api.downloadDataset({
        provider_symbol: providerSymbol.trim(),
        instrument_symbol: instrumentSymbol,
        timeframe,
        start: new Date(`${start}T00:00:00Z`).toISOString(),
        end: new Date(`${end}T00:00:00Z`).toISOString(),
        research_end: new Date(`${researchEnd}T00:00:00Z`).toISOString(),
        validation_end: new Date(`${validationEnd}T00:00:00Z`).toISOString(),
        bulk,
      })
      setResult(downloaded)
      onDownloaded()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const complete =
    providerSymbol.trim() !== "" &&
    instrumentSymbol !== "" &&
    start !== "" &&
    end !== "" &&
    researchEnd !== "" &&
    validationEnd !== ""

  return (
    <Card className="rounded-none">
      <CardHeader>
        <h2 className="text-sm font-semibold">Télécharger depuis London Strategic Edge</h2>
        <p className="max-w-[80ch] text-xs text-muted-foreground">
          Le catalogue et le téléchargement passent par la clé{" "}
          <span className="num">LSE_API_KEY</span> lue dans l'environnement du serveur. Les barres
          reçues traversent le même contrôle d'intégrité que n'importe quelle autre source : un
          dataset troué part en quarantaine et le backtester le refusera.
        </p>
      </CardHeader>

      <CardContent className="flex flex-col gap-5">
        <section className="flex flex-col gap-2">
          <h3 className="text-[11px] uppercase tracking-wide text-muted-foreground">
            1 · trouver le symbole
          </h3>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                catégorie
              </span>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger className="h-8 w-36 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_VALUE}>toutes</SelectItem>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                recherche
              </span>
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 w-56 text-xs"
                placeholder="eur/usd, gold, nasdaq…"
              />
            </label>
            <Button
              type="button"
              variant="outline"
              className="h-8 text-xs"
              onClick={loadCatalog}
              disabled={catalogBusy}
            >
              {catalogBusy ? "interrogation…" : "interroger le catalogue"}
            </Button>
          </div>

          {catalogError ? (
            <p className="text-xs text-destructive" role="alert">
              {catalogError}
            </p>
          ) : null}

          {catalog ? (
            <div className="max-h-56 overflow-auto border border-border">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-background">
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="px-2 py-1 font-medium">symbole</th>
                    <th className="px-2 py-1 font-medium">nom</th>
                    <th className="px-2 py-1 font-medium">catégorie</th>
                    <th className="px-2 py-1 font-medium">historique</th>
                    <th className="px-2 py-1 text-right font-medium">ticks</th>
                    <th className="px-2 py-1" />
                  </tr>
                </thead>
                <tbody>
                  {catalog.slice(0, 200).map((row) => (
                    <tr key={`${row.dataset}:${row.symbol}`} className="border-b border-border/60">
                      <td className="num px-2 py-1">{row.symbol}</td>
                      <td className="px-2 py-1 text-muted-foreground">{row.name}</td>
                      <td className="px-2 py-1 text-muted-foreground">{row.category}</td>
                      <td className="num px-2 py-1 text-muted-foreground">
                        {row.first?.slice(0, 10) ?? "?"} → {row.last?.slice(0, 10) ?? "?"}
                      </td>
                      <td className="num px-2 py-1 text-right text-muted-foreground">
                        {row.ticks ?? "?"}
                      </td>
                      <td className="px-2 py-1 text-right">
                        <button
                          type="button"
                          className="underline underline-offset-4 hover:text-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal"
                          onClick={() => setProviderSymbol(row.symbol)}
                        >
                          choisir
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-[11px] uppercase tracking-wide text-muted-foreground">
            2 · période et résolution
          </h3>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="symbole fournisseur">
              <Input
                value={providerSymbol}
                onChange={(e) => setProviderSymbol(e.target.value)}
                className="h-8 w-36 text-xs"
                placeholder="EUR/USD"
              />
            </Field>
            <Field label="instrument edgelab">
              <Select value={instrumentSymbol} onValueChange={setInstrumentSymbol}>
                <SelectTrigger className="h-8 w-36 text-xs">
                  <SelectValue placeholder="choisir" />
                </SelectTrigger>
                <SelectContent>
                  {(instruments.data ?? []).map((i) => (
                    <SelectItem key={i.symbol} value={i.symbol}>
                      {i.symbol} — {i.asset_class}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="résolution">
              <Select value={timeframe} onValueChange={setTimeframe}>
                <SelectTrigger className="h-8 w-24 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEFRAMES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="début">
              <Input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="h-8 w-36 text-xs"
              />
            </Field>
            <Field label="fin">
              <Input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="h-8 w-36 text-xs"
              />
            </Field>
            <label className="flex items-center gap-2 pb-1 text-xs text-muted-foreground">
              <input type="checkbox" checked={bulk} onChange={(e) => setBulk(e.target.checked)} />
              export Parquet (volume)
            </label>
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-[11px] uppercase tracking-wide text-muted-foreground">
            3 · partitionnement — la décision qui compte
          </h3>
          <p className="max-w-[80ch] text-xs text-muted-foreground">
            Aucun défaut n'est appliqué à ta place. La suggestion ci-dessous découpe 60 / 20 / 20 en
            temps calendaire ; le holdout qui en résulte ne sera lisible qu'en consommant un accès
            compté à vie.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="fin research">
              <Input
                type="date"
                value={researchEnd}
                onChange={(e) => setResearchEnd(e.target.value)}
                className="h-8 w-36 text-xs"
              />
            </Field>
            <Field label="fin validation">
              <Input
                type="date"
                value={validationEnd}
                onChange={(e) => setValidationEnd(e.target.value)}
                className="h-8 w-36 text-xs"
              />
            </Field>
            {suggestion.research ? (
              <Button
                type="button"
                variant="ghost"
                className="h-8 text-xs"
                onClick={() => {
                  setResearchEnd(suggestion.research)
                  setValidationEnd(suggestion.validation)
                }}
              >
                suggérer 60 / 20 / 20
              </Button>
            ) : null}
          </div>
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="outline"
            className="h-8 text-xs"
            disabled={busy || !complete}
            onClick={submit}
          >
            {busy ? "téléchargement…" : "télécharger et ingérer"}
          </Button>
          {error ? (
            <span className="text-xs text-destructive" role="alert">
              {error}
            </span>
          ) : null}
          {result ? (
            <span
              className={
                result.quarantined ? "text-xs text-destructive" : "text-xs text-muted-foreground"
              }
            >
              {result.quarantined
                ? `Dataset ${result.dataset.dataset_id.slice(0, 12)} mis en QUARANTAINE : ${result.dataset.integrity_summary}`
                : `Dataset ${result.dataset.dataset_id.slice(0, 12)} ingéré, ${result.dataset.n_bars} barres.`}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
