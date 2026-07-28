import { NavLink, Outlet } from "react-router-dom"
import { cn } from "@/lib/utils"
import { useApi } from "@/hooks/useApi"
import { api } from "@/lib/api"

const NAV = [
  { to: "/", label: "Leaderboard", end: true },
  { to: "/risk-surface", label: "Surface de risque" },
  { to: "/portfolio", label: "Combinaisons" },
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
      <header className="border-b border-border bg-card">
        <div className="mx-auto max-w-[1400px] px-4 flex items-center gap-6 h-12">
          <span className="text-sm font-semibold tracking-tight">EDGELAB</span>
          <nav className="flex items-center gap-1 text-sm">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "px-2.5 py-1 rounded-sm transition-colors",
                    isActive
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto num text-xs text-muted-foreground" title="Compteur global d'essais — l'entrée du Deflated Sharpe Ratio">
            essais : <span className="text-foreground font-medium">{data?.count ?? "—"}</span>
          </div>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-[1400px] px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
