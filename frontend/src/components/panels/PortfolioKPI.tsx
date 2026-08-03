import { useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type { OptimizerResult, PortfolioKPIs, HistoryEntry, FabnMarketPoint } from '../../types'
import FabnMarketChart, { findPointForDate } from './FabnMarketChart'

interface Props {
  date:              string
  optimizerResult?:  OptimizerResult | null
  optimizerLoading?: boolean
  history?:          HistoryEntry[]
  appliedTxnCost?:   number
  fabnMarketHistory?: FabnMarketPoint[]
  gammaW?:           number
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
    neutral ? 'text-text-secondary' : change !== undefined
      ? change >= 0 ? 'text-emerald-400' : 'text-red-400'
      : 'text-text-secondary'
  )

  return (
    <div
      onClick={onClick}
      title={title}
      className={`bg-surface-2/60 rounded-2xl p-4 border transition-colors
        ${onClick ? 'cursor-pointer hover:border-amber-500/40' : 'hover:border-border-strong'}
        ${expanded ? 'border-amber-500/40' : 'border-border/50'}`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-text-muted text-xs uppercase tracking-wider">{label}</p>
        <div className="flex items-center gap-1.5">
          {live && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 opacity-70" title="Live from optimizer" />}
          {onClick && (
            <span className={`text-text-muted text-xs transition-transform ${expanded ? 'rotate-180' : ''}`}>▾</span>
          )}
        </div>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-xl font-mono font-semibold ${textColor}`}>{value}</span>
        {unit && <span className="text-text-muted text-xs">{unit}</span>}
      </div>
      {sublabel && <p className="text-text-muted text-[10px] mt-0.5">{sublabel}</p>}
      {change !== undefined && !valueColor && (
        <p className={`text-xs mt-1 ${change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          {change >= 0 ? '▲' : '▼'} {Math.abs(change).toFixed(2)}%
        </p>
      )}
    </div>
  )
}

function SectionLabel({ children }: { children: string }) {
  return <p className="text-text-muted text-xs uppercase tracking-wider pt-1">{children}</p>
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
        className="bg-surface-1 border border-border rounded-3xl p-6 w-[520px] shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-text-primary font-semibold text-sm">{title}</h3>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>
        {annotation && (
          <p className="text-text-muted text-xs mb-4">{annotation}</p>
        )}

        {data.length < 2 ? (
          <div className="h-40 flex items-center justify-center">
            <p className="text-text-muted text-sm">Visit more dates to see the evolution chart</p>
          </div>
        ) : (
          <div className="h-48 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              {(() => {
                const vals = data.map(d => d[dataKey] as number).filter(v => isFinite(v))
                const minV = Math.min(...vals)
                const maxV = Math.max(...vals)
                const range = maxV - minV
                const pad = range > 0 ? range * 0.25 : Math.abs(maxV) * 0.01
                const yMin = Math.max(0, minV - pad)
                const yMax = maxV + pad
                return (
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
                  domain={[yMin, yMax]}
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
                )
              })()}
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}

export default function PortfolioKPI({
  date, optimizerResult, optimizerLoading, history = [], appliedTxnCost = 0,
  fabnMarketHistory = [], gammaW = 0.15,
}: Props) {
  const isOptimal = optimizerResult?.status === 'optimal'
  const [expandedKPI, setExpandedKPI] = useState<string | null>(null)

  function toggleKPI(label: string) {
    setExpandedKPI(prev => prev === label ? null : label)
  }

  const kpis: PortfolioKPIs | null = isOptimal && optimizerResult
    ? {
        value:        500_000_000,
        total_return: (optimizerResult.nev / 500_000_000) * 100,
        yield_pct:    optimizerResult.yield_pct,
        duration:     optimizerResult.duration,
        n_bonds:      optimizerResult.n_bonds_selected,
        spread_bps:   optimizerResult.spread_bps,
        rbc_c1_usage: optimizerResult.rbc_c1_usage,
      }
    : null

  // Live replacements for stub fields
  const liveYtdReturn = isOptimal ? optimizerResult!.yield_pct * ytdFraction(date) : null
  const liveCvar      = isOptimal ? optimizerResult!.cvar_pct : null
  const liveCapEff    = isOptimal ? optimizerResult!.rbc_ratio : null

  const loading = optimizerLoading ?? false

  const badgeClass = isOptimal
    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
    : 'bg-surface-2 border-border text-text-muted'

  // capital_cost = gammaW * rbc_bar * RBC_val, so dividing by gammaW alone
  // yields the required capital reserve (rbc_bar * RBC_val) directly.
  const regulatoryCapital  = isOptimal && optimizerResult ? optimizerResult.capital_cost / gammaW : null
  const marketValue        = isOptimal && optimizerResult
    ? optimizerResult.allocations.reduce((s, a) => s + a.h_opt * a.mid_price / 100, 0)
    : null

  // ROE_NII / ROE_SAP — denominator = C1 usage × RBC_bar × Duration × FABN market value
  const roe = isOptimal && optimizerResult && marketValue !== null
    ? (() => {
        const denom = optimizerResult.rbc_c1_usage * optimizerResult.rbc_bar * optimizerResult.duration * marketValue
        return denom > 0
          ? { nii: optimizerResult.spread_income / denom, sap: optimizerResult.nev / denom }
          : null
      })()
    : null

  // Modal config derived from expandedKPI
  type ModalCfg = { dataKey: keyof HistoryEntry; formatter: (v: number) => string; annotation?: string }
  const modalCfg: Record<string, ModalCfg> = {
    'Portfolio Value': {
      dataKey:   'market_value',
      formatter: (v: number) => {
        if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`
        if (v >= 1_000_000)     return `$${(v / 1_000_000).toFixed(1)}M`
        if (v >= 1_000)         return `$${(v / 1_000).toFixed(1)}k`
        return `$${v.toLocaleString()}`
      },
      annotation: 'Total portfolio market value = Σ(face × mid price / 100) across visited dates',
    },
  }

  return (
    <div className="bg-surface-1 rounded-2xl border border-border p-5 flex flex-col h-full">
      {/* Panel header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div>
          <h2 className="text-text-primary font-semibold text-sm tracking-wide">Portfolio KPI</h2>
          <p className="text-text-muted text-xs mt-0.5">
            FABN Spread Portfolio{isOptimal ? ` · ${date}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {loading && <span className="text-amber-400 text-xs animate-pulse">Optimizing…</span>}
          <span className={`px-2 py-1 border text-xs rounded-full ${badgeClass}`}>
            {isOptimal ? '● Optimizer' : loading ? '○ Loading…' : '○ No data'}
          </span>
        </div>
      </div>

      {/* Everything scrollable together */}
      <div className="flex-1 overflow-y-auto min-h-0 space-y-3">

        {/* ── 1. FABN vs Market — the client spread story ────────────────── */}
        <SectionLabel>FABN vs Market</SectionLabel>
        {(() => {
          const creditingRateBps = (optimizerResult ? optimizerResult.r_FABN : 0.03205) * 10_000
          const current = findPointForDate(fabnMarketHistory, date)
          return (
            <>
              <FabnMarketChart
                data={fabnMarketHistory}
                creditingRate={creditingRateBps}
                selectedDate={date}
              />
              {current && (
                <div className="grid grid-cols-3 gap-3">
                  <Metric
                    label="FABN Crediting Rate"
                    value={`${creditingRateBps.toFixed(0)} bps`}
                    neutral
                    title="Fixed rate paid to FABN holders (funding agreement crediting rate)"
                  />
                  <Metric
                    label="FABN YTM"
                    value={`${(current.fabn_ytm * 100).toFixed(0)} bps`}
                    neutral live
                    sublabel={current.date}
                    title="FABN yield to maturity from Bloomberg market data, as of the selected date"
                  />
                  <Metric
                    label="Spread to Treasury"
                    value={`${current.spread_bps.toFixed(0)} bps`}
                    valueColor="text-brand-highlight"
                    live
                    sublabel={current.date}
                    title="FABN YTM minus benchmark Treasury YTM — the client's spread pickup vs risk-free, as of the selected date"
                  />
                </div>
              )}
            </>
          )
        })()}
        <div className="border-t border-border" />

        {/* ── 2. Return on Equity — the LP/investor view ──────────────────── */}
        <SectionLabel>Return on Equity — LP View</SectionLabel>
        {isOptimal && optimizerResult && roe && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="ROE (NII)"
                value={`${(roe.nii * 100).toFixed(1)}%`}
                valueColor="text-brand"
                live
                sublabel="NII / (C1 × RegFactor × Dur × Balance)"
                title="ROE_NII = Statutory NII ÷ (C1 usage × RBC_bar × Duration × FABN market value)"
              />
              <Metric
                label="ROE (SAP)"
                value={`${(roe.sap * 100).toFixed(1)}%`}
                valueColor="text-brand-highlight"
                live
                sublabel="SAP Obj / (C1 × RegFactor × Dur × Balance)"
                title="ROE_SAP = SAP Objective ÷ (C1 usage × RBC_bar × Duration × FABN market value)"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Metric
                label="Statutory NII"
                value={`$${(optimizerResult.spread_income / 1e6).toFixed(2)}M`}
                valueColor="text-brand"
                live
                title="Annual net interest income = Σ(book_yield_i − r_FABN) × h_i"
              />
              <Metric
                label="SAP Objective"
                value={`$${(optimizerResult.nev / 1e6).toFixed(2)}M`}
                valueColor="text-brand-highlight"
                live
                title="Maximised quantity: NII − capital_cost − turnover − liquidity_penalty + savings"
              />
              <Metric
                label="C1 (RBC Usage)"
                value={`${(optimizerResult.rbc_c1_usage * 100).toFixed(2)}%`}
                neutral live
                title="C1 capital charge as % of portfolio: Σ(theta_i × h_i) / H"
              />
              <Metric
                label="Avg Spread"
                value={optimizerResult.spread_bps.toFixed(1)} unit="bps"
                neutral live
                title="Weighted-average OAS spread of the selected bonds"
              />
              <Metric
                label="Regulatory Capital"
                value={`$${regulatoryCapital !== null ? (regulatoryCapital / 1e6).toFixed(1) : '—'}M`}
                valueColor="text-text-secondary"
                sublabel="required reserve"
                title={`Required capital = capital_cost ÷ γ (${gammaW}) = RBC_bar (${optimizerResult.rbc_bar}) × Σ(theta_i × h_i)`}
              />
              <Metric
                label="Reg Factor"
                value={optimizerResult.rbc_bar.toFixed(1)} unit="×"
                neutral
                title="RBC solvency multiplier (minimum required-capital ratio)"
              />
            </div>
            <div className="border-t border-border" />
          </>
        )}

        {/* ── 3. Portfolio Metrics — the issuer/portfolio view ─────────────── */}
        <SectionLabel>Portfolio Metrics</SectionLabel>
        <div className="grid grid-cols-2 gap-3">
          <Metric
            label="Portfolio Value"
            value={marketValue !== null ? formatValue(marketValue) : kpis !== null ? formatValue(kpis.value) : '—'}
            neutral
            live={isOptimal}
            onClick={() => toggleKPI('Portfolio Value')}
            expanded={expandedKPI === 'Portfolio Value'}
            sublabel={marketValue !== null ? `par $500M · mkt ${((marketValue / 500_000_000) * 100).toFixed(2)}¢` : undefined}
            title="Market value = Σ(face allocation × mid price / 100). Click to see evolution over visited dates."
          />
          <Metric
            label="Net SAP Rate"
            value={kpis !== null ? `${kpis.total_return >= 0 ? '+' : ''}${kpis.total_return.toFixed(2)}%` : '—'}
            change={kpis?.total_return}
            live={isOptimal}
            title="SAP objective ÷ $500M — net statutory income rate on invested capital"
          />
          <Metric
            label="YTD Return"
            value={liveYtdReturn !== null ? `+${liveYtdReturn.toFixed(2)}%` : '—'}
            change={liveYtdReturn ?? undefined}
            live={isOptimal}
            sublabel={liveYtdReturn !== null ? `${(ytdFraction(date) * 365).toFixed(0)} days elapsed` : undefined}
            title="Accrued statutory book yield YTD = book yield × days since Jan 1"
          />
          <Metric
            label="Portfolio Yield"
            value={kpis !== null ? kpis.yield_pct.toFixed(2) : '—'} unit="%"
            neutral live={isOptimal}
            title="Weighted-average book yield (coupon + amortization/accretion)"
          />
          <Metric
            label="Duration"
            value={kpis !== null ? kpis.duration.toFixed(2) : '—'} unit="yrs"
            neutral live={isOptimal}
            title="Weighted-average modified duration of the optimal portfolio"
          />
          <Metric
            label="CVaR (95%)"
            value={liveCvar != null ? `${liveCvar.toFixed(2)}%` : '—'}
            change={liveCvar != null ? -liveCvar : undefined}
            live={isOptimal && liveCvar != null}
            valueColor={isOptimal && optimizerResult?.cvar_degraded ? 'text-amber-500' : undefined}
            sublabel={
              isOptimal && optimizerResult
                ? liveCvar != null
                  ? `${optimizerResult.cvar_n_obs} days${optimizerResult.cvar_degraded ? ' · low sample' : ''}`
                  : 'insufficient history'
                : loading ? 'optimizer running…' : 'optimizer not yet run'
            }
            title={
              isOptimal
                ? `Historical-simulation CVaR, scaled to a 1-quarter horizon: expected market-value loss in the worst 5% of daily FABN yield moves (${optimizerResult?.cvar_n_obs ?? 0} historical days), duration-mapped to this portfolio.${optimizerResult?.cvar_degraded ? ' Fewer than 60 observations available — treat as indicative only.' : ''}`
                : 'Run the optimizer to see the real historical-simulation CVaR.'
            }
          />
          <Metric
            label="Capital Eff."
            value={liveCapEff !== null ? liveCapEff.toFixed(3) : '—'}
            change={liveCapEff !== null ? liveCapEff - 1 : undefined}
            live={isOptimal}
            sublabel="NII / req. capital"
            title="Statutory NII ÷ required regulatory capital. >1 means the portfolio earns more than its regulatory burden."
          />
          <Metric
            label="Avg Spread"
            value={kpis !== null ? kpis.spread_bps.toFixed(1) : '—'} unit="bps"
            neutral live={isOptimal}
            title="Weighted-average OAS spread of the selected bonds"
          />
          <Metric
            label="# Bonds"
            value={kpis !== null ? kpis.n_bonds.toString() : '—'}
            neutral live={isOptimal}
            title="Number of bonds with allocation > $1 in the optimal portfolio"
          />
          <Metric
            label="RBC C1 Usage"
            value={kpis !== null ? `${(kpis.rbc_c1_usage * 100).toFixed(1)}%` : '—'}
            neutral live={isOptimal}
            title="C1 capital charge as % of portfolio: Σ(theta_i × h_i) / H"
          />
          {isOptimal && optimizerResult && (
            <Metric
              label="Trading Cost"
              value={appliedTxnCost > 0 ? `−${formatValue(appliedTxnCost)}` : '$0'}
              valueColor="text-red-400"
              sublabel={`optimizer suggests: −${formatValue(optimizerResult.txn_cost)}`}
              title="Cumulative bid-ask spread cost of trades you have actually applied this session."
            />
          )}
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
