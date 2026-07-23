import {
  ComposedChart, Bar, Area, ReferenceLine, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import Modal from './Modal'
import type { ConstraintResult, OptimizerResult } from '../../types'

interface Props {
  onClose: () => void
  result:  OptimizerResult | null
  loading: boolean
}

const SECTOR_WARN_PCT = 25  // informational concentration threshold, not an optimizer constraint

function fmtConstraintValue(c: ConstraintResult): string {
  switch (c.label) {
    case 'Budget':
      return `$${(c.value / 1e6).toFixed(1)}M`
    case 'Solvency (RBC)':
      return `${c.value.toFixed(3)}x`
    default:
      if (c.label.startsWith('CVaR')) return `$${(c.value / 1e6).toFixed(2)}M`
      if (c.label.startsWith('Duration Gap')) return `${c.value.toFixed(3)} yrs`
      return String(c.value)
  }
}

function fmtConstraintBound(c: ConstraintResult): string {
  if (c.bound === null) return 'informational'
  switch (c.label) {
    case 'Budget':
      return `= $${(c.bound / 1e6).toFixed(0)}M`
    case 'Solvency (RBC)':
      return `≥ ${c.bound.toFixed(1)}x`
    default:
      if (c.label.startsWith('CVaR')) return `≤ $${(c.bound / 1e6).toFixed(2)}M`
      return String(c.bound)
  }
}

function ConstraintCard({ c }: { c: ConstraintResult }) {
  return (
    <div className={`p-4 rounded-2xl border ${c.pass
      ? 'bg-emerald-500/5 border-emerald-500/20'
      : 'bg-red-500/5 border-red-500/20'}`}>
      <div className="flex items-center justify-between mb-1">
        <p className="text-text-muted text-xs">{c.label}</p>
        <span className={`text-xs font-bold ${c.pass ? 'text-emerald-400' : 'text-red-400'}`}>
          {c.pass ? '✓' : '✗'}
        </span>
      </div>
      <p className={`font-mono font-semibold text-lg ${c.pass ? 'text-emerald-400' : 'text-red-400'}`}>
        {fmtConstraintValue(c)}
      </p>
      <p className={`text-xs mt-0.5 ${c.pass ? 'text-emerald-500/70' : 'text-red-500/70'}`}>
        {c.pass ? 'PASS' : 'FAIL'} · bound {fmtConstraintBound(c)}
      </p>
    </div>
  )
}

function CvarCard({ result }: { result: OptimizerResult }) {
  const { cvar_pct, cvar_var_pct, cvar_n_obs, cvar_degraded } = result
  const ok = cvar_pct == null || !cvar_degraded
  return (
    <div
      className={`p-4 rounded-2xl border ${ok ? 'bg-surface-2/60 border-border' : 'bg-amber-500/5 border-amber-500/20'}`}
      title="Historical-simulation CVaR: expected quarterly loss in the worst 5% of daily FABN yield moves, duration-mapped to this portfolio."
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-text-muted text-xs">CVaR (95%, quarterly)</p>
        <span className={`text-xs ${ok ? 'text-text-muted' : 'text-amber-400'}`}>{ok ? '○' : '⚠'}</span>
      </div>
      <p className="font-mono font-semibold text-lg text-text-secondary">
        {cvar_pct != null ? `${cvar_pct.toFixed(2)}%` : '—'}
      </p>
      <p className="text-xs mt-0.5 text-text-muted">
        {cvar_pct != null
          ? `VaR ${cvar_var_pct?.toFixed(2)}% · ${cvar_n_obs} days${cvar_degraded ? ' · low sample' : ''}`
          : 'insufficient history'}
      </p>
    </div>
  )
}

function SectorCard({ result }: { result: OptimizerResult }) {
  const { top_sector, top_weight_pct } = result.sector_concentration
  const warn = top_weight_pct > SECTOR_WARN_PCT
  return (
    <div
      className={`p-4 rounded-2xl border ${warn ? 'bg-amber-500/5 border-amber-500/20' : 'bg-surface-2/60 border-border'}`}
      title={`Largest single-sector weight in the optimized portfolio. Informational — not an enforced optimizer constraint (warn threshold ${SECTOR_WARN_PCT}%).`}
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-text-muted text-xs">Sector Cap (max)</p>
        <span className={`text-xs ${warn ? 'text-amber-400' : 'text-text-muted'}`}>{warn ? '⚠' : '○'}</span>
      </div>
      <p className="font-mono font-semibold text-lg text-text-secondary">{top_weight_pct.toFixed(1)}%</p>
      <p className="text-xs mt-0.5 text-text-muted">
        {top_sector || '—'} · informational, warn &gt; {SECTOR_WARN_PCT}%
      </p>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="p-4 rounded-2xl border bg-surface-2/60 border-border animate-pulse">
      <div className="h-3 bg-surface-3 rounded-lg w-2/3 mb-2" />
      <div className="h-6 bg-surface-3 rounded-lg w-1/2 mb-1" />
      <div className="h-2 bg-surface-3 rounded-lg w-3/4" />
    </div>
  )
}

function HistogramTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="glass border border-border rounded-2xl p-2.5 text-xs shadow-xl">
      <p className="text-text-primary font-mono">{p.bin_mid_pct >= 0 ? '+' : ''}{p.bin_mid_pct.toFixed(2)}%</p>
      <p className="text-text-muted">{p.count} historical {p.count === 1 ? 'day' : 'days'}</p>
    </div>
  )
}

function CvarHistogram({ result }: { result: OptimizerResult }) {
  const { cvar_histogram, cvar_pct, cvar_var_pct, cvar_degraded } = result
  if (!cvar_histogram || cvar_histogram.length === 0) {
    return (
      <div className="h-48 bg-surface-2 rounded-2xl border border-border border-dashed flex items-center justify-center">
        <p className="text-text-muted text-sm">Insufficient history to build a return distribution yet</p>
      </div>
    )
  }
  return (
    <div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={cvar_histogram} margin={{ top: 34, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="bin_mid_pct"
              type="number"
              domain={['dataMin', 'dataMax']}
              tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
              width={28}
              allowDecimals={false}
            />
            <Tooltip content={<HistogramTooltip />} cursor={{ fill: 'var(--surface-3)' }} />
            {cvar_var_pct != null && (
              <ReferenceLine
                x={-cvar_var_pct}
                stroke="var(--text-secondary)"
                strokeDasharray="4 3"
                label={{ value: `VaR ${cvar_var_pct.toFixed(1)}%`, fill: 'var(--text-secondary)', fontSize: 9, position: 'top', offset: 4 }}
              />
            )}
            {cvar_pct != null && (
              <ReferenceLine
                x={-cvar_pct}
                stroke="var(--brand-highlight)"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{ value: `CVaR ${cvar_pct.toFixed(1)}%`, fill: 'var(--brand-highlight)', fontSize: 9, position: 'top', offset: 18 }}
              />
            )}
            <Bar dataKey="count" radius={[3, 3, 0, 0]} barSize={16} isAnimationActive={false}>
              {cvar_histogram.map((b, i) => (
                <Cell key={i} fill={b.bin_mid_pct < 0 ? 'var(--brand-highlight)' : 'var(--brand-accent)'} fillOpacity={0.55} />
              ))}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-text-muted text-xs mt-2 text-center">
        Simulated quarterly return distribution from {result.cvar_n_obs} historical daily FABN yield moves, duration-mapped to this portfolio
        {cvar_degraded ? ' — sample is small, treat as indicative only' : ''}.
      </p>
    </div>
  )
}

function VolTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass border border-border rounded-2xl p-2.5 text-xs shadow-xl">
      <p className="text-text-muted mb-1">{label}</p>
      <p className="text-text-primary font-mono">{payload[0].value.toFixed(1)} bps</p>
    </div>
  )
}

function VolatilitySignalChart({ result }: { result: OptimizerResult }) {
  const { series, median_vol_bps, threshold_vol_bps, percentile, degraded } = result.trading_signal
  if (!series || series.length === 0) {
    return (
      <div className="h-40 bg-surface-2 rounded-2xl border border-border border-dashed flex items-center justify-center">
        <p className="text-text-muted text-sm">Insufficient history to compute rolling volatility yet</p>
      </div>
    )
  }
  return (
    <div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={series} margin={{ top: 18, right: 8, bottom: 0, left: 0 }}>
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
              width={32}
            />
            <Tooltip content={<VolTooltip />} />
            {median_vol_bps != null && (
              <ReferenceLine
                y={median_vol_bps}
                stroke="var(--text-secondary)"
                strokeDasharray="3 3"
                label={{ value: `median ${median_vol_bps.toFixed(0)}`, fill: 'var(--text-secondary)', fontSize: 9, position: 'insideBottomRight' }}
              />
            )}
            {threshold_vol_bps != null && (
              <ReferenceLine
                y={threshold_vol_bps}
                stroke="var(--brand-highlight)"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{ value: `p${percentile.toFixed(0)} = ${threshold_vol_bps.toFixed(0)} — worth-trading threshold`, fill: 'var(--brand-highlight)', fontSize: 9, position: 'top' }}
              />
            )}
            <Area
              type="monotone"
              dataKey="vol_21_bps"
              stroke="var(--brand-accent)"
              strokeWidth={1.75}
              fill="var(--brand-accent)"
              fillOpacity={0.12}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-text-muted text-xs mt-2 text-center">
        21-day rolling volatility of the cross-sectional median book yield vs. its own trailing-year
        distribution — fires when σ_t exceeds the {percentile.toFixed(0)}th percentile of that
        distribution, the Size-of-Prize volatility-threshold trigger (informational only — doesn't
        gate the optimizer){degraded ? '. Sample is small, treat as indicative only' : ''}.
      </p>
    </div>
  )
}

function TradingSignalBanner({ result }: { result: OptimizerResult }) {
  const { current_vol_bps, threshold_vol_bps, ratio_to_median, worth_trading, degraded } = result.trading_signal
  if (current_vol_bps == null || worth_trading == null) {
    return (
      <div className="p-3.5 rounded-2xl border bg-surface-2/60 border-border text-xs text-text-muted">
        Insufficient history to compute a trading signal yet.
      </div>
    )
  }
  return (
    <div className={`p-3.5 rounded-2xl border flex items-center gap-3 text-xs ${
      worth_trading
        ? 'bg-brand-highlight/5 border-brand-highlight/25'
        : 'bg-surface-2/60 border-border'
    }`}>
      <span className={`text-base ${worth_trading ? 'text-brand-highlight' : 'text-text-muted'}`}>
        {worth_trading ? '⚡' : '○'}
      </span>
      <div className="flex-1">
        <p className={`font-semibold ${worth_trading ? 'text-brand-highlight' : 'text-text-secondary'}`}>
          {worth_trading ? 'High volatility — worth trading' : 'Normal volatility — carry favors holding static'}
        </p>
        <p className="text-text-muted mt-0.5">
          21d yield vol {current_vol_bps.toFixed(1)} bps vs {threshold_vol_bps?.toFixed(1)} bps threshold
          ({ratio_to_median?.toFixed(2)}× median){degraded ? ' · low sample' : ''}
        </p>
      </div>
    </div>
  )
}

export default function Risk({ onClose, result, loading }: Props) {
  const isOptimal = result?.status === 'optimal'
  const constraints: ConstraintResult[] = isOptimal ? (result?.constraints ?? []) : []

  return (
    <Modal title="Risk" subtitle="CVaR, RBC constraints, and concentration limits" onClose={onClose}>
      <div className="space-y-5">

        {/* Optimizer constraint status */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-text-primary font-medium text-sm">Constraint Status</h3>
            {isOptimal && (
              <span className="text-emerald-400 text-xs px-2 py-0.5 bg-emerald-500/10 rounded-full border border-emerald-500/20">
                ● Live from optimizer
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {isOptimal && constraints.length > 0
              ? constraints.map((c, i) => <ConstraintCard key={i} c={c} />)
              : Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
            }
            {isOptimal && result
              ? <>
                  <CvarCard result={result} />
                  <SectorCard result={result} />
                </>
              : Array.from({ length: 2 }).map((_, i) => <SkeletonCard key={`extra-${i}`} />)
            }
          </div>
        </div>

        {/* RBC breakdown */}
        {isOptimal && result && (
          <div>
            <h3 className="text-text-primary font-medium text-sm mb-3">RBC Capital Breakdown</h3>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="bg-surface-2/40 rounded-2xl p-3 border border-border">
                <p className="text-text-muted mb-1">RBC Ratio</p>
                <p className="text-emerald-400 font-mono font-bold text-base">{result.rbc_ratio.toFixed(2)}x</p>
                <p className="text-text-muted mt-0.5">min 1.5x</p>
              </div>
              <div className="bg-surface-2/40 rounded-2xl p-3 border border-border">
                <p className="text-text-muted mb-1">C-1 Capital</p>
                <p className="text-amber-400 font-mono font-bold text-base">${(result.c1_cost / 1e6).toFixed(2)}M</p>
                <p className="text-text-muted mt-0.5">{(result.rbc_c1_usage * 100).toFixed(1)}% of budget</p>
              </div>
              <div className="bg-surface-2/40 rounded-2xl p-3 border border-border">
                <p className="text-text-muted mb-1">Duration Gap</p>
                <p className="text-blue-400 font-mono font-bold text-base">{result.duration_gap.toFixed(3)} yr</p>
                <p className="text-text-muted mt-0.5">ε_D tolerance</p>
              </div>
            </div>
          </div>
        )}

        {/* Sector concentration breakdown */}
        {isOptimal && result && result.sector_concentration.breakdown.length > 0 && (
          <div>
            <h3 className="text-text-primary font-medium text-sm mb-3">Sector Concentration</h3>
            <div className="space-y-1.5">
              {result.sector_concentration.breakdown.map(s => (
                <div key={s.sector} className="flex items-center gap-3 text-xs">
                  <span className="w-36 flex-shrink-0 text-text-secondary truncate">{s.sector}</span>
                  <div className="flex-1 h-2 bg-surface-3 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(100, s.weight_pct)}%`,
                        backgroundColor: s.weight_pct > SECTOR_WARN_PCT ? 'var(--brand-highlight)' : 'var(--brand-accent)',
                        opacity: 0.7,
                      }}
                    />
                  </div>
                  <span className="w-12 flex-shrink-0 text-right font-mono text-text-muted">{s.weight_pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* CVaR distribution */}
        <div>
          <h3 className="text-text-primary font-medium text-sm mb-3">Return Distribution &amp; CVaR Boundary</h3>
          {isOptimal && result
            ? <CvarHistogram result={result} />
            : <div className="h-48 bg-surface-2 rounded-2xl border border-border border-dashed flex items-center justify-center">
                <p className="text-text-muted text-sm">{loading ? 'Running optimizer…' : 'Run the optimizer to see the return distribution'}</p>
              </div>
          }
        </div>

        {/* Volatility-triggered trading signal (Size-of-Prize methodology) */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-text-primary font-medium text-sm">Volatility &amp; Trading Signal</h3>
            <span className="text-text-muted text-xs">
              σ_t vs p{result?.trading_signal.percentile.toFixed(0) ?? '75'} of trailing distribution
            </span>
          </div>
          {isOptimal && result ? (
            <div className="space-y-3">
              <TradingSignalBanner result={result} />
              <VolatilitySignalChart result={result} />
            </div>
          ) : (
            <div className="h-40 bg-surface-2 rounded-2xl border border-border border-dashed flex items-center justify-center">
              <p className="text-text-muted text-sm">{loading ? 'Running optimizer…' : 'Run the optimizer to see the trading signal'}</p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
