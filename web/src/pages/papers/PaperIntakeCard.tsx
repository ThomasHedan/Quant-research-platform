import { useState } from "react"
import { api, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { CopyPromptButton } from "@/pages/papers/CopyPromptButton"

/**
 * Étape 1 du flux Phase 7 : copier le prompt d'analyse, le donner à une IA
 * externe, coller le JSON renvoyé ici. Le JSON n'est jamais re-validé côté
 * front — un `JSON.parse` seulement, pour distinguer un texte qui n'est
 * même pas du JSON d'un JSON syntaxiquement valide mais rejeté par le
 * schéma (l'API renvoie alors 422, message affiché tel quel).
 */
export function PaperIntakeCard({ onCreated }: { onCreated: () => void }) {
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
      await api.createPaper(parsed)
      setText("")
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erreur inattendue.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="rounded-none">
      <CardHeader>
        <CardTitle className="text-sm">1. Analyser un nouveau papier</CardTitle>
        <CardDescription>
          Copie le prompt, donne-le avec le papier (texte, lien ou PDF collé) à une IA, colle ici
          le JSON qu'elle renvoie.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div>
          <CopyPromptButton
            label="Copier le prompt : Analyse de papier de recherche"
            fetchPrompt={async () => (await api.getPaperAnalysisPrompt()).prompt}
          />
        </div>
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Colle ici le JSON renvoyé par l'IA…"
          rows={6}
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
          {submitting ? "Insertion…" : "Insérer la fiche"}
        </Button>
      </CardContent>
    </Card>
  )
}
