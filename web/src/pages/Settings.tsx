import { useState } from "react"
import { cn } from "@/lib/utils"
import { api, ApiError } from "@/lib/api"
import { useApi } from "@/hooks/useApi"
import type { CredentialStatus, SettingsResponse } from "@/lib/types"
import { ErrorState, LoadingState } from "@/components/DataState"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

const SOURCE_LABELS: Record<string, string> = {
  environment: "variable d'environnement",
  file: "fichier local",
  absent: "non renseignée",
}

/**
 * Réglages : les clés API de la plateforme.
 *
 * Une clé posée ici n'est jamais relue par l'API — il n'existe aucun endpoint
 * qui renvoie un secret, et cette page ne peut donc afficher qu'un état masqué.
 * Conséquence assumée : on ne peut pas « vérifier » une clé enregistrée en la
 * relisant, seulement la remplacer.
 */
export function Settings() {
  const [refreshKey, setRefreshKey] = useState(0)
  const settings = useApi(() => api.getSettings(), [refreshKey])
  const [override, setOverride] = useState<SettingsResponse | null>(null)
  const current = override ?? settings.data

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Réglages</h1>
        <p className="max-w-[80ch] text-sm text-muted-foreground">
          Clés API des fournisseurs. Elles sont écrites dans un fichier local en 0600, hors du
          dépôt git, et ne sont jamais renvoyées en clair par l'API — cette page ne peut afficher
          que les derniers caractères.
        </p>
      </div>

      {settings.loading && <LoadingState />}
      {settings.error && <ErrorState error={settings.error} />}

      {current ? (
        <>
          <div className="border-y border-border py-3 text-xs text-muted-foreground">
            <p>
              fichier : <span className="num">{current.credentials_file}</span>
            </p>
            <p className="mt-1 max-w-[80ch]">
              Une variable d'environnement du même nom a toujours la priorité sur ce fichier. L'API
              n'a aucune authentification : l'écriture d'une clé n'est acceptée que depuis la
              machine locale, et le serveur ne doit pas écouter sur une interface publique.
            </p>
          </div>

          <div className="flex flex-col gap-4">
            {current.credentials.map((credential) => (
              <CredentialCard
                key={credential.env_var}
                credential={credential}
                onChanged={setOverride}
              />
            ))}
          </div>

          <AddCredentialCard
            onChanged={(next) => {
              setOverride(next)
              setRefreshKey((k) => k + 1)
            }}
          />
        </>
      ) : null}
    </div>
  )
}

function CredentialCard({
  credential,
  onChanged,
}: {
  credential: CredentialStatus
  onChanged: (settings: SettingsResponse) => void
}) {
  const [value, setValue] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fromEnv = credential.source === "environment"

  async function save() {
    setBusy(true)
    setError(null)
    try {
      onChanged(await api.setCredential(credential.env_var, value))
      setValue("")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      onChanged(await api.deleteCredential(credential.env_var))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="rounded-none">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            <span className={cn(credential.label === credential.env_var && "num")}>
              {credential.label}
            </span>
            {credential.label === credential.env_var ? null : (
              <span className="num font-normal text-muted-foreground">{credential.env_var}</span>
            )}
            {credential.wired ? null : (
              <span className="inline-flex items-center rounded-sm border border-border px-1.5 py-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                lue par aucun module
              </span>
            )}
          </h2>
          <p className="max-w-[70ch] text-xs text-muted-foreground">{credential.description}</p>
          {credential.docs_url ? (
            <a
              href={credential.docs_url}
              target="_blank"
              rel="noreferrer"
              className="w-fit text-xs underline underline-offset-4 hover:text-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal"
            >
              obtenir une clé
            </a>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">état</span>
          <span
            className={cn(
              "num text-sm font-medium",
              credential.configured ? "text-signal" : "text-muted-foreground",
            )}
          >
            {credential.configured ? credential.hint : "non renseignée"}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {SOURCE_LABELS[credential.source] ?? credential.source}
          </span>
        </div>
      </CardHeader>

      <CardContent className="flex flex-col gap-2">
        {fromEnv ? (
          <p className="text-xs text-muted-foreground">
            Cette clé vient d'une variable d'environnement et gardera la priorité sur toute valeur
            écrite ici. Pour piloter la clé depuis cette page, retire l'export de ton shell.
          </p>
        ) : null}
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-1 flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {credential.configured ? "remplacer la clé" : "nouvelle clé"}
            </span>
            <Input
              type="password"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="h-8 min-w-64 text-xs"
              placeholder="collée depuis le fournisseur"
            />
          </label>
          <Button
            type="button"
            variant="outline"
            className="h-8 text-xs"
            disabled={busy || value.trim() === ""}
            onClick={save}
          >
            {busy ? "enregistrement…" : "enregistrer"}
          </Button>
          {credential.source === "file" ? (
            <Button
              type="button"
              variant="ghost"
              className="h-8 text-xs text-destructive"
              disabled={busy}
              onClick={remove}
            >
              supprimer
            </Button>
          ) : null}
        </div>
        {error ? (
          <p className="text-xs text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function AddCredentialCard({ onChanged }: { onChanged: (settings: SettingsResponse) => void }) {
  const [envVar, setEnvVar] = useState("")
  const [value, setValue] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      onChanged(await api.setCredential(envVar.trim().toUpperCase(), value))
      setEnvVar("")
      setValue("")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="rounded-none">
      <CardHeader>
        <h2 className="text-sm font-semibold">Ajouter une clé</h2>
        <p className="max-w-[80ch] text-xs text-muted-foreground">
          Pour un fournisseur qu'EdgeLab ne lit pas encore. La clé est stockée et exposée comme les
          autres, mais rien ne l'utilisera tant que le module correspondant n'existe pas — elle
          apparaîtra marquée comme telle plutôt que de laisser croire qu'elle fait quelque chose.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              nom (style variable d'environnement)
            </span>
            <Input
              value={envVar}
              onChange={(e) => setEnvVar(e.target.value)}
              className="num h-8 w-56 text-xs"
              placeholder="POLYGON_API_KEY"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">clé</span>
            <Input
              type="password"
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="h-8 min-w-56 text-xs"
            />
          </label>
          <Button
            type="button"
            variant="outline"
            className="h-8 text-xs"
            disabled={busy || envVar.trim() === "" || value.trim() === ""}
            onClick={save}
          >
            {busy ? "enregistrement…" : "ajouter"}
          </Button>
        </div>
        {error ? (
          <p className="text-xs text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
