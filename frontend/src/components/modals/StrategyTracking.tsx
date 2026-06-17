import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import type { OptimizerResult } from '../../types'
import Modal from './Modal'

interface Props {
  onClose: () => void
  result:  OptimizerResult | null
}

function fmt$(n: number): string {
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-20 bg-gray-800/40 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
      <p className="text-gray-600 text-sm">{label}</p>
    </div>
  )
}

export default function StrategyTracking({ onClose, result }: Props) {
  const isOptimal = result?.status === 'optimal'
  const sc        = isOptimal ? result!.static_comparison : null

  // ── SAP vs Static rows ────────────────────────────────────────────────────
  type BenchRow = { label: string; optVal: number; stVal: number; higherIsBetter: boolean | null; isInt?: boolean }
  const benchRows: BenchRow[] = isOptimal && sc ? [
    { label: 'Statutory NII',      optVal: result!.spread_income,     stVal: sc.nii,          higherIsBetter: true  },
    { label: 'Capital Cost (RBC)', optVal: result!.capital_cost,      stVal: sc.capital_cost, higherIsBetter: false },
    { label: 'SAP Objective',      optVal: result!.nev,               stVal: sc.sap,          higherIsBetter: true  },
    { label: 'Duration (yr)',      optVal: result!.duration,          stVal: sc.duration,     higherIsBetter: null  },
    { label: '# Bonds',           optVal: result!.n_bonds_selected,  stVal: sc.n_bonds,      higherIsBetter: null, isInt: true },
  ] : []

  // ── IMR ───────────────────────────────────────────────────────────────────
  const imrSchedule = result?.imr_schedule ?? []
  const imrContribs = result?.imr_contributions ?? []
  const imrTotal    = result?.imr_total_gain ?? 0
  const hasSells    = imrContribs.length > 0

  // ── Shadow prices ─────────────────────────────────────────────────────────
  const shadowPrices = result?.shadow_prices ?? []

  return (
    <Modal title="Strategy Tracking" subtitle="SAP optimizer vs. benchmark · IMR amortization · constraint analysis" onClose={onClose}>
      <div className="space-y-8">

        {/* ── Section 1: SAP vs Static ───────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-white font-medium text-sm">SAP Optimizer vs Equal-Weight Benchmark</h3>
            {isOptimal && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Live
              </span>
            )}
          </div>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see benchmark comparison" />
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-700">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-800/80 border-b border-gray-700">
                    <th className="px-4 py-2.5 text-left text-gray-400 font-medium">Metric</th>
                    <th className="px-4 py-2.5 text-right text-amber-400 font-medium">SAP Optimizer</th>
                    <th className="px-4 py-2.5 text-right text-gray-400 font-medium">Equal-Weight</th>
                    <th className="px-4 py-2.5 text-right text-gray-400 font-medium">Δ vs Benchmark</th>
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
                      good === null ? 'text-gray-500' :
                      good          ? 'text-emerald-400' : 'text-red-400'

                    return (
                      <tr key={row.label} className="border-b border-gray-800/60 hover:bg-gray-800/30">
                        <td className="px-4 py-3 text-gray-300 font-medium">{row.label}</td>
                        <td className="px-4 py-3 text-right text-amber-400 font-mono font-semibold">
                          {fmtVal(row.optVal)}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-400 font-mono">
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
            <h3 className="text-white font-medium text-sm">IMR Impact (Interest Maintenance Reserve)</h3>
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
          <p className="text-gray-600 text-xs mb-3">
            Rate-driven gains/losses on bond sales are deferred into IMR and released into NII on a straight-line basis over remaining duration.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see IMR schedule" />
          ) : !hasSells ? (
            <EmptyState label="No bonds sold — no IMR entries this rebalance" />
          ) : (
            <>
              {/* Recharts: Bar = quarterly release, Line = balance */}
              <div className="h-52 mb-4">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={imrSchedule} margin={{ top: 4, right: 20, bottom: 0, left: 20 }}>
                    <CartesianGrid stroke="#1f2937" vertical={false} />
                    <XAxis
                      dataKey="period"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      yAxisId="left"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#111827',
                        border: '1px solid #374151',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(value: number, name: string) => [
                        fmt$(value),
                        name === 'imr_release' ? 'Quarterly NII Release' : 'IMR Balance',
                      ]}
                    />
                    <Bar
                      yAxisId="left"
                      dataKey="imr_release"
                      fill="#10b981"
                      opacity={0.8}
                      radius={[2, 2, 0, 0]}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="imr_balance"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      dot={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
                <div className="flex items-center gap-4 justify-center mt-1">
                  <span className="flex items-center gap-1.5 text-xs text-gray-500">
                    <span className="inline-block w-3 h-2 rounded-sm bg-emerald-500/80" />
                    Quarterly NII release
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-gray-500">
                    <span className="inline-block w-4 border-t-2 border-amber-400" />
                    IMR balance
                  </span>
                </div>
              </div>

              {/* Per-trade table */}
              <p className="text-gray-600 text-xs mb-2 uppercase tracking-wider">Per-trade IMR contributions</p>
              <div className="overflow-x-auto rounded-xl border border-gray-700">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-800/80 border-b border-gray-700">
                      {['CUSIP', 'Sale Amount', 'Mid Price', 'Realized Gain'].map(h => (
                        <th key={h} className="px-4 py-2 text-left text-gray-400 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {imrContribs.map((c, i) => (
                      <tr key={i} className="border-b border-gray-800/60 hover:bg-gray-800/30">
                        <td className="px-4 py-2.5 font-mono text-gray-300">{c.cusip}</td>
                        <td className="px-4 py-2.5 font-mono text-gray-300">{fmt$(c.sale_usd)}</td>
                        <td className="px-4 py-2.5 font-mono text-gray-300">{c.mid_price.toFixed(2)}</td>
                        <td className={`px-4 py-2.5 font-mono font-semibold ${
                          c.realized_gain >= 0 ? 'text-emerald-400' : 'text-red-400'
                        }`}>
                          {c.realized_gain >= 0 ? '+' : ''}{fmt$(c.realized_gain)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        {/* ── Section 3: Shadow Prices ───────────────────────────────────── */}
        <section>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-white font-medium text-sm">Constraint Shadow Prices</h3>
          </div>
          <p className="text-gray-600 text-xs mb-3">
            Marginal SAP improvement from relaxing each constraint by one unit.
            Amber rows are binding — these constraints are limiting the optimizer.
          </p>

          {!isOptimal ? (
            <EmptyState label="Run optimizer to see shadow prices" />
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-700">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-800/80 border-b border-gray-700">
                    <th className="px-4 py-2.5 text-left text-gray-400 font-medium">Constraint</th>
                    <th className="px-4 py-2.5 text-right text-gray-400 font-medium">Shadow Price</th>
                    <th className="px-4 py-2.5 text-left text-gray-400 font-medium">Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  {shadowPrices.map((row, i) => {
                    const isBinding = row.dual !== null && Math.abs(row.dual) > 1
                    return (
                      <tr
                        key={i}
                        className={`border-b border-gray-800/60 hover:bg-gray-800/30 ${isBinding ? 'bg-amber-500/5' : ''}`}
                      >
                        <td className={`px-4 py-3 font-medium ${isBinding ? 'text-amber-300' : 'text-gray-300'}`}>
                          {row.label}
                        </td>
                        <td className={`px-4 py-3 text-right font-mono font-semibold ${
                          row.dual === null          ? 'text-gray-600' :
                          Math.abs(row.dual) < 0.01 ? 'text-gray-500' :
                          isBinding                 ? 'text-amber-400' : 'text-gray-300'
                        }`}>
                          {row.dual === null
                            ? 'n/a'
                            : `${row.dual >= 0 ? '+' : ''}${row.dual.toFixed(2)} ${row.unit}`}
                        </td>
                        <td className="px-4 py-3 text-gray-500">
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
        </section>

      </div>
    </Modal>
  )
}
