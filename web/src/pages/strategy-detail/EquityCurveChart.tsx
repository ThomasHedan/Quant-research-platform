import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { formatNumber } from "@/components/StatCell"

/**
 * Courbe d'equity — rendement cumulé par trade. Ligne unique, encre neutre :
 * ce graphique décrit une trajectoire, il ne porte aucun jugement de
 * signification (c'est le rôle du t-stat et du DSR affichés ailleurs).
 */
export function EquityCurveChart({ equityCurve }: { equityCurve: number[] }) {
  const data = equityCurve.map((cumulativeReturn, index) => ({
    trade: index + 1,
    cumulativeReturn,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="2 3" stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="trade"
          tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
          stroke="var(--color-border)"
          label={{ value: "trade #", position: "insideBottom", offset: -2, fontSize: 11, fill: "var(--color-muted-foreground)" }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
          stroke="var(--color-border)"
          width={56}
          tickFormatter={(v: number) => formatNumber(v, 2)}
        />
        <ReferenceLine y={0} stroke="var(--color-border)" />
        <Tooltip
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 2,
            fontSize: 12,
          }}
          labelFormatter={(v) => `trade #${v}`}
          formatter={(v) => [formatNumber(Number(v), 3), "cumulé"]}
        />
        <Line
          type="monotone"
          dataKey="cumulativeReturn"
          stroke="var(--color-foreground)"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
