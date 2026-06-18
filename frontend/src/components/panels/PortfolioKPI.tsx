import { useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type { OptimizerResult, PortfolioKPIs, HistoryEntry } from '../../types'
import { stubKPIs } from '../../data/stubs'

interface Props {
  date:              string
  optimizerResult?:  OptimizerResult | null
  optimizerLoading?: boolean
  history?:          HistoryEntry[]
}

interface MetricProps {
  label:      string
  value:      string
  change?:    number
  unit?:      string
  neutral?:   boolean
  live?:      boolean
  onClick?:   () => void
  expanded?:  boolean
  title?:     string
  sublabel?:  string
  valueColor?: string  // explicit color override (e.g. text-amber-400, text-blue-400)
}

function Metric({ label, value, change, unit, neutral, live, onClick, expanded, title, sublabel, valueColor }: MetricProps) {
  const textColor = valueColor ?? (
    neutral ? 'text-gray-300' : change !== undefined
      ? change >= 0 ? 'text-emerald-400' : 'text-red-400'
      : 'text-gray-300'
  )

  return (
    <div
      onClick={onClick}
      title={title}
      className={`bg-gray-800/60 rounded-xl p-4 border transition-colors
        ${onClick ? 'cursor-pointer hover:border-amber-500/40' : 'hover:border-gray-600'}
        ${expanded ? 'border-amber-500/40' : 'border-gray-700/50'}`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-gray-500 text-xs uppercase tracking-wider">{label}</p>
        <div className="flex items-center gap-1.5">
          {live && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 opacity-70" title="Live from optimizer" />}
          {onClick && (
            <span className={`text-gray-600 text-xs transition-transform ${expanded ? 'rotate-180' : ''}`}>▾</span>
          )}
        </div>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-xl font-mono font-semibold ${textColor}`}>{value}</span>
        {unit && <span className="text-gray-500 text-xs">{unit}</span>}
      </div>
      {sublabel && <p className="text-gray-600 text-[10px] mt-0.5">{sublabel}</p>}
      {change !== undefined && !valueColor && (
        <p className={`text-xs mt-1 ${change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {change >= 0 ? '▲' : '▼'} {Math.abs(change).toFixed(2)}%
        </p>
      )}
    </div>
  )
}

function SectionLabel({ children }: { children: string }) {
  return <p className="text-gray-600 text-xs uppercase tracking-wider pt-1">{children}</p>
}

function formatValue(n: number): string {
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000)     return `$${(n / 1_000_000).toFixed(0)}M`
  if (n >= 1_000)         return `$${(n / 1_000).toFixed(1)}k`
  return `$${n.toLocaleString()}`
}

function ytdFraction(dateIso: string): number {
  const d = new Date(dateIso + 'T00:00:00')
  const jan1 = new Date(d.getFullYear(), 0, 1)
  return (d.getTime() - jan1.getTime()) / (365.25 * 24 * 3600 * 1000)
}

// ── Evolution modal ────────────────────────────────────────────────────────────
interface EvolutionModalProps {
  title:     string
  data:      HistoryEntry[]
  dataKey:   keyof HistoryEntry
  formatter: (v: number) => string
  annotation?: string
  onClose:   () => void
}

function EvolutionModal({ title, data, dataKey, formatter, annotation, onClose }: EvolutionModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-[520px] shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-white font-semibold text-sm">{title}</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>
        {annotation && (
          <p className="text-gray-500 text-xs mb-4">{annotation}</p>
        )}

        {data.length < 2 ? (
          <div className="h-40 flex items-center justify-center">
            <p className="text-gray-600 text-sm">Visit more dates to see the evolution chart</p>
          </div>
        ) : (
          <div className="h-48 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                <defs>
                  <linearGradient id="modal-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1f2937" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickFormatter={(d: string) => d.slice(5)}
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  tickFormatter={(v: number) => formatter(v)}
                  width={70}
                />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [formatter(v), title]}
                  labelFormatter={(l: string) => l}
                />
                <Area
                  type="monotone"
                  dataKey={dataKey as string}
                  stroke="#f59e0b"
                  strokeWidth={2}
                  fill="url(#modal-grad)"
                  dot={{ r: 3, fill: '#f59e0b', strokeWidth: 0 }}
                  activeDot={{ r: 5 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}

export default function PortfolioKPI({ date, optimizerResult, optimizerLoading, history = [] }: Props) {
  const isOptimal = optimizerResult?.status === 'optimal'
  const [expandedKPI, setExpandedKPI] = useState<string | null>(null)

  function toggleKPI(label: string) {
    setExpandedKPI(prev => prev === label ? null : label)
  }

  const kpis: PortfolioKPIs = isOptimal && optimizerResult
    ? {
        value:        500_000_000,
        total_return: (optimizerResult.nev / 500_000_000) * 100,
        yield_pct:    optimizerResult.yield_pct,
        duration:     optimizerResult.duration,
        cvar_pct:     2.87,
        sharpe:       1.34,
        n_bonds:      optimizerResult.n_bonds_selected,
        ytd_return:   3.41,
        spread_bps:   optimizerResult.spread_bps,
        rbc_c1_usage: optimizerResult.rbc_c1_usage,
      }
    : stubKPIs

  // Live replacements for stub fields
  const liveYtdReturn = isOptimal ? optimizerResult!.yield_pct * ytdFraction(date) : null
  const liveCvar      = isOptimal ? optimizerResult!.duration * 2.0 : null
  const liveCapEff    = isOptimal ? optimizerResult!.rbc_ratio : null

  const loading = optimizerLoading ?? false

  const badgeClass = isOptimal
    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
    : 'bg-gray-800 border-gray-700 text-gray-500'

  const regulatoryCapital  = isOptimal && optimizerResult ? optimizerResult.capital_cost / 0.15 : null
  const cumulativeTxnCost  = history.reduce((s, h) => s + h.txn_cost, 0)
  const marketValue        = isOptimal && optimizerResult
    ? optimizerResult.allocations.reduce((s, a) => s + a.h_opt * a.mid_price / 100, 0)
    : null
  const swapAllocs         = optimizerResult?.swap_allocations ?? []
  const totalSwapNotional  = swapAllocs.reduce((s, a) => s + a.notional, 0)

  // Modal config derived from expandedKPI
  type ModalCfg = { dataKey: keyof HistoryEntry; formatter: (v: number) => string; annotation?: string }
  const modalCfg: Record<string, ModalCfg> = {
    'Portfolio Value': {
      dataKey:    'market_value',
      formatter:  (v: number) => formatValue(v),
      annotation: 'Total portfolio market value = Σ(face × mid price / 100) across visited dates',
    },
    'Trading Cost': {
      dataKey:   'txn_cost',
      formatter: (v: number) => `−${formatValue(v)}`,
      annotation: history.length > 1 ? `Cumulative: −${formatValue(cumulativeTxnCost)}` : undefined,
    },
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 flex flex-col h-full">
      {/* Panel header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div>
          <h2 className="text-white font-semibold text-sm tracking-wide">Portfolio KPI</h2>
          <p className="text-gray-500 text-xs mt-0.5">
            FABN Spread Portfolio{isOptimal ? ` · ${date}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {loading && <span className="text-amber-400 text-xs animate-pulse">Optimizing…</span>}
          <span className={`px-2 py-1 border text-xs rounded-full ${badgeClass}`}>
            {isOptimal ? '● Optimizer' : '○ Stub'}
          </span>
        </div>
      </div>

      {/* Everything scrollable together */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-3">

        {/* ── SAP Breakdown ─────────────────────────────────────────────── */}
        {isOptimal && optimizerResult && (
          <>
            <SectionLabel>SAP Breakdown</SectionLabel>
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="Statutory NII"
                value={`$${(optimizerResult.spread_income / 1e6).toFixed(2)}M`}
                valueColor="text-emerald-400"
                live
                title="Annual net interest income = Σ(book_yield_i − r_FABN) × h_i"
              />
              <Metric
                label="Regulatory Capital"
                value={`$${regulatoryCapital !== null ? (regulatoryCapital / 1e6).toFixed(1) : '—'}M`}
                valueColor="text-blue-400"
                sublabel="required reserve"
                title="Required capital = capital_cost ÷ WACC (0.15) = RBC_bar × Σ(theta_i × h_i)"
              />
              <Metric
                label="SAP Objective"
                value={`$${(optimizerResult.nev / 1e6).toFixed(2)}M`}
                valueColor="text-amber-400"
                live
                title="Maximised quantity: NII − capital_cost − turnover − liquidity_penalty + savings"
              />
              <Metric
                label="Trading Cost"
                value={cumulativeTxnCost > 0 ? `−${formatValue(cumulativeTxnCost)}` : '$0'}
                valueColor="text-red-400"
                sublabel={`this rebalance: −${formatValue(optimizerResult.txn_cost)}`}
                onClick={() => toggleKPI('Trading Cost')}
                expanded={expandedKPI === 'Trading Cost'}
                title="Cumulative bid-ask spread cost across all rebalances this session. Click to see evolution."
              />
              {totalSwapNotional > 1_000 && (
                <Metric
                  label="Swap Notional"
                  value={formatValue(totalSwapNotional)}
                  valueColor="text-purple-400"
                  sublabel={`${swapAllocs.filter(a => a.notional > 1_000).length} receive-fixed`}
                  title="Total notional of receive-fixed interest-rate swaps in the optimal overlay. See Strategy Tracking for details."
                />
              )}
            </div>
            <div className="border-t border-gray-800" />
          </>
        )}

        {/* ── Portfolio Metrics ──────────────────────────────────────────── */}
        <SectionLabel>Portfolio Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-3">
          <Metric
            label="Portfolio Value"
            value={marketValue !== null ? formatValue(marketValue) : formatValue(kpis.value)}
            neutral
            live={isOptimal}
            onClick={() => toggleKPI('Portfolio Value')}
            expanded={expandedKPI === 'Portfolio Value'}
            sublabel={marketValue !== null ? `par $500M · mkt ${((marketValue / 500_000_000) * 100).toFixed(2)}¢` : undefined}
            title="Market value = Σ(face allocation × mid price / 100). Click to see evolution over visited dates."
          />
          <Metric
            label="Net SAP Rate"
            value={`${kpis.total_return >= 0 ? '+' : ''}${kpis.total_return.toFixed(2)}%`}
            change={kpis.total_return}
            live={isOptimal}
            title="SAP objective ÷ $500M — net statutory income rate on invested capital"
          />
          <Metric
            label="YTD Return"
            value={liveYtdReturn !== null
              ? `+${liveYtdReturn.toFixed(2)}%`
              : `${kpis.ytd_return >= 0 ? '+' : ''}${kpis.ytd_return.toFixed(2)}%`}
            change={liveYtdReturn ?? kpis.ytd_return}
            live={isOptimal}
            sublabel={liveYtdReturn !== null ? `${(ytdFraction(date) * 365).toFixed(0)} days elapsed` : undefined}
            title="Accrued statutory book yield YTD = book yield × days since Jan 1"
          />
          <Metric
            label="Portfolio Yield"
            value={kpis.yield_pct.toFixed(2)} unit="%"
            neutral live={isOptimal}
            title="Weighted-average book yield (coupon + amortization/accretion)"
          />
          <Metric
            label="Duration"
            value={kpis.duration.toFixed(2)} unit="yrs"
            neutral live={isOptimal}
            title="Weighted-average modified duration of the optimal portfolio"
          />
          <Metric
            label="CVaR (95%)"
            value={liveCvar !== null ? `${liveCvar.toFixed(2)}%` : `${kpis.cvar_pct.toFixed(2)}%`}
            change={-(liveCvar ?? kpis.cvar_pct)}
            live={isOptimal}
            sublabel="≈ 200 bps shock"
            title="Market-value drop at 200 bps parallel rate shock (duration × 2%). Analytical approximation."
          />
          <Metric
            label="Capital Eff."
            value={liveCapEff !== null ? liveCapEff.toFixed(3) : kpis.sharpe.toFixed(2)}
            change={(liveCapEff ?? kpis.sharpe) - 1}
            live={isOptimal}
            sublabel="NII / req. capital"
            title="Statutory NII ÷ required regulatory capital. >1 means the portfolio earns more than its regulatory burden."
          />
          <Metric
            label="Avg Spread"
            value={kpis.spread_bps.toFixed(1)} unit="bps"
            neutral live={isOptimal}
            title="Weighted-average OAS spread of the selected bonds"
          />
          <Metric
            label="# Bonds"
            value={kpis.n_bonds.toString()}
            neutral live={isOptimal}
            title="Number of bonds with allocation > $1 in the optimal portfolio"
          />
          <Metric
            label="RBC C1 Usage"
            value={`${(kpis.rbc_c1_usage * 100).toFixed(1)}%`}
            neutral live={isOptimal}
            title="C1 capital charge as % of portfolio: Σ(theta_i × h_i) / H"
          />
        </div>

      </div>

      {/* ── Evolution modal ───────────────────────────────────────────────── */}
      {expandedKPI && modalCfg[expandedKPI] && (
        <EvolutionModal
          title={`${expandedKPI} — Evolution`}
          data={history}
          dataKey={modalCfg[expandedKPI].dataKey}
          formatter={modalCfg[expandedKPI].formatter}
          annotation={modalCfg[expandedKPI].annotation}
          onClose={() => setExpandedKPI(null)}
        />
      )}
    </div>
  )
}
