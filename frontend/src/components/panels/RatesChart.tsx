import { useEffect, useMemo, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { generateStubRates } from '../../data/stubs'
import type { RatePoint } from '../../types'

interface Props {
  date: string
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface-2 border border-border rounded-xl px-3 py-2 text-xs shadow-xl">
      <p className="text-text-muted mb-1.5 font-mono">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }} className="font-mono">
          {p.name}: {p.value?.toFixed(2)}
        </p>
      ))}
    </div>
  )
}

export default function RatesChart({ date }: Props) {
  const [data, setData]       = useState<RatePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [live, setLive]       = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch(`/api/rates?date=${date}`)
      .then(r => r.json())
      .then((rows: RatePoint[]) => {
        if (cancelled) return
        if (rows && rows.length > 0) {
          setData(rows)
          setLive(true)
        } else {
          setData(generateStubRates(date, 90))
          setLive(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(generateStubRates(date, 90))
          setLive(false)
        }
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [date])

  const thinned = useMemo(() => data.filter((_, i) => i % 3 === 0), [data])

  return (
    <div className="bg-surface-1 rounded-2xl border border-border p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-text-primary font-semibold text-sm">
            {live ? 'Bond ETF Prices' : 'Treasury Rates'}
          </h2>
          <p className="text-text-muted text-xs mt-0.5">
            {live ? 'SHY (2Y proxy) · IEF (10Y proxy) — indexed to 100' : '90-day trailing · simulated'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-3 text-xs">
            <span className="flex items-center gap-1.5 text-red-400">
              <span className="w-3 h-0.5 bg-red-400 rounded-lg inline-block" />
              {live ? 'SHY' : '2Y'}
            </span>
            <span className="flex items-center gap-1.5 text-emerald-400">
              <span className="w-3 h-0.5 bg-emerald-400 rounded-lg inline-block" />
              {live ? 'IEF' : '10Y'}
            </span>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full border ${live
            ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
            : 'text-text-muted border-border bg-surface-2'}`}>
            {live ? '● Live' : '○ Stub'}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-text-muted text-sm animate-pulse">Loading rates…</span>
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={thinned} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => v.slice(5)}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="rate_2y"  name={live ? 'SHY' : '2Y'}  stroke="#f87171" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
              <Line type="monotone" dataKey="rate_10y" name={live ? 'IEF' : '10Y'} stroke="#34d399" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
