import { useState } from "react"
import { cn } from "@/lib/utils"
import { api, ApiError } from "@/lib/api"
import type { DatasetSummary, HoldoutResult } from "@/lib/types"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { StatCell } from "@/components/StatCell"
import { SplitBar } from "@/pages/data/SplitBar"

const RED_FLAG_THRESHOLD = 3

/**
 * Un dataset local. La quarantaine est un état de premier ordre : elle porte
 * la bordure rouge et reste visible dans la liste, jamais filtrée — c'est
 * précisément le dataset qu'il faut regarder, pas celui qu'il faut cacher.
 *
 * L'ouverture du holdout est délibérément inconfortable : un champ de raison
 * obligatoire, une confirmation, et un compteur affiché après coup. Il n'y a
 * pas de bouton « voir le holdout » en un clic, par construction (I3).
 */
export function DatasetCard({ dataset }: { dataset: DatasetSummary }) {
  const quarantined = dataset.status === "quarantine"
  const [open, setOpen] = useState(false)

  return (
    <Card
      className={cn(
        "rounded-none",
        quarantined && "border-destructive/60 border-l-4 border-l-destructive bg-destructive/[0.06]",
      )}
    >
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <span className="num">{dataset.instrument_symbol}</span>
            <span className="text-muted-foreground font-normal">{dataset.source}</span>
            {quarantined ? (
              <span className="inline-flex items-center rounded-sm border border-destructive/50 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-destructive">
                quarantaine
              </span>
            ) : null}
          </h3>
          <p className="text-xs text-muted-foreground">
            <span className="num">{dataset.start.slice(0, 16).replace("T", " ")}</span> →{" "}
            <span className="num">{dataset.end.slice(0, 16).replace("T", " ")}</span> ·{" "}
            {dataset.timezone} · hash{" "}
            <span className="num">{dataset.manifest_hash.slice(0, 12)}</span>
          </p>
          <p className="text-xs text-muted-foreground">{dataset.integrity_summary}</p>
        </div>
        <StatCell label="barres" value={dataset.n_bars} digits={0} />
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        <SplitBar splits={dataset.splits} />

        {quarantined ? (
          <p className="text-xs text-destructive/90">
            Le moteur de backtest refusera ce dataset. Il reste stocké pour diagnostic : corriger
            les données et ré-ingérer crée un nouveau dataset, cela ne répare jamais celui-ci.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {open ? (
              <HoldoutForm datasetId={dataset.dataset_id} onCancel={() => setOpen(false)} />
            ) : (
              <button
                type="button"
                onClick={() => setOpen(true)}
                className="w-fit text-xs text-destructive/90 underline underline-offset-4 hover:text-destructive focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal"
              >
                ouvrir le holdout (accès compté à vie)
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function HoldoutForm({ datasetId, onCancel }: { datasetId: string; onCancel: () => void }) {
  const [strategyId, setStrategyId] = useState("")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<HoldoutResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.openHoldout(datasetId, strategyId.trim(), reason))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <div className="flex flex-col gap-1 border border-destructive/50 bg-destructive/[0.06] p-3">
        <p className="text-xs text-destructive/90">
          Holdout ouvert : <span className="num">{result.n_bars}</span> barres. Accès de{" "}
          <span className="num">{result.strategy_id}</span> :{" "}
          <span className="num font-medium">{result.access_count}</span>.
        </p>
        {result.flagged ? (
          <p className="text-xs font-medium text-destructive">
            Drapeau rouge : {result.access_count} accès (seuil {RED_FLAG_THRESHOLD}). Toute
            significativité mesurée sur ce holdout est désormais moins crédible.
          </p>
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 border border-destructive/40 bg-destructive/[0.04] p-3">
      <p className="text-xs text-destructive/90">
        Chaque ouverture est journalisée définitivement et compte contre la stratégie. Trois accès
        lèvent un drapeau rouge visible partout. Il n'existe aucun moyen de remettre ce compteur à
        zéro.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            stratégie
          </span>
          <Input
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="h-8 w-44 text-xs"
            placeholder="orb-eurusd"
          />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            raison écrite (obligatoire)
          </span>
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="h-8 min-w-56 text-xs"
            placeholder="validation finale avant propsim"
          />
        </label>
        <Button
          type="button"
          variant="outline"
          className="h-8 text-xs"
          disabled={busy || !strategyId.trim() || !reason.trim()}
          onClick={submit}
        >
          {busy ? "ouverture…" : "confirmer l'ouverture"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="h-8 text-xs"
          onClick={onCancel}
          disabled={busy}
        >
          annuler
        </Button>
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}
