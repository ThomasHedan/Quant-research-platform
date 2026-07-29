import { NavLink, Outlet } from "react-router-dom"
import { cn } from "@/lib/utils"
import { useApi } from "@/hooks/useApi"
import { api } from "@/lib/api"

const NAV = [
  { to: "/", label: "Leaderboard", end: true },
  { to: "/risk-surface", label: "Surface de risque" },
  { to: "/portfolio", label: "Combinaisons" },
  { to: "/data", label: "Données" },
  { to: "/papers", label: "Papiers" },
  { to: "/trials", label: "Essais" },
]

/**
 * Coquille de navigation. Le compteur global d'essais est visible ici en
 * permanence, pas seulement sur la vue Journal d'essais — c'est l'entrée du
 * Deflated Sharpe Ratio, l'utilisateur doit le voir monter (CLAUDE.md §4).
 */
export function AppShell() {
  const { data } = useApi(() => api.trialCount(), [])

  return (
    <div className="min-h-svh flex flex-col">
      {/* Filet de bezel — pas une ombre, un repère d'instrument. */}
      <div className="h-[2px] bg-signal/70 shrink-0" />
      <header className="border-b border-border bg-card">
        {/* Le conteneur défilant a besoin de sa propre marge verticale : un
            enfant qui touche son bord haut/bas se ferait rogner l'anneau de
            focus clavier par le `overflow-x-auto` (clipping d'outline connu
            de Chromium) — jamais de hauteur pleine sur les liens ici. */}
        <div className="mx-auto max-w-[1400px] px-4 flex items-center gap-7 py-3.5 overflow-x-auto">
          <span className="flex items-center gap-2 shrink-0">
            <span
              aria-hidden="true"
              className="size-2 rounded-[1px] bg-signal"
            />
            <span className="text-sm font-semibold tracking-[0.08em]">EDGELAB</span>
          </span>
          <nav className="flex items-center gap-1 text-sm shrink-0">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "px-2.5 py-1 border-b-2 transition-colors whitespace-nowrap",
                    isActive
                      ? "border-signal text-foreground font-medium"
                      : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div
            className="ml-auto flex items-center gap-1.5 rounded-full border border-border bg-secondary/50 pl-2 pr-2.5 py-1 shrink-0 whitespace-nowrap"
            title="Compteur global d'essais — l'entrée du Deflated Sharpe Ratio"
          >
            <span aria-hidden="true" className="size-1.5 rounded-full bg-signal animate-pulse" />
            <span className="num text-xs text-muted-foreground">
              essais&nbsp;<span className="text-foreground font-medium">{data?.count ?? "—"}</span>
            </span>
          </div>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-[1400px] px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
