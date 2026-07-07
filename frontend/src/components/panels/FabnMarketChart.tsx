import { useMemo } from 'react'
import {
  ComposedChart, Line, Area, ReferenceLine,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type { FabnMarketPoint } from '../../types'

interface Props {
  data: FabnMarketPoint[]
  creditingRate?: number   // FABN's fixed crediting rate, in bps (e.g. 320.5)
  selectedDate?: string    // currently viewed portfolio date (YYYY-MM-DD)
}

// Most recent history row on or before `date`. History is sorted ascending.
export function findPointForDate(history: FabnMarketPoint[], date: string): FabnMarketPoint | null {
  if (history.length === 0) return null
  let candidate = history[0]
  for (const p of history) {
    if (p.date <= date) candidate = p
    else break
  }
  return candidate
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const prime   = payload.find((p: any) => p.dataKey === 'prime_rate_bps')
  const fabn    = payload.find((p: any) => p.dataKey === 'fabn_ytm_bps')
  const treas   = payload.find((p: any) => p.dataKey === 'treasury_ytm_bps')
  const spread  = payload.find((p: any) => p.dataKey === 'spread_bps')
  return (
    <div className="glass border border-border rounded-2xl p-3 text-xs shadow-xl min-w-[170px]">
      <p className="text-text-muted font-medium mb-2">{label}</p>
      {prime  && <p className="text-text-muted mb-0.5">Prime Rate <span className="font-mono float-right">{prime.value.toFixed(0)} bps</span></p>}
      {fabn   && <p style={{ color: 'var(--brand-accent)' }} className="mb-0.5">FABN YTM <span className="font-mono float-right">{fabn.value.toFixed(0)} bps</span></p>}
      {treas  && <p className="text-text-secondary mb-0.5">Treasury YTM <span className="font-mono float-right">{treas.value.toFixed(0)} bps</span></p>}
      {spread && <p style={{ color: 'var(--brand-highlight)' }} className="font-semibold">Spread <span className="font-mono float-right">{spread.value.toFixed(0)} bps</span></p>}
    </div>
  )
}

export default function FabnMarketChart({ data, creditingRate, selectedDate }: Props) {
  const visibleData = useMemo(
    () => selectedDate ? data.filter(d => d.date <= selectedDate) : data,
    [data, selectedDate],
  )

  const bpsData = useMemo(() => visibleData.map(d => ({
    ...d,
    prime_rate_bps:    d.prime_rate * 100,
    fabn_ytm_bps:      d.fabn_ytm * 100,
    treasury_ytm_bps:  d.treasury_ytm * 100,
  })), [visibleData])

  const currentPoint = selectedDate ? findPointForDate(data, selectedDate) : null

  if (data.length === 0) {
    return (
      <div className="h-52 bg-surface-2/40 rounded-2xl border border-border border-dashed flex items-center justify-center">
        <p className="text-text-muted text-sm">Loading FABN market history…</p>
      </div>
    )
  }

  return (
    <div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={bpsData} margin={{ top: 22, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
              tickFormatter={(d: string) => d.slice(0, 4)}
              interval="preserveStartEnd"
              minTickGap={80}
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
              tickFormatter={(v: number) => `${v.toFixed(0)}`}
              width={44}
              label={{ value: 'bps', angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 10 }}
            />
            <Tooltip content={<ChartTooltip />} />

            {creditingRate !== undefined && (
              <ReferenceLine
                y={creditingRate}
                stroke="var(--text-secondary)"
                strokeDasharray="3 3"
                strokeWidth={1.5}
                label={{ value: `Crediting ${creditingRate.toFixed(0)} bps`, fill: 'var(--text-secondary)', fontSize: 9, position: 'insideBottomRight' }}
              />
            )}

            {currentPoint && (
              <ReferenceLine
                x={currentPoint.date}
                stroke="var(--brand-highlight)"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{ value: `▲ ${currentPoint.date}`, fill: 'var(--brand-highlight)', fontSize: 9, position: 'top' }}
              />
            )}

            <Area
              type="monotone"
              dataKey="spread_bps"
              stroke="none"
              fill="var(--brand-highlight)"
              fillOpacity={0.12}
            />
            <Line
              type="stepAfter"
              dataKey="prime_rate_bps"
              stroke="var(--text-muted)"
              strokeWidth={1.5}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="treasury_ytm_bps"
              stroke="var(--text-secondary)"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="fabn_ytm_bps"
              stroke="var(--brand-accent)"
              strokeWidth={2.25}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-4 justify-center mt-1.5 text-xs text-text-muted flex-wrap">
        <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2" style={{ borderColor: 'var(--text-muted)' }} />Prime Rate</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2" style={{ borderColor: 'var(--brand-accent)' }} />FABN YTM</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: 'var(--text-secondary)' }} />Treasury YTM</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-md" style={{ backgroundColor: 'var(--brand-highlight)', opacity: 0.4 }} />Spread (bps)</span>
        {creditingRate !== undefined && (
          <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: 'var(--text-secondary)' }} />FABN Crediting Rate</span>
        )}
        {currentPoint && (
          <span className="flex items-center gap-1.5"><span className="inline-block w-px h-3" style={{ backgroundColor: 'var(--brand-highlight)' }} />Selected date</span>
        )}
      </div>
    </div>
  )
}
