import type { OptimizerResult, PortfolioKPIs } from '../../types'
import { stubKPIs } from '../../data/stubs'

interface Props {
  date:              string
  optimizerResult?:  OptimizerResult | null
  optimizerLoading?: boolean
}

interface MetricProps {
  label:    string
  value:    string
  change?:  number
  unit?:    string
  neutral?: boolean
  live?:    boolean
}

function Metric({ label, value, change, unit, neutral, live }: MetricProps) {
  const changeColor = neutral ? 'text-gray-300' : change !== undefined
    ? change >= 0 ? 'text-emerald-400' : 'text-red-400'
    : 'text-gray-300'

  return (
    <div className="bg-gray-800/60 rounded-xl p-4 border border-gray-700/50 hover:border-gray-600 transition-colors">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-gray-500 text-xs uppercase tracking-wider">{label}</p>
        {live && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 opacity-70" title="Live from optimizer" />}
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

export default function PortfolioKPI({ date, optimizerResult, optimizerLoading }: Props) {
  const isOptimal = optimizerResult?.status === 'optimal'

  // Derive KPIs from optimizer result when available, else fall back to stubs
  const kpis: PortfolioKPIs = isOptimal && optimizerResult
    ? {
        value:        500_000_000,
        total_return: (optimizerResult.nev / 500_000_000) * 100,
        yield_pct:    optimizerResult.yield_pct,
        duration:     optimizerResult.duration,
        cvar_pct:     2.87,    // stub — requires scenario analysis
        sharpe:       1.34,    // stub — requires return history
        n_bonds:      optimizerResult.n_bonds_selected,
        ytd_return:   3.41,    // stub — requires historical context
        spread_bps:   optimizerResult.spread_bps,
        rbc_c1_usage: optimizerResult.rbc_c1_usage,
      }
    : stubKPIs

  const loading = optimizerLoading ?? false

  const badgeClass = isOptimal
    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
    : 'bg-gray-800 border-gray-700 text-gray-500'

  const badgeLabel = isOptimal ? '● Optimizer' : '○ Stub'

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-white font-semibold text-sm tracking-wide">Portfolio KPI</h2>
          <p className="text-gray-500 text-xs mt-0.5">
            FABN Spread Portfolio{isOptimal ? ` · ${date}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {loading && (
            <span className="text-amber-400 text-xs animate-pulse">Optimizing…</span>
          )}
          <span className={`px-2 py-1 border text-xs rounded-full ${badgeClass}`}>
            {badgeLabel}
          </span>
        </div>
      </div>

      {/* Scrollable content — prevents NEV strip from being clipped */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid grid-cols-2 gap-3 content-start">
          <Metric label="Portfolio Value"  value={formatValue(kpis.value)}                         neutral />
          <Metric label="Total Return"     value={`${kpis.total_return >= 0 ? '+' : ''}${kpis.total_return.toFixed(2)}%`}
                                                                                                   change={kpis.total_return} />
          <Metric label="YTD Return"       value={`${kpis.ytd_return >= 0 ? '+' : ''}${kpis.ytd_return.toFixed(2)}%`}
                                                                                                   change={kpis.ytd_return} />
          <Metric label="Portfolio Yield"  value={kpis.yield_pct.toFixed(2)} unit="%" neutral      live={isOptimal} />
          <Metric label="Duration"         value={kpis.duration.toFixed(2)}  unit="yrs" neutral    live={isOptimal} />
          <Metric label="CVaR (95%)"       value={kpis.cvar_pct.toFixed(2)}  unit="%"             change={-kpis.cvar_pct} />
          <Metric label="Sharpe Ratio"     value={kpis.sharpe.toFixed(2)}                         change={kpis.sharpe - 1} />
          <Metric label="Avg Spread"       value={kpis.spread_bps.toFixed(1)} unit="bps" neutral  live={isOptimal} />
          <Metric label="# Bonds"          value={kpis.n_bonds.toString()}    neutral              live={isOptimal} />
          <Metric label="RBC C1 Usage"     value={`${(kpis.rbc_c1_usage * 100).toFixed(1)}%`} neutral live={isOptimal} />
        </div>

        {isOptimal && optimizerResult && (
          <div className="mt-4 pt-4 border-t border-gray-800">
            <p className="text-gray-600 text-xs mb-2 uppercase tracking-wider">SAP Breakdown</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="bg-gray-800/40 rounded-lg p-2.5">
                <p className="text-gray-500">Statutory NII</p>
                <p className="text-emerald-400 font-mono font-semibold mt-0.5">
                  ${(optimizerResult.spread_income / 1e6).toFixed(2)}M
                </p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2.5">
                <p className="text-gray-500">Capital Cost</p>
                <p className="text-red-400 font-mono font-semibold mt-0.5">
                  −${(optimizerResult.capital_cost / 1e6).toFixed(2)}M
                </p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2.5">
                <p className="text-gray-500">SAP Objective</p>
                <p className="text-amber-400 font-mono font-semibold mt-0.5">
                  ${(optimizerResult.nev / 1e6).toFixed(2)}M
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
