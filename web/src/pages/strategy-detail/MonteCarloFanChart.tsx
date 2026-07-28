import { CartesianGrid, ComposedChart, Area, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { formatNumber } from "@/components/StatCell"
import type { MonteCarloFan } from "@/lib/types"

/**
 * Fan chart Monte Carlo : bande p10–p90 (incertitude de trajectoire) et
 * médiane p50 en trait distinct. La bande est construite par empilement
 * (p10 transparent, delta p90-p10 teinté) — le motif standard recharts pour
 * une aire "range" sans dépendre d'une API de version spécifique.
 */
export function MonteCarloFanChart({ fan }: { fan: MonteCarloFan }) {
  const data = fan.trade_index.map((tradeIndex, i) => ({
    trade: tradeIndex,
    p10: fan.p10[i],
    band: fan.p90[i] - fan.p10[i],
    p50: fan.p50[i],
    p90: fan.p90[i],
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
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
        <Tooltip
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 2,
            fontSize: 12,
          }}
          labelFormatter={(v) => `trade #${v}`}
          formatter={(value, name, item) => {
            const payload = item?.payload as { p10?: number; p90?: number } | undefined
            if (name === "band") {
              return [
                `[${formatNumber(payload?.p10 ?? 0, 3)}, ${formatNumber(payload?.p90 ?? 0, 3)}]`,
                "p10–p90",
              ]
            }
            if (name === "p50") return [formatNumber(Number(value), 3), "médiane (p50)"]
            return [formatNumber(Number(value), 3), String(name)]
          }}
        />
        <Area dataKey="p10" stackId="fan" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area
          dataKey="band"
          stackId="fan"
          stroke="none"
          fill="var(--color-muted-foreground)"
          fillOpacity={0.18}
          isAnimationActive={false}
        />
        <Line type="monotone" dataKey="p50" stroke="var(--color-foreground)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
