import { useState } from "react"
import { api, ApiError } from "@/lib/api"
import type { TriageStatus } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const STATUS_LABELS: Record<TriageStatus, string> = {
  a_lire: "à lire",
  fiche_faite: "fiche faite",
  hypothese_ecrite: "hypothèse écrite",
  en_test: "en test",
  mort: "mort",
  valide: "validé",
}

const ALL_STATUSES = Object.keys(STATUS_LABELS) as TriageStatus[]

/**
 * Déplacement manuel dans la file de triage. `mort` exige un motif écrit —
 * le formulaire ne soumet pas tant qu'il est vide, en plus du refus côté
 * API (spec Phase 7 : le motif de mort doit rester conservé).
 */
export function StatusChanger({
  paperId,
  currentStatus,
  onChanged,
}: {
  paperId: string
  currentStatus: TriageStatus
  onChanged: () => void
}) {
  const [pending, setPending] = useState<TriageStatus>(currentStatus)
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const needsReason = pending === "mort"
  const canApply = pending !== currentStatus && (!needsReason || reason.trim().length > 0)

  async function handleApply() {
    setError(null)
    setSubmitting(true)
    try {
      await api.setPaperStatus(paperId, pending, reason)
      setReason("")
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erreur inattendue.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={pending} onValueChange={(v) => setPending(v as TriageStatus)}>
          <SelectTrigger className="h-8 w-44 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ALL_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_LABELS[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {needsReason ? (
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="motif — obligatoire"
            className="h-8 max-w-64 text-xs"
          />
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleApply}
          disabled={!canApply || submitting}
        >
          Appliquer
        </Button>
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}

export { STATUS_LABELS }
