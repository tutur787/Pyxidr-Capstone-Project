import { useEffect, useState } from 'react'

interface BondRate {
  symbol: string
  name: string
  yield_pct: number
  change_bps: number
  direction: 'up' | 'down'
}

interface Props {
  date: string
}

const STUBS: BondRate[] = [
  { symbol: 'US3M',  name: 'US T-Bill 3M',  yield_pct: 5.25, change_bps:  2, direction: 'up'   },
  { symbol: 'US1Y',  name: 'US Treasury 1Y', yield_pct: 5.10, change_bps: -1, direction: 'down' },
  { symbol: 'US5Y',  name: 'US Treasury 5Y', yield_pct: 4.35, change_bps:  3, direction: 'up'   },
  { symbol: 'GILTS', name: 'UK Gilts 10Y',   yield_pct: 4.20, change_bps: -2, direction: 'down' },
  { symbol: 'CAD5Y', name: 'CAD Govt 5Y',    yield_pct: 3.75, change_bps:  1, direction: 'up'   },
]

function RateRow({ r }: { r: BondRate }) {
  const up     = r.direction === 'up'
  const clr    = up ? 'text-emerald-400' : 'text-red-400'
  const bg     = up ? 'bg-emerald-500/8' : 'bg-red-500/8'
  const border = up ? 'border-emerald-500/15' : 'border-red-500/15'

  return (
    <div className={`flex items-center justify-between px-3 py-2.5 rounded-xl border ${border} ${bg} hover:brightness-110 transition-all`}>
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-text-primary font-mono font-bold text-sm w-14 flex-shrink-0">{r.symbol}</span>
        <span className="text-text-muted text-xs truncate hidden sm:block">{r.name}</span>
      </div>
      <div className="flex items-center gap-4 flex-shrink-0">
        <span className="text-text-primary font-mono font-semibold text-sm tabular-nums">
          {r.yield_pct.toFixed(2)}%
        </span>
        <div className={`flex items-center gap-1 min-w-[80px] justify-end ${clr}`}>
          <span className="text-xs font-bold">{up ? '▲' : '▼'}</span>
          <span className="font-mono text-xs tabular-nums">
            {up ? '+' : ''}{r.change_bps} bps
          </span>
        </div>
      </div>
    </div>
  )
}

export default function MarketsPanel({ date }: Props) {
  const [rates, setRates]     = useState<BondRate[]>(STUBS)
  const [loading, setLoading] = useState(true)
  const [live, setLive]       = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch(`/api/markets?date=${date}`)
      .then(r => r.json())
      .then((data: BondRate[]) => {
        if (cancelled) return
        if (data && data.length > 0) {
          setRates(data)
          setLive(true)
        } else {
          setRates(STUBS)
          setLive(false)
        }
      })
      .catch(() => {
        if (!cancelled) { setRates(STUBS); setLive(false) }
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [date])

  return (
    <div className="bg-surface-1 rounded-2xl border border-border p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-text-primary font-semibold text-sm">Rates</h2>
          <p className="text-text-muted text-xs mt-0.5">{live ? `As of ${date}` : `Sim date ${date}`}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${live
          ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
          : 'text-text-muted border-border bg-surface-2'}`}>
          {live ? '● Live' : '○ Stub'}
        </span>
      </div>

      <div className="flex items-center justify-between px-3 mb-1.5">
        <span className="text-text-muted text-xs">Instrument</span>
        <div className="flex gap-4">
          <span className="text-text-muted text-xs">Yield</span>
          <span className="text-text-muted text-xs min-w-[80px] text-right">Change</span>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-text-muted text-sm animate-pulse">Fetching rates…</span>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5 flex-1">
          {rates.map(r => <RateRow key={r.symbol} r={r} />)}
        </div>
      )}
    </div>
  )
}
