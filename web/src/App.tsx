import { BrowserRouter, Route, Routes } from "react-router-dom"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppShell } from "@/components/AppShell"
import { Leaderboard } from "@/pages/Leaderboard"
import { StrategyDetail } from "@/pages/StrategyDetail"
import { RiskSurfacePage } from "@/pages/RiskSurfacePage"
import { PortfolioExplorer } from "@/pages/PortfolioExplorer"
import { PapersLibrary } from "@/pages/PapersLibrary"
import { TrialLog } from "@/pages/TrialLog"

function App() {
  return (
    <TooltipProvider delayDuration={150}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Leaderboard />} />
            <Route path="strategies/:strategyId" element={<StrategyDetail />} />
            <Route path="risk-surface" element={<RiskSurfacePage />} />
            <Route path="portfolio" element={<PortfolioExplorer />} />
            <Route path="papers" element={<PapersLibrary />} />
            <Route path="trials" element={<TrialLog />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  )
}

export default App
