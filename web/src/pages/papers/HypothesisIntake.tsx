import { useState } from "react"
import { api, ApiError } from "@/lib/api"
import type { HypothesisDraft } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { CopyPromptButton } from "@/pages/papers/CopyPromptButton"

/**
 * Étape 2, personnalisée à un papier : prompt embarquant sa fiche, JSON
 * collé en retour. S'arrête délibérément à un brouillon — voir le docstring
 * de `edgelab.papers.prompts` et `edgelab/papers/README.md`. Rien ici
 * n'écrit dans `edgelab/strategies/` ni ne lance de backtest.
 */
export function HypothesisIntake({
  paperId,
  onAttached,
}: {
  paperId: string
  onAttached: () => void
}) {
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleInsert() {
    setError(null)
    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch {
      setError("Ce texte n'est pas du JSON valide — vérifie qu'il n'y a rien avant/après l'objet.")
      return
    }
    setSubmitting(true)
    try {
      await api.attachPaperHypothesis(paperId, parsed)
      setText("")
      onAttached()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erreur inattendue.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-border pt-3">
      <p className="text-xs text-muted-foreground">
        2. Génère une hypothèse falsifiable (I2) pour ce papier.
      </p>
      <div>
        <CopyPromptButton
          label="Copier le prompt : Générer une hypothèse falsifiable"
          fetchPrompt={async () => (await api.getPaperHypothesisPrompt(paperId)).prompt}
        />
      </div>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Colle ici le JSON de l'hypothèse renvoyé par l'IA…"
        rows={5}
        className="num text-xs"
        aria-invalid={error ? "true" : undefined}
      />
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
      <Button
        type="button"
        size="sm"
        onClick={handleInsert}
        disabled={submitting || !text.trim()}
        className="w-fit"
      >
        {submitting ? "Insertion…" : "Insérer l'hypothèse"}
      </Button>
    </div>
  )
}

/** Affiche un brouillon d'hypothèse déjà rattaché — jamais une exécution, un texte à relire. */
export function HypothesisDraftView({ draft }: { draft: HypothesisDraft }) {
  const h = draft.hypothesis
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3 text-xs">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        Brouillon d'hypothèse (I2)
      </p>
      <p>{h.economic_hypothesis}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 num text-muted-foreground">
        <span>direction : {h.predicted_direction}</span>
        <span>amplitude : {h.predicted_amplitude_atr} ATR</span>
        <span>hit rate attendu : {h.predicted_hit_rate}</span>
        <span>horizon : {h.predicted_horizon_bars} barres</span>
      </div>
      <p>
        <span className="font-medium">Ne doit pas marcher : </span>
        {h.where_it_should_not_work}
      </p>
      <ul className="list-inside list-disc">
        {h.kill_criteria.map((c) => (
          <li key={c.name} className="num">
            {c.name} — {c.metric} {c.comparison === "less_than" ? "<" : ">"} {c.threshold}
          </li>
        ))}
      </ul>
      <details>
        <summary className="cursor-pointer select-none text-muted-foreground">
          squelette de code (non exécuté)
        </summary>
        <pre className="num mt-1 overflow-x-auto rounded-md bg-secondary/50 p-2 text-[11px]">
          {draft.strategy_code_skeleton}
        </pre>
      </details>
      <p className="text-muted-foreground">
        Ce brouillon ne lance aucun backtest. En faire une stratégie réellement testable — un
        dossier dans <code className="num">edgelab/strategies/</code>, gaté par les critères de
        mort ci-dessus (I2) — reste une étape CLI volontaire, distincte, non construite dans cette
        vue.
      </p>
    </div>
  )
}
