import { useMemo, useState } from 'react'
import {
  ComposedChart, BarChart, Bar, Line, Area, Cell,
  ScatterChart, Scatter,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Legend,
} from 'recharts'
import type { OptimizerResult, HistoryEntry, AppliedTrade } from '../../types'
import Modal from './Modal'

interface Props {
  onClose:       () => void
  result:        OptimizerResult | null
  history:       HistoryEntry[]
  appliedTrades: AppliedTrade[]
}

function fmt$(n: number): string {
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

function fmtDual(n: number): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-20 bg-surface-2/40 rounded-2xl border border-border border-dashed flex items-center justify-center">
      <p className="text-text-muted text-sm">{label}</p>
    </div>
  )
}

// ── LP helpers ────────────────────────────────────────────────────────────────

function ratingBucket(rating: string): string {
  const r = (rating ?? '').toUpperCase()
  if (r.startsWith('AAA') || r.startsWith('AA')) return '#3b82f6'
  if (r.startsWith('A') && !r.startsWith('AA')) return '#10b981'
  if (r.startsWith('BBB') || r.startsWith('BAA')) return '#f59e0b'
  return '#ef4444'
}

const LP_BUCKET_LABELS: [string, string][] = [
  ['#3b82f6', 'AAA/AA'],
  ['#10b981', 'A'],
  ['#f59e0b', 'BBB'],
  ['#ef4444', 'BB / below'],
]

function LPScatterTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null
  const d = payload[0].payload
  return (
    <div className="bg-surface-1 border border-border rounded-2xl p-3 text-xs shadow-xl">
      <p className="text-amber-400 font-mono font-semibold mb-1">{d.cusip}</p>
      <p className="text-text-muted">Rating: <span className="text-text-primary">{d.rating}</span></p>
      <p className="text-text-muted">Z-Spread: <span className="text-blue-400 font-mono">{(d.x as number).toFixed(1)} bps</span></p>
      <p className="text-text-muted">Duration: <span className="text-text-primary font-mono">{(d.duration as number).toFixed(2)} yr</span></p>
      <p className="text-text-muted">Shadow Price: <span className="text-emerald-400 font-mono">{(d.y as number).toFixed(4)} bps</span></p>
    </div>
  )
}

// ── Custom tooltip for the evolution chart ────────────────────────────────────
function EvolutionTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const opt   = payload.find((p: any) => p.dataKey === 'sap_opt')
  const stat  = payload.find((p: any) => p.dataKey === 'sap_static')
  const alpha = payload.find((p: any) => p.dataKey === 'alpha')
  return (
    <div className="bg-surface-1 border border-border rounded-2xl p-3 text-xs shadow-xl min-w-[180px]">
      <p className="text-text-muted font-medium mb-2">{label}</p>
      {opt   && <p className="text-amber-400 mb-0.5">Optimizer  <span className="font-mono float-right">{fmt$(opt.value)}</span></p>}
      {stat  && <p className="text-text-muted mb-0.5">Equal-wt   <span className="font-mono float-right">{fmt$(stat.value)}</span></p>}
      {alpha && <p className={`font-semibold ${alpha.value >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>Alpha <span className="font-mono float-right">{fmt$(alpha.value)}</span></p>}
    </div>
  )
}

// ── Custom tooltip for the cumulative SAP income chart ───────────────────────
function CumulativeTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const opt   = payload.find((p: any) => p.dataKey === 'cum_opt')
  const stat  = payload.find((p: any) => p.dataKey === 'cum_static')
  const alpha = payload.find((p: any) => p.dataKey === 'cum_alpha')
  return (
    <div className="bg-surface-1 border border-border rounded-2xl p-3 text-xs shadow-xl min-w-[210px]">
      <p className="text-text-muted font-medium mb-2">{label}</p>
      {opt  && <p className="text-amber-400 mb-0.5">Optimizer earned  <span className="font-mono float-right">{fmt$(opt.value)}</span></p>}
      {stat && <p className="text-text-muted mb-0.5">Equal-wt earned   <span className="font-mono float-right">{fmt$(stat.value)}</span></p>}
      {alpha && (
        <p className={`font-semibold ${alpha.value >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
          Cumulative alpha  <span className="font-mono float-right">{alpha.value >= 0 ? '+' : ''}{fmt$(alpha.value)}</span>
        </p>
      )}
    </div>
  )
}

const IMR_PAGE = 15

export default function StrategyTracking({ onClose, result, history, appliedTrades }: Props) {
  const isOptimal = result?.status === 'optimal'
  const sc        = isOptimal ? result!.static_comparison : null
  const [showAllIMR, setShowAllIMR] = useState(false)
  const [showAllLP,  setShowAllLP]  = useState(false)
  const [lpSortKey,  setLpSortKey]  = useState<'reduced_cost' | 'spread_bps' | 'duration'>('reduced_cost')
  const [lpSortDesc, setLpSortDesc] = useState(true)

  function toggleLpSort(key: 'reduced_cost' | 'spread_bps' | 'duration') {
    if (lpSortKey === key) setLpSortDesc(d => !d)
    else { setLpSortKey(key); setLpSortDesc(true) }
  }

  // Dates where at least one trade was applied (for reference lines on the chart)
  const appliedDates = [...new Set(appliedTrades.map(a => a.appliedAt))]

  // Cumulative SAP income: integrate SAP_rate × Δt over visited dates (Δt in years)
  // Each point represents total statutory income earned by each strategy since the first date.
  const cumulativeData = useMemo(() => {
    if (history.length < 2) return []
    let cumOpt = 0
    let cumStatic = 0
    return history.map((h, i) => {
      const dt = i === 0
        ? 0
        : (new Date(h.date).getTime() - new Date(history[i - 1].date).getTime()) / (365.25 * 24 * 3600 * 1000)
      cumOpt    += h.sap_opt    * dt
      cumStatic += h.sap_static * dt
      return { date: h.date, cum_opt: cumOpt, cum_static: cumStatic, cum_alpha: cumOpt - cumStatic }
    })
  }, [history])

  const cumulativeAlpha = cumulativeData.length ? cumulativeData[cumulativeData.length - 1].cum_alpha : 0

  const LP_PAGE = 15

  const lpAllocs = useMemo(() => {
    const allocs = result?.allocations ?? []
    return [...allocs].sort((a, b) => {
      const av = ((a as any)[lpSortKey] ?? 0) as number
      const bv = ((b as any)[lpSortKey] ?? 0) as number
      return lpSortDesc ? bv - av : av - bv
    })
  }, [result?.allocations, lpSortKey, lpSortDesc])

  const lpScatterGroups = useMemo(() => {
    const allocs = result?.allocations ?? []
    const groups: Record<string, { x: number; y: number; cusip: string; rating: string; duration: number }[]> =
      Object.fromEntries(LP_BUCKET_LABELS.map(([c]) => [c, []]))
    for (const a of allocs) {
      const color = ratingBucket(a.rating)
      groups[color]?.push({
        x:        a.spread_bps,
        y:        (a.reduced_cost ?? 0) * 1e4,
        cusip:    a.cusip,
        rating:   a.rating,
        duration: a.duration,
      })
    }
    return groups
  }, [result?.allocations])

  // Summary stats over the history
  const latestAlpha  = history.length ? history[history.length - 1].alpha : 0
  const bestAlpha    = history.length ? Math.max(...history.map(h => h.alpha)) : 0

  // ── SAP vs Static rows (current date) ─────────────────────────────────────
  type BenchRow = { label: string; optVal: number; stVal: number; higherIsBetter: boolean | null; isInt?: boolean }
  const benchRows: BenchRow[] = isOptimal && sc ? [
    { label: 'Statutory NII',      optVal: result!.spread_income,    stVal: sc.nii,          higherIsBetter: true  },
    { label: 'Capital Cost (RBC)', optVal: result!.capital_cost,     stVal: sc.capital_cost, higherIsBetter: false },
    { label: 'SAP Objective',      optVal: result!.nev,              stVal: sc.sap,          higherIsBetter: true  },
    { label: 'Duration (yr)',      optVal: result!.duration,         stVal: sc.duration,     higherIsBetter: null  },
    { label: '# Bonds',           optVal: result!.n_bonds_selected, stVal: sc.n_bonds,      higherIsBetter: null, isInt: true },
  ] : []

  // ── IMR ───────────────────────────────────────────────────────────────────
  const imrSchedule = result?.imr_schedule ?? []
  const imrContribs = result?.imr_contributions ?? []
  const imrTotal    = result?.imr_total_gain ?? 0
  const hasSells    = imrContribs.length > 0

  // ── Shadow prices ─────────────────────────────────────────────────────────
  const shadowPrices = result?.shadow_prices ?? []
  const budgetPi      = shadowPrices.find(r => r.label.startsWith('Budget'))?.dual ?? null
  const marginalUnconstrained = result?.marginal_dollar_unconstrained ?? null
  const piFacility    = result?.pi_facility ?? []
  const piIssuerBinding = result?.pi_issuer_binding ?? []

  // ── Reservation prices (per-bond shadow price, $ terms) ────────────────────
  const reservationPrices = result?.reservation_prices ?? []
  const [showAllRes, setShowAllRes] = useState(false)
  const RES_PAGE = 15

  // ── Swap overlay ──────────────────────────────────────────────────────────
  const swapAllocs      = result?.swap_allocations ?? []
  const totalSwapNotional = swapAllocs.reduce((s, a) => s + a.notional, 0)
  const totalSwapIncome   = swapAllocs.reduce((s, a) => s + a.net_income, 0)
  const totalSwapDur      = swapAllocs.reduce((s, a) => s + a.dur_contrib, 0)
  const hasSwaps          = totalSwapNotional > 1_000

  return (
    <Modal title="Strategy Tracking" subtitle="Performance evolution · SAP vs benchmark · IMR · constraint analysis · swap overlay" onClose={onClose}>
      <div className="space-y-8">

        {/* ── Section 0: Performance Evolution ──────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-text-primary font-medium text-sm">Performance Evolution</h3>
            <span className="text-text-muted text-xs">Session history · resets on portfolio reset</span>
          </div>

          {/* Summary KPI ribbon */}
          {history.length > 0 && (
            <div className="grid grid-cols-4 gap-2 mb-4">
              {[
                { label: 'Dates Tracked',   value: String(history.length),        color: 'text-text-secondary' },
                { label: 'Snapshot Alpha',  value: fmt$(latestAlpha),             color: latestAlpha >= 0 ? 'text-emerald-400' : 'text-red-400',
                  title: 'SAP rate advantage vs equal-weight at the latest visited date' },
                { label: 'Cumul. Alpha',    value: cumulativeAlpha !== 0 ? `${cumulativeAlpha >= 0 ? '+' : ''}${fmt$(cumulativeAlpha)}` : '—',
                  color: cumulativeAlpha >= 0 ? 'text-emerald-400' : 'text-red-400',
                  title: 'Total income advantage accumulated since the first visited date (optimizer vs equal-weight, time-weighted)' },
                { label: 'Trades Applied',  value: String(appliedTrades.length),  color: appliedTrades.length > 0 ? 'text-emerald-400' : 'text-text-muted' },
              ].map(({ label, value, color, title }) => (
                <div key={label} title={title} className="bg-surface-2/60 rounded-2xl p-3 border border-border/50 cursor-default">
                  <p className="text-text-muted text-xs mb-1">{label}</p>
                  <p className={`font-mono font-semibold text-sm ${color}`}>{value}</p>
                </div>
              ))}
            </div>
          )}

          {history.length < 2 ? (
            <EmptyState label={
              history.length === 0
                ? 'Navigate between dates to track SAP evolution over time'
                : 'Navigate to one more date to see the evolution chart'
            } />
          ) : (
            <>
              {/* ── Chart A: Snapshot SAP rate at each visited date ─────────── */}
              <p className="text-text-muted text-xs mb-2">
                <span className="text-text-muted font-medium">Snapshot SAP rate</span>
                {' '}— annualised SAP objective at each visited date ($/yr). Shows which strategy is currently better, but not how much has accumulated.
              </p>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={history} margin={{ top: 18, right: 24, bottom: 0, left: 20 }}>
                    <CartesianGrid stroke="#1f2937" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={d => d.slice(5)}
                    />
                    <YAxis
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={v => `$${(v / 1e6).toFixed(1)}M`}
                      width={54}
                    />
                    <Tooltip content={<EvolutionTooltip />} />

                    {appliedDates.map(d => (
                      <ReferenceLine
                        key={d}
                        x={d}
                        stroke="#10b981"
                        strokeDasharray="4 3"
                        strokeWidth={1.5}
                        label={{ value: '▲', fill: '#10b981', fontSize: 9, position: 'top' }}
                      />
                    ))}

                    <Area type="monotone" dataKey="sap_opt" stroke="none" fill="#f59e0b" fillOpacity={0.08} />
                    <Line type="monotone" dataKey="sap_static" stroke="#6b7280" strokeWidth={1.5} dot={false} strokeDasharray="5 3" />
                    <Line type="monotone" dataKey="sap_opt" stroke="#f59e0b" strokeWidth={2}
                      dot={{ r: 3, fill: '#f59e0b', strokeWidth: 0 }} activeDot={{ r: 5 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-5 mt-1.5 mb-6 text-xs text-text-muted justify-center">
                <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-amber-400" />SAP Optimizer</span>
                <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-border-strong border-dashed" />Equal-Weight</span>
                {appliedDates.length > 0 && (
                  <span className="flex items-center gap-1.5"><span className="inline-block w-px h-3 bg-emerald-400" />Trade applied</span>
                )}
              </div>

              {/* ── Chart B: Cumulative SAP income since first date ──────────── */}
              <p className="text-text-muted text-xs mb-2">
                <span className="text-text-muted font-medium">Cumulative SAP income</span>
                {' '}— total statutory income accumulated from the first visited date (SAP rate × time elapsed). Both strategies start at $0; the gap is cumulative alpha.
              </p>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={cumulativeData} margin={{ top: 18, right: 24, bottom: 0, left: 20 }}>
                    <CartesianGrid stroke="#1f2937" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={d => d.slice(5)}
                    />
                    <YAxis
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={v => `$${(v / 1e6).toFixed(2)}M`}
                      width={62}
                    />
                    <Tooltip content={<CumulativeTooltip />} />

                    {appliedDates.map(d => (
                      <ReferenceLine
                        key={d}
                        x={d}
                        stroke="#10b981"
                        strokeDasharray="4 3"
                        strokeWidth={1.5}
                        label={{ value: '▲', fill: '#10b981', fontSize: 9, position: 'top' }}
                      />
                    ))}

                    {/* Shade the alpha gap between the two curves */}
                    <Area type="monotone" dataKey="cum_opt" stroke="none" fill="#f59e0b" fillOpacity={0.10} />

                    <Line type="monotone" dataKey="cum_static" stroke="#6b7280" strokeWidth={1.5} dot={false} strokeDasharray="5 3" />
                    <Line type="monotone" dataKey="cum_opt" stroke="#f59e0b" strokeWidth={2}
                      dot={{ r: 3, fill: '#f59e0b', strokeWidth: 0 }} activeDot={{ r: 5 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-5 mt-1.5 text-xs text-text-muted justify-center">
                <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-amber-400" />Optimizer cumulative</span>
                <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-border-strong border-dashed" />Equal-weight cumulative</span>
                {appliedDates.length > 0 && (
                  <span className="flex items-center gap-1.5"><span className="inline-block w-px h-3 bg-emerald-400" />Trade applied</span>
                )}
              </div>
            </>
          )}
        </section>

        {/* ── Section 0b: Alpha & Metrics by Date ───────────────────────── */}
        {history.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-text-primary font-medium text-sm">Metrics by Date</h3>
              <span className="text-text-muted text-xs">All dates visited this session</span>
            </div>
            <div className="overflow-x-auto rounded-2xl border border-border max-h-52 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0">
                  <tr className="bg-surface-2/90 border-b border-border">
                    {['Date', 'SAP Opt', 'Equal-Wt', 'Alpha', 'Yield', 'Dur Gap', 'Spread', 'Bonds'].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-text-muted font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...history].reverse().map((h, i) => {
                    const isAppliedDate = appliedDates.includes(h.date)
                    return (
                      <tr
                        key={h.date}
                        className={`border-b border-border/60 hover:bg-surface-2/30
                          ${i === 0 ? 'bg-amber-500/5' : ''}
                          ${isAppliedDate ? 'border-l-2 border-l-emerald-500/40' : ''}`}
                      >
                        <td className="px-3 py-2 font-mono text-text-secondary whitespace-nowrap">
                          {h.date}
                          {isAppliedDate && <span className="ml-1.5 text-emerald-400 text-[9px]">▲ applied</span>}
                        </td>
                        <td className="px-3 py-2 font-mono text-amber-400">{fmt$(h.sap_opt)}</td>
                        <td className="px-3 py-2 font-mono text-text-muted">{fmt$(h.sap_static)}</td>
                        <td className={`px-3 py-2 font-mono font-semibold ${h.alpha >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {h.alpha >= 0 ? '+' : ''}{fmt$(h.alpha)}
                        </td>
                        <td className="px-3 py-2 font-mono text-text-secondary">{h.yield_pct.toFixed(2)}%</td>
                        <td className={`px-3 py-2 font-mono ${h.duration_gap <= 0.3 ? 'text-emerald-400' : 'text-amber-400'}`}>
                          {h.duration_gap.toFixed(3)} yr
                        </td>
                        <td className="px-3 py-2 font-mono text-blue-400">{h.spread_bps.toFixed(0)} bps</td>
                        <td className="px-3 py-2 font-mono text-text-muted">{h.n_bonds_selected}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ── Section 1: SAP vs Static (current date snapshot) ──────────── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-text-primary font-medium text-sm">SAP Optimizer vs Equal-Weight Benchmark</h3>
            <span className="text-text-muted text-xs">Current date snapshot</span>
            {isOptimal && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Live
              </span>
            )}
          </div>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see benchmark comparison" />
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface-2/80 border-b border-border">
                    <th className="px-4 py-2.5 text-left text-text-muted font-medium">Metric</th>
                    <th className="px-4 py-2.5 text-right text-amber-400 font-medium">SAP Optimizer</th>
                    <th className="px-4 py-2.5 text-right text-text-muted font-medium">Equal-Weight</th>
                    <th className="px-4 py-2.5 text-right text-text-muted font-medium">Δ vs Benchmark</th>
                  </tr>
                </thead>
                <tbody>
                  {benchRows.map(row => {
                    const delta = row.optVal - row.stVal
                    const good  = row.higherIsBetter === null
                      ? null
                      : row.higherIsBetter ? delta > 0 : delta < 0

                    const fmtVal = (v: number) =>
                      row.isInt ? String(Math.round(v)) :
                      row.label === 'Duration (yr)' ? `${v.toFixed(2)} yr` :
                      fmt$(v)

                    const deltaColor =
                      good === null ? 'text-text-muted' :
                      good          ? 'text-emerald-400' : 'text-red-400'

                    return (
                      <tr key={row.label} className="border-b border-border/60 hover:bg-surface-2/30">
                        <td className="px-4 py-3 text-text-secondary font-medium">{row.label}</td>
                        <td className="px-4 py-3 text-right text-amber-400 font-mono font-semibold">
                          {fmtVal(row.optVal)}
                        </td>
                        <td className="px-4 py-3 text-right text-text-muted font-mono">
                          {fmtVal(row.stVal)}
                        </td>
                        <td className={`px-4 py-3 text-right font-mono font-semibold ${deltaColor}`}>
                          {row.isInt || row.label === 'Duration (yr)'
                            ? `${delta >= 0 ? '+' : ''}${fmtVal(delta)}`
                            : `${delta >= 0 ? '+' : ''}${fmt$(delta)}`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Section 2: IMR Impact ──────────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <h3 className="text-text-primary font-medium text-sm">IMR Impact (Interest Maintenance Reserve)</h3>
            {isOptimal && Math.abs(imrTotal) > 1 && (
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                imrTotal >= 0
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  : 'bg-red-500/10 text-red-400 border-red-500/20'
              }`}>
                {imrTotal >= 0 ? '+' : ''}{fmt$(imrTotal)} net realized gain
              </span>
            )}
          </div>
          <p className="text-text-muted text-xs mb-3">
            Rate-driven gains/losses on bond sales are deferred into IMR and released into NII on a straight-line basis over remaining duration.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see IMR schedule" />
          ) : !hasSells ? (
            <EmptyState label="No bonds sold — no IMR entries this rebalance" />
          ) : (
            <>
              <div className="h-52 mb-4">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={imrSchedule} margin={{ top: 4, right: 20, bottom: 0, left: 20 }}>
                    <CartesianGrid stroke="#1f2937" vertical={false} />
                    <XAxis
                      dataKey="period"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis yAxisId="left"  tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                    <Tooltip
                      contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                      formatter={(value: number, name: string) => [
                        fmt$(value),
                        name === 'imr_release' ? 'Quarterly NII Release' : 'IMR Balance',
                      ]}
                    />
                    <Bar yAxisId="left" dataKey="imr_release" fill="#10b981" opacity={0.8} radius={[2, 2, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="imr_balance" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
                <div className="flex items-center gap-4 justify-center mt-1">
                  <span className="flex items-center gap-1.5 text-xs text-text-muted">
                    <span className="inline-block w-3 h-2 rounded-md bg-emerald-500/80" />Quarterly NII release
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-text-muted">
                    <span className="inline-block w-4 border-t-2 border-amber-400" />IMR balance
                  </span>
                </div>
              </div>

              {/* Per-trade IMR — top 15 visible, scrollable, View more to expand */}
              {(() => {
                const sorted   = [...imrContribs].sort((a, b) => Math.abs(b.realized_gain) - Math.abs(a.realized_gain))
                const visible  = showAllIMR ? sorted : sorted.slice(0, IMR_PAGE)
                const overflow = sorted.length - IMR_PAGE

                return (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-text-muted text-xs uppercase tracking-wider">Per-trade IMR contributions</p>
                      {sorted.length > 0 && (
                        <p className="text-text-muted text-xs">{sorted.length} trade{sorted.length !== 1 ? 's' : ''}</p>
                      )}
                    </div>
                    <div className="rounded-2xl border border-border overflow-hidden">
                      <div className={`overflow-y-auto overflow-x-auto ${showAllIMR ? 'max-h-[420px]' : ''}`}>
                        <table className="w-full text-xs">
                          <thead className="sticky top-0">
                            <tr className="bg-surface-2/90 border-b border-border">
                              {['CUSIP', 'Sale Amount', 'Mid Price', 'Realized Gain'].map(h => (
                                <th key={h} className="px-4 py-2 text-left text-text-muted font-medium">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {visible.map((c, i) => (
                              <tr key={i} className="border-b border-border/60 hover:bg-surface-2/30">
                                <td className="px-4 py-2.5 font-mono text-text-secondary">{c.cusip}</td>
                                <td className="px-4 py-2.5 font-mono text-text-secondary">{fmt$(c.sale_usd)}</td>
                                <td className="px-4 py-2.5 font-mono text-text-secondary">{c.mid_price.toFixed(2)}</td>
                                <td className={`px-4 py-2.5 font-mono font-semibold ${c.realized_gain >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                  {c.realized_gain >= 0 ? '+' : ''}{fmt$(c.realized_gain)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* View more / View less footer */}
                      {overflow > 0 && (
                        <div className="border-t border-border bg-surface-2/60">
                          <button
                            onClick={() => setShowAllIMR(v => !v)}
                            className="w-full py-2 text-xs text-text-muted hover:text-amber-400 transition-colors flex items-center justify-center gap-1.5"
                          >
                            {showAllIMR
                              ? <>▲ View less</>
                              : <>▼ View {overflow} more trade{overflow !== 1 ? 's' : ''}</>}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })()}
            </>
          )}
        </section>

        {/* ── Section 2b: Swap Overlay ──────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-3 mb-1">
            <h3 className="text-text-primary font-medium text-sm">Swap Overlay</h3>
            <span className="text-text-muted text-xs">Receive-fixed interest-rate swaps</span>
            {isOptimal && hasSwaps && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-purple-500/10 text-purple-400 border border-purple-500/20">
                {fmt$(totalSwapNotional)} notional
              </span>
            )}
          </div>
          <p className="text-text-muted text-xs mb-3">
            Swaps adjust duration at a fraction of bond bid-ask cost. Decision variables{' '}
            <span className="font-mono text-text-muted">v[k]</span> enter the SAP LP jointly
            with bond holdings <span className="font-mono text-text-muted">h[i]</span>.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see swap overlay" />
          ) : !hasSwaps ? (
            <EmptyState label="No swap overlay active — optimizer chose 0 notional for all tenors" />
          ) : (
            <>
              {/* Summary KPI strip */}
              <div className="grid grid-cols-3 gap-2 mb-4">
                {[
                  { label: 'Total Notional', value: fmt$(totalSwapNotional), color: 'text-purple-400' },
                  { label: 'Net Income',     value: `+${fmt$(totalSwapIncome)}`, color: 'text-emerald-400' },
                  { label: 'Dur. Contribution', value: `${totalSwapDur.toFixed(4)} yr`, color: 'text-blue-400' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-surface-2/60 rounded-2xl p-3 border border-border/50">
                    <p className="text-text-muted text-xs mb-1">{label}</p>
                    <p className={`font-mono font-semibold text-sm ${color}`}>{value}</p>
                  </div>
                ))}
              </div>

              {/* Per-tenor allocation table */}
              <div className="overflow-x-auto rounded-2xl border border-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-surface-2/80 border-b border-border">
                      {['Tenor', 'Notional', 'Fixed Rate', 'Float Rate', 'Net Income ($/yr)', 'Dur. Contrib. (yr)'].map(h => (
                        <th key={h} className="px-4 py-2 text-left text-text-muted font-medium whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {swapAllocs.map((s, i) => (
                      <tr key={i} className={`border-b border-border/60 hover:bg-surface-2/30 ${s.notional > 1_000 ? '' : 'opacity-40'}`}>
                        <td className="px-4 py-2.5 font-mono text-purple-400 font-semibold">{s.tenor_years.toFixed(0)}yr</td>
                        <td className="px-4 py-2.5 font-mono text-text-secondary">{fmt$(s.notional)}</td>
                        <td className="px-4 py-2.5 font-mono text-text-secondary">{(s.fixed_rate * 100).toFixed(2)}%</td>
                        <td className="px-4 py-2.5 font-mono text-text-secondary">{result ? (result.r_float * 100).toFixed(2) : '—'}%</td>
                        <td className={`px-4 py-2.5 font-mono font-semibold ${s.net_income >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {s.net_income >= 0 ? '+' : ''}{fmt$(s.net_income)}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-blue-400">{s.dur_contrib.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        {/* ── Section LP-B: Per-Bond Shadow Price vs Z-Spread ───────────── */}
        <section>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-text-primary font-medium text-sm">Marginal LP Value vs Z-Spread</h3>
            <span className="text-text-muted text-xs">Per-bond Gurobi reduced costs</span>
            <span className="px-2 py-0.5 rounded-full text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20">LP</span>
          </div>
          <p className="text-text-muted text-xs mb-3">
            X = Z-spread (credit risk proxy, bps). Y = reduced cost × 10 000 (bps) — SAP improvement per $1 invested.
            Bonds above zero are at their upper weight limit; their constraint is binding on the optimizer.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see per-bond shadow prices" />
          ) : (
            <>
              {/* Scatter chart */}
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 8, right: 20, bottom: 24, left: 10 }}>
                    <CartesianGrid stroke="#1f2937" />
                    <XAxis
                      dataKey="x"
                      type="number"
                      name="Z-Spread"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      label={{ value: 'Z-Spread (bps)', position: 'insideBottom', offset: -12, fill: '#6b7280', fontSize: 10 }}
                    />
                    <YAxis
                      dataKey="y"
                      type="number"
                      name="Shadow Price"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={(v: number) => v.toFixed(3)}
                      label={{ value: 'Shadow (bps)', angle: -90, position: 'insideLeft', offset: 12, fill: '#6b7280', fontSize: 10 }}
                    />
                    <Tooltip content={<LPScatterTooltip />} cursor={{ stroke: '#374151', strokeWidth: 1 }} />
                    <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="4 2" />
                    {LP_BUCKET_LABELS.map(([color]) => (
                      <Scatter key={color} data={lpScatterGroups[color] ?? []} fill={color} opacity={0.8} />
                    ))}
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-4 justify-center mt-1 mb-4 text-xs text-text-muted">
                {LP_BUCKET_LABELS.map(([color, label]) => (
                  <span key={label} className="flex items-center gap-1.5">
                    <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                    {label}
                  </span>
                ))}
              </div>

              {/* Sortable table */}
              <div className="rounded-2xl border border-border overflow-hidden">
                <div className={`overflow-x-auto ${showAllLP ? 'overflow-y-auto max-h-[500px]' : ''}`}>
                  <table className="w-full text-xs">
                    <thead className="sticky top-0">
                      <tr className="bg-surface-2/90 border-b border-border">
                        {([
                          { key: 'cusip',        label: 'CUSIP',                 sortable: false },
                          { key: 'rating',       label: 'Rating',                sortable: false },
                          { key: 'duration',     label: 'Duration (yr)',          sortable: true  },
                          { key: 'spread_bps',   label: 'Z-Spread (bps)',         sortable: true  },
                          { key: 'reduced_cost', label: 'Shadow Price (SAP/$1M)', sortable: true  },
                        ]).map(col => (
                          <th
                            key={col.key}
                            onClick={col.sortable
                              ? () => toggleLpSort(col.key as 'reduced_cost' | 'spread_bps' | 'duration')
                              : undefined}
                            className={`px-4 py-2 text-left text-text-muted font-medium whitespace-nowrap
                              ${col.sortable ? 'cursor-pointer hover:text-amber-400 select-none' : ''}`}
                          >
                            {col.label}
                            {col.sortable && lpSortKey === col.key && (
                              <span className="ml-1 text-amber-400">{lpSortDesc ? '▼' : '▲'}</span>
                            )}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(showAllLP ? lpAllocs : lpAllocs.slice(0, LP_PAGE)).map((a, i) => {
                        const rc = a.reduced_cost ?? 0
                        return (
                          <tr key={i} className={`border-b border-border/60 hover:bg-surface-2/30 ${rc > 0 ? 'bg-amber-500/5' : ''}`}>
                            <td className="px-4 py-2.5 font-mono text-amber-400">{a.cusip}</td>
                            <td className="px-4 py-2.5 font-mono text-text-secondary">{a.rating}</td>
                            <td className="px-4 py-2.5 font-mono text-text-secondary">{a.duration.toFixed(2)}</td>
                            <td className="px-4 py-2.5 font-mono text-blue-400">{a.spread_bps.toFixed(1)}</td>
                            <td className={`px-4 py-2.5 font-mono font-semibold ${rc > 0 ? 'text-amber-400' : 'text-text-muted'}`}>
                              {(rc * 1e6).toFixed(2)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {lpAllocs.length > LP_PAGE && (
                  <div className="border-t border-border bg-surface-2/60">
                    <button
                      onClick={() => setShowAllLP(v => !v)}
                      className="w-full py-2 text-xs text-text-muted hover:text-amber-400 transition-colors flex items-center justify-center gap-1.5"
                    >
                      {showAllLP ? <>▲ Show fewer</> : <>▼ Show all {lpAllocs.length} bonds</>}
                    </button>
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        {/* ── Section LP-C: Per-Bond Reservation Price ────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-text-primary font-medium text-sm">Per-Bond Reservation Price</h3>
            <span className="text-text-muted text-xs">Same shadow price, in $/100 face terms</span>
            <span className="px-2 py-0.5 rounded-full text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20">LP</span>
          </div>
          <p className="text-text-muted text-xs mb-3">
            P* = PV of the bond's cashflows discounted at its own hurdle yield (book yield − reduced cost).
            Gap = P* − market price: positive means the bond is worth more to this portfolio than it costs to buy.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see per-bond reservation prices" />
          ) : reservationPrices.length === 0 ? (
            <EmptyState label="No reservation-price data for this solve" />
          ) : (
            <div className="rounded-2xl border border-border overflow-hidden">
              <div className={`overflow-x-auto ${showAllRes ? 'overflow-y-auto max-h-[500px]' : ''}`}>
                <table className="w-full text-xs">
                  <thead className="sticky top-0">
                    <tr className="bg-surface-2/90 border-b border-border">
                      {['CUSIP', 'Mkt Price', 'Reservation P*', 'Gap', 'Gap %', 'Hurdle Rate', ''].map(h => (
                        <th key={h} className="px-4 py-2 text-left text-text-muted font-medium whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(showAllRes ? reservationPrices : reservationPrices.slice(0, RES_PAGE)).map((r, i) => (
                      <tr key={i} className={`border-b border-border/60 hover:bg-surface-2/30 ${r.gap > 0 ? 'bg-emerald-500/5' : r.gap < 0 ? 'bg-red-500/5' : ''}`}>
                        <td className="px-4 py-2.5 font-mono text-amber-400">{r.cusip}</td>
                        <td className="px-4 py-2.5 font-mono text-text-secondary">${r.mkt_price.toFixed(2)}</td>
                        <td className="px-4 py-2.5 font-mono text-text-secondary">${r.reservation_price.toFixed(2)}</td>
                        <td className={`px-4 py-2.5 font-mono font-semibold ${r.gap > 0 ? 'text-emerald-400' : r.gap < 0 ? 'text-red-400' : 'text-text-muted'}`}>
                          {r.gap >= 0 ? '+' : ''}{r.gap.toFixed(2)}
                        </td>
                        <td className={`px-4 py-2.5 font-mono ${r.gap > 0 ? 'text-emerald-400' : r.gap < 0 ? 'text-red-400' : 'text-text-muted'}`}>
                          {r.gap_pct >= 0 ? '+' : ''}{r.gap_pct.toFixed(2)}%
                        </td>
                        <td className="px-4 py-2.5 font-mono text-text-muted">{r.hurdle_rate.toFixed(3)}%</td>
                        <td className="px-4 py-2.5">
                          {r.selected && (
                            <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">HELD</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {reservationPrices.length > RES_PAGE && (
                <div className="border-t border-border bg-surface-2/60">
                  <button
                    onClick={() => setShowAllRes(v => !v)}
                    className="w-full py-2 text-xs text-text-muted hover:text-amber-400 transition-colors flex items-center justify-center gap-1.5"
                  >
                    {showAllRes ? <>▲ Show fewer</> : <>▼ Show all {reservationPrices.length} (top/bottom 25 by gap)</>}
                  </button>
                </div>
              )}
            </div>
          )}
        </section>

        {/* ── Section 3: Shadow Prices ───────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-text-primary font-medium text-sm">Constraint Shadow Prices</h3>
          </div>
          <p className="text-text-muted text-xs mb-3">
            Marginal SAP improvement from relaxing each constraint by one unit.
            Amber rows are binding — these constraints are limiting the optimizer.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see shadow prices" />
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface-2/80 border-b border-border">
                    <th className="px-4 py-2.5 text-left text-text-muted font-medium">Constraint</th>
                    <th className="px-4 py-2.5 text-right text-text-muted font-medium">Shadow Price</th>
                    <th className="px-4 py-2.5 text-left text-text-muted font-medium">Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  {shadowPrices.map((row, i) => {
                    const isBinding = row.dual !== null && Math.abs(row.dual) > 1
                    return (
                      <tr key={i} className={`border-b border-border/60 hover:bg-surface-2/30 ${isBinding ? 'bg-amber-500/5' : ''}`}>
                        <td className={`px-4 py-3 font-medium ${isBinding ? 'text-amber-300' : 'text-text-secondary'}`}>{row.label}</td>
                        <td className={`px-4 py-3 text-right font-mono font-semibold ${
                          row.dual === null          ? 'text-text-muted' :
                          Math.abs(row.dual) < 0.01 ? 'text-text-muted' :
                          isBinding                 ? 'text-amber-400' : 'text-text-secondary'
                        }`}>
                          {row.dual === null
                            ? 'n/a'
                            : `${row.dual >= 0 ? '+' : ''}${fmtDual(row.dual)} ${row.unit}`}
                        </td>
                        <td className="px-4 py-3 text-text-muted">
                          {row.dual === null
                            ? 'Constraint not found in model'
                            : Math.abs(row.dual) < 0.01
                            ? 'Not binding — slack available'
                            : `Relaxing by 1 unit adds ${fmt$(Math.abs(row.dual))} to SAP`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          {isOptimal && budgetPi !== null && marginalUnconstrained !== null && (
            <div className="mt-3 p-3.5 rounded-2xl border border-border bg-surface-2/40 text-xs">
              <p className="text-text-secondary">
                <span className="font-medium">Marginal $ with no issuer/diversification caps:</span>{' '}
                <span className="font-mono text-amber-400">${fmtDual(marginalUnconstrained)}</span> vs{' '}
                <span className="font-mono text-text-secondary">${fmtDual(budgetPi)}</span> constrained
              </p>
              <p className="text-text-muted mt-1">
                Dropping the 5% issuer caps would make the next dollar worth{' '}
                <span className="font-mono text-amber-400">${fmtDual(marginalUnconstrained - budgetPi)}</span> more —
                that's the value currently held back by diversification requirements.
              </p>
            </div>
          )}
        </section>

        {/* ── Section 3B: Facility Shadow Prices by Quarter ──────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-text-primary font-medium text-sm">Facility Shadow Prices by Quarter</h3>
          </div>
          <p className="text-text-muted text-xs mb-3">
            Marginal SAP value of $1 more lending-facility balance, per quarter. More negative = that quarter's
            liquidity is most urgently needed to cover FABN payments.
          </p>
          {!isOptimal ? (
            <EmptyState label="Run optimizer to see facility shadow prices" />
          ) : piFacility.length === 0 ? (
            <EmptyState label="No facility shadow-price data for this solve" />
          ) : (() => {
            const tightest = piFacility.reduce((min, row) => row.dual < min.dual ? row : min, piFacility[0])
            return (
              <>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={piFacility} margin={{ top: 8, right: 16, bottom: 0, left: 16 }}>
                      <CartesianGrid stroke="#1f2937" vertical={false} />
                      <XAxis dataKey="period" tick={{ fill: '#6b7280', fontSize: 10 }} interval="preserveStartEnd" />
                      <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => v.toFixed(3)} width={48} />
                      <Tooltip
                        contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                        formatter={(v: number) => [v.toFixed(4), 'Shadow price']}
                      />
                      <ReferenceLine y={0} stroke="#4b5563" />
                      <Bar dataKey="dual" maxBarSize={28} radius={[3, 3, 0, 0]}>
                        {piFacility.map((row, idx) => (
                          <Cell key={idx} fill={row.dual < -1e-6 ? '#ef4444' : row.dual > 1e-6 ? '#10b981' : '#6b7280'} opacity={0.8} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="text-text-muted text-xs mt-2 text-center">
                  Tightest funding quarter: <span className="text-red-400 font-mono">{tightest.period}</span>{' '}
                  (shadow price {tightest.dual.toFixed(4)})
                </p>
              </>
            )
          })()}
        </section>

        {/* ── Section 3C: Issuer Concentration Caps ──────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-text-primary font-medium text-sm">Issuer Concentration Caps</h3>
          </div>
          <p className="text-text-muted text-xs mb-3">
            Issuers where the 5% single-issuer cap is actively binding — the optimizer wants to hold more than the
            cap allows. "$ if cap +1pp" is the SAP gain from relaxing that issuer's cap by one percentage point.
          </p>
          {!isOptimal ? (
            <EmptyState label="Run optimizer to see issuer concentration caps" />
          ) : piIssuerBinding.length === 0 ? (
            <div className="h-16 bg-surface-2/40 rounded-2xl border border-border border-dashed flex items-center justify-center">
              <p className="text-text-muted text-sm">No issuer caps are currently binding</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface-2/80 border-b border-border">
                    <th className="px-4 py-2.5 text-left text-text-muted font-medium">Issuer (6-char CUSIP)</th>
                    <th className="px-4 py-2.5 text-right text-text-muted font-medium">Shadow Price</th>
                    <th className="px-4 py-2.5 text-right text-text-muted font-medium">$ if cap +1pp</th>
                  </tr>
                </thead>
                <tbody>
                  {piIssuerBinding.map((row, i) => (
                    <tr key={i} className="border-b border-border/60 hover:bg-surface-2/30 bg-amber-500/5">
                      <td className="px-4 py-3 font-mono text-amber-300">{row.issuer}</td>
                      <td className="px-4 py-3 text-right font-mono font-semibold text-amber-400">
                        ${fmtDual(row.dual)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-text-secondary">
                        {fmt$(Math.abs(row.dual) * 0.01 * 500_000_000)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Section 4: Applied Trades Log ─────────────────────────────── */}
        {appliedTrades.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-text-primary font-medium text-sm">Applied Trades Log</h3>
              <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {appliedTrades.length} trade{appliedTrades.length > 1 ? 's' : ''}
              </span>
            </div>
            <div className="overflow-x-auto rounded-2xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-surface-2/80 border-b border-border">
                    {['Applied On', 'CUSIP', 'Action', 'Δ USD', 'Target ($M)'].map(h => (
                      <th key={h} className="px-4 py-2.5 text-left text-text-muted font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...appliedTrades].reverse().map((t, i) => (
                    <tr key={i} className="border-b border-border/60 hover:bg-surface-2/30">
                      <td className="px-4 py-2.5 font-mono text-text-muted">{t.appliedAt}</td>
                      <td className="px-4 py-2.5 font-mono text-amber-400">{t.cusip}</td>
                      <td className="px-4 py-2.5">
                        <span className={`px-1.5 py-0.5 rounded-lg text-xs font-bold ${
                          t.action === 'BUY'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}>{t.action}</span>
                      </td>
                      <td className={`px-4 py-2.5 font-mono font-semibold ${t.delta_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {t.delta_usd >= 0 ? '+' : ''}{fmt$(t.delta_usd)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-text-secondary">
                        ${(t.h_opt / 1e6).toFixed(2)}M
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

      </div>
    </Modal>
  )
}
