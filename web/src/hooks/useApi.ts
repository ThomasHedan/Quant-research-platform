import { useEffect, useState } from "react"
import { ApiError } from "@/lib/api"

export interface ApiState<T> {
  data: T | undefined
  error: ApiError | Error | undefined
  loading: boolean
}

/**
 * Charge `fetcher()` au montage et à chaque changement de `deps`. Pas de
 * cache inter-vues : chaque page reflète l'artefact au moment où elle
 * s'ouvre, cohérent avec le principe d'un registre d'essais qui ne ment
 * jamais sur son état courant.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: React.DependencyList): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({
    data: undefined,
    error: undefined,
    loading: true,
  })

  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: undefined }))
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ data, error: undefined, loading: false })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            data: undefined,
            error: error instanceof Error ? error : new Error(String(error)),
            loading: false,
          })
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
