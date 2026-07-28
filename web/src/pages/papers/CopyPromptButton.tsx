import { useState } from "react"
import { Button } from "@/components/ui/button"

type CopyState = "idle" | "loading" | "copied" | "error"

/**
 * Récupère un prompt via `fetchPrompt` et le pose dans le presse-papiers.
 * Aucun texte de prompt n'est codé en dur côté front : la source unique est
 * `edgelab.papers.prompts`, servie par l'API — voir `edgelab/papers/README.md`.
 */
export function CopyPromptButton({
  label,
  fetchPrompt,
}: {
  label: string
  fetchPrompt: () => Promise<string>
}) {
  const [state, setState] = useState<CopyState>("idle")

  async function handleClick() {
    setState("loading")
    try {
      const text = await fetchPrompt()
      await navigator.clipboard.writeText(text)
      setState("copied")
    } catch {
      setState("error")
    } finally {
      setTimeout(() => setState("idle"), 1800)
    }
  }

  return (
    <Button type="button" variant="outline" size="sm" onClick={handleClick} disabled={state === "loading"}>
      {state === "copied" ? "Copié ✓" : state === "error" ? "Échec de la copie" : label}
    </Button>
  )
}
