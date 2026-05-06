import { useEffect, useState } from 'react'
import { stubKPIs } from '../../data/stubs'
import type { PortfolioKPIs } from '../../types'

interface Props {
  date: string
}

interface MetricProps {
  label: string
  value: string
  change?: number
  unit?: string
  neutral?: boolean
  live?: boolean
}

function Metric({ label, value, change, unit, neutral, live }: MetricProps) {
  const changeColor = neutral ? 'text-gray-300' : change !== undefined
    ? change >= 0 ? 'text-emerald-400' : 'text-red-400'
    : 'text-gray-300'

  return (
    <div className="bg-gray-800/60 rounded-xl p-4 border border-gray-700/50 hover:border-gray-600 transition-colors">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-gray-500 text-xs uppercase tracking-wider">{label}</p>
        {live && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 opacity-70" title="Live from BigQuery" />}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-xl font-mono font-semibold ${changeColor}`}>{value}</span>
        {unit && <span className="text-gray-500 text-xs">{unit}</span>}
      </div>
      {change !== undefined && (
        <p className={`text-xs mt-1 ${change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {change >= 0 ? '▲' : '▼'} {Math.abs(change).toFixed(2)}%
        </p>
      )}
    </div>
  )
}

function formatValue(n: number): string {
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000)     return `$${(n / 1_000_000).toFixed(0)}M`
  return `$${n.toLocaleString()}`
}

export default function PortfolioKPI({ date }: Props) {
  const [kpis, setKpis]       = useState<PortfolioKPIs>(stubKPIs)
  const [loading, setLoading] = useState(true)
  const [live, setLive]       = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch(`/api/portfolio/kpis?date=${date}`)
      .then(r => r.json())
      .then((data: PortfolioKPIs) => {
        if (cancelled) return
        setKpis(data)
        // Fields that come live from BQ are non-stub values
        setLive(data.n_bonds !== 104 || data.spread_bps !== 71)
      })
      .catch(() => { if (!cancelled) { setKpis(stubKPIs); setLive(false) } })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [date])

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-white font-semibold text-sm tracking-wide">Portfolio KPI</h2>
          <p className="text-gray-500 text-xs mt-0.5">FABN Spread Portfolio</p>
        </div>
        <div className="flex items-center gap-2">
          {loading && <span className="text-gray-600 text-xs animate-pulse">Loading…</span>}
          <span className={`px-2 py-1 border text-xs rounded-full ${live
            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
            : 'bg-gray-800 border-gray-700 text-gray-500'}`}>
            {live ? '● BQ Live' : '○ Stub'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 content-start">
        <Metric label="Portfolio Value"  value={formatValue(kpis.value)}                       neutral />
        <Metric label="Total Return"     value={`+${kpis.total_return.toFixed(2)}%`}           change={kpis.total_return} />
        <Metric label="YTD Return"       value={`${kpis.ytd_return >= 0 ? '+' : ''}${kpis.ytd_return.toFixed(2)}%`} change={kpis.ytd_return} />
        <Metric label="Portfolio Yield"  value={kpis.yield_pct.toFixed(2)} unit="%" neutral live={live} />
        <Metric label="Duration"         value={kpis.duration.toFixed(2)}  unit="yrs" neutral live={live} />
        <Metric label="CVaR (95%)"       value={kpis.cvar_pct.toFixed(2)}  unit="%" change={-kpis.cvar_pct} />
        <Metric label="Sharpe Ratio"     value={kpis.sharpe.toFixed(2)}    change={kpis.sharpe - 1} />
        <Metric label="Avg Spread"       value={kpis.spread_bps.toString()} unit="bps" neutral live={live} />
        <Metric label="# Bonds"          value={kpis.n_bonds.toString()}   neutral live={live} />
        <Metric label="RBC C1 Usage"     value={`${(kpis.rbc_c1_usage * 100).toFixed(0)}%`} neutral />
      </div>
    </div>
  )
}
