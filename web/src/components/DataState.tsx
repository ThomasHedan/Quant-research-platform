import { ApiError } from "@/lib/api"

export function LoadingState({ label = "Chargement…" }: { label?: string }) {
  return (
    <div className="text-sm text-muted-foreground py-8" role="status">
      {label}
    </div>
  )
}

export function ErrorState({ error }: { error: Error }) {
  const message =
    error instanceof ApiError ? `${error.status} — ${error.message}` : error.message
  return (
    <div
      className="text-sm text-destructive border border-destructive/40 bg-destructive/[0.04] rounded-md p-3"
      role="alert"
    >
      {message}
    </div>
  )
}
