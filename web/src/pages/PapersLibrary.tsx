import { api } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import { ErrorState, LoadingState } from "@/components/DataState"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"

const TRIAGE_STAGES = ["à lire", "fiche faite", "hypothèse écrite", "en test", "mort / validé"]

export function PapersLibrary() {
  const { data, error, loading } = useApi(() => api.getPapersStatus(), [])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Bibliothèque de papiers</h1>
        <p className="text-sm text-muted-foreground">
          Ingestion PDF, fiche papier multilingue, score de testabilité, file de triage.
        </p>
      </div>

      {loading && <LoadingState />}
      {error && <ErrorState error={error} />}

      {data && (
        <Card className="rounded-none border-destructive/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <span aria-hidden="true">&#9888;</span>
              Module non construit
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive">{data.message}</p>
          </CardContent>
        </Card>
      )}

      <Card className="rounded-none">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            File de triage prévue — à venir, non fonctionnelle
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2">
            {TRIAGE_STAGES.map((stage, index) => (
              <span key={stage} className="flex items-center gap-2">
                <Badge
                  variant="outline"
                  className="rounded-none border-dashed text-muted-foreground opacity-60"
                >
                  {stage}
                </Badge>
                {index < TRIAGE_STAGES.length - 1 && (
                  <span aria-hidden="true" className="text-muted-foreground opacity-60">
                    &rarr;
                  </span>
                )}
              </span>
            ))}
          </div>
          <Separator className="my-4" />
          <p className="text-xs text-muted-foreground">
            Illustration de l'enchaînement des statuts prévu par la spécification (Phase 7).
            Aucun papier, aucun filtre et aucun compteur réels n'existent encore : cette rangée
            n'est ni cliquable ni connectée à des données.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
