import Modal from './Modal'
import type { OptimizerResult } from '../../types'

interface Props {
  onClose: () => void
  result:  OptimizerResult | null
  loading: boolean
}

function fmt$(n: number): string {
  const abs = Math.abs(n)
  const sign = n < 0 ? '−' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1_000)     return `${sign}$${(abs / 1e3).toFixed(0)}k`
  return `${sign}$${abs.toFixed(0)}`
}

function KpiCard({ label, value, valueColor, sublabel }: { label: string; value: string; valueColor?: string; sublabel?: string }) {
  return (
    <div className="bg-surface-2/60 rounded-2xl p-3.5 border border-border">
      <p className="text-text-muted text-xs mb-1.5">{label}</p>
      <p className={`font-mono font-semibold text-base ${valueColor ?? 'text-text-secondary'}`}>{value}</p>
      {sublabel && <p className="text-text-muted text-xs mt-0.5">{sublabel}</p>}
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-24 flex items-center justify-center text-text-muted text-sm border border-dashed border-border rounded-2xl">
      {label}
    </div>
  )
}

export default function DerivativeUsage({ onClose, result, loading }: Props) {
  const isOptimal = result?.status === 'optimal'
  const swaps = isOptimal ? (result?.swap_allocations ?? []) : []
  const hasSwaps = swaps.some(s => s.notional > 1_000)

  const totalNotional = isOptimal ? (result!.swap_notional_total) : 0
  const capNotional    = isOptimal ? (result!.swap_cap_notional) : 0
  const capUsagePct    = capNotional > 0 ? (totalNotional / capNotional) * 100 : 0
  const totalIncome    = swaps.reduce((s, a) => s + a.net_income, 0)
  const totalDurContrib = swaps.reduce((s, a) => s + a.dur_contrib, 0)

  // Hedge effectiveness: bond-only duration gap (the reported KPI elsewhere) vs the
  // combined bonds+swaps duration that actually satisfies the optimizer's LP constraint.
  const bondOnlyDuration  = isOptimal ? result!.duration : null
  const combinedDuration  = isOptimal ? result!.duration + totalDurContrib : null
  const durationTarget    = isOptimal ? result!.duration_target : null
  const bondOnlyGap       = isOptimal ? result!.duration_gap : null
  const combinedGap       = isOptimal && durationTarget !== null && combinedDuration !== null
    ? Math.abs(combinedDuration - durationTarget)
    : null

  return (
    <Modal title="Derivative Usage" subtitle="Interest-rate swap overlay used to hit the duration target" onClose={onClose}>
      <div className="space-y-5">

        <div className="p-4 bg-surface-2 rounded-2xl border border-border">
          <p className="text-text-muted text-sm leading-relaxed">
            The optimizer's only modeled derivative overlay is a book of <span className="text-text-secondary font-medium">1/2/3-year pay-fixed, at-the-money interest rate swaps</span>,
            jointly optimized with the bond portfolio inside the same SAP objective. Pay-fixed swaps subtract duration —
            they hedge the sale-price rate risk of the now-open, post-FABN-maturity bond universe rather than closing a
            duration gap, and at-the-money rates mean close to zero carry by design. <span className="text-text-secondary font-medium">Credit default swaps and Treasury futures are not
            currently modeled</span> (no cost, RBC, or cashflow data source exists for them yet) — they aren't shown here
            with placeholder numbers.
          </p>
        </div>

        {/* Live swap KPIs */}
        <div className="grid grid-cols-4 gap-3">
          {isOptimal && result ? (
            <>
              <KpiCard
                label="Total Swap Notional"
                value={fmt$(totalNotional)}
                valueColor="text-purple-400"
                sublabel={`${capUsagePct.toFixed(0)}% of $${(capNotional / 1e6).toFixed(0)}M cap`}
              />
              <KpiCard
                label="Net Swap Income"
                value={`${totalIncome >= 0 ? '+' : ''}${fmt$(totalIncome)}`}
                valueColor={totalIncome >= 0 ? 'text-emerald-400' : 'text-red-400'}
                sublabel="per year, fixed − floating"
              />
              <KpiCard
                label="Duration Contribution"
                value={`${totalDurContrib.toFixed(4)} yr`}
                valueColor="text-blue-400"
                sublabel={totalDurContrib < 0 ? 'subtracted from portfolio duration (pay-fixed)' : 'added to portfolio duration'}
              />
              <KpiCard
                label="Swap C3 Capital Cost"
                value={fmt$(result.swap_c3_capital_cost)}
                valueColor="text-amber-500"
                sublabel="λ_cap × μ_swap × notional"
              />
            </>
          ) : (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-surface-2/60 rounded-2xl p-3.5 border border-border animate-pulse">
                <div className="h-3 bg-surface-3 rounded-lg w-2/3 mb-2" />
                <div className="h-5 bg-surface-3 rounded-lg w-1/2" />
              </div>
            ))
          )}
        </div>

        {/* Swap notional cap utilization */}
        {isOptimal && result && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <h3 className="text-text-primary font-medium text-sm">Swap Notional Cap Utilization</h3>
              <span className="text-text-muted text-xs">v_max_frac × $500M budget</span>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <div className="flex-1 h-2.5 bg-surface-3 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, capUsagePct)}%`,
                    backgroundColor: capUsagePct >= 99.5 ? 'var(--brand-highlight)' : 'var(--brand-accent)',
                    opacity: 0.75,
                  }}
                />
              </div>
              <span className="w-32 flex-shrink-0 text-right font-mono text-text-muted">
                {fmt$(totalNotional)} / {fmt$(capNotional)}
              </span>
            </div>
            {capUsagePct >= 99.5 && (
              <p className="text-brand-highlight text-xs mt-1.5">
                ⚡ At cap — the optimizer would use more swap notional if the constraint allowed it.
              </p>
            )}
          </div>
        )}

        {/* Per-tenor allocation table */}
        <div>
          <h3 className="text-text-primary font-medium text-sm mb-3">Swap Overlay by Tenor</h3>
          {!isOptimal ? (
            <EmptyState label={loading ? 'Running optimizer…' : 'Run optimizer to see swap overlay'} />
          ) : !hasSwaps ? (
            <EmptyState label="No swap overlay active — optimizer chose 0 notional for all tenors" />
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface-2 border-b border-border">
                    {['Tenor', 'Notional', 'Fixed Rate', 'Float Rate', 'Net Income ($/yr)', 'Dur. Contrib. (yr)'].map(h => (
                      <th key={h} className="px-4 py-2.5 text-left text-text-muted font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {swaps.map((s, i) => (
                    <tr key={i} className={`border-b border-border last:border-0 hover:bg-surface-2/40 ${s.notional > 1_000 ? '' : 'opacity-40'}`}>
                      <td className="px-4 py-3 font-mono text-purple-400 font-semibold">{s.tenor_years.toFixed(0)}yr</td>
                      <td className="px-4 py-3 font-mono text-text-secondary">{fmt$(s.notional)}</td>
                      <td className="px-4 py-3 font-mono text-text-secondary">{(s.fixed_rate * 100).toFixed(2)}%</td>
                      <td className="px-4 py-3 font-mono text-text-secondary">{(result!.r_float * 100).toFixed(2)}%</td>
                      <td className={`px-4 py-3 font-mono font-semibold ${s.net_income >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {s.net_income >= 0 ? '+' : ''}{fmt$(s.net_income)}
                      </td>
                      <td className="px-4 py-3 font-mono text-blue-400">{s.dur_contrib.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Hedge effectiveness */}
        <div>
          <h3 className="text-text-primary font-medium text-sm mb-1">Hedge Effectiveness</h3>
          <p className="text-text-muted text-xs mb-3">
            The duration band is currently relaxed to an inert 100yr tolerance — CVaR governs risk instead — so these
            figures are informational, not pass/fail against a hard bound. The "Duration Gap" KPI shown in Risk only
            reflects the bond book; this compares both bond-only and combined (bonds + swaps) duration against the
            liability target.
          </p>
          {!isOptimal ? (
            <EmptyState label={loading ? 'Running optimizer…' : 'Run optimizer to see hedge effectiveness'} />
          ) : (
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3.5 rounded-2xl border bg-surface-2/60 border-border">
                <p className="text-text-muted mb-1">Bond-Only Duration Gap</p>
                <p className="font-mono font-bold text-base text-text-secondary">
                  {bondOnlyDuration?.toFixed(3)} yr <span className="text-text-muted font-normal">vs target {durationTarget?.toFixed(3)}</span>
                </p>
                <p className="text-text-muted mt-0.5">gap {bondOnlyGap?.toFixed(3)} yr · informational</p>
              </div>
              <div className="p-3.5 rounded-2xl border bg-surface-2/60 border-border">
                <p className="text-text-muted mb-1">Combined (Bonds + Swaps)</p>
                <p className="font-mono font-bold text-base text-text-secondary">
                  {combinedDuration?.toFixed(3)} yr <span className="text-text-muted font-normal">vs target {durationTarget?.toFixed(3)}</span>
                </p>
                <p className="text-text-muted mt-0.5">gap {combinedGap?.toFixed(3)} yr · informational</p>
              </div>
            </div>
          )}
          {isOptimal && totalDurContrib < -1e-6 && (
            <p className="text-blue-400 text-xs mt-2">
              The pay-fixed overlay is subtracting {Math.abs(totalDurContrib).toFixed(4)} yr of duration — hedging the
              open bond universe's sale-price rate risk rather than closing a duration gap.
            </p>
          )}
        </div>

        {/* Not modeled */}
        <div>
          <h3 className="text-text-primary font-medium text-sm mb-3">Not Modeled</h3>
          <div className="grid grid-cols-2 gap-3">
            {['Credit Default Swaps (CDS)', 'Treasury Futures'].map(label => (
              <div key={label} className="p-3.5 rounded-2xl border border-border border-dashed bg-surface-2/30">
                <p className="text-text-muted text-xs font-medium mb-1">{label}</p>
                <p className="text-text-muted text-xs">No cost, RBC, or cashflow model exists in the optimizer yet.</p>
              </div>
            ))}
          </div>
        </div>

      </div>
    </Modal>
  )
}
