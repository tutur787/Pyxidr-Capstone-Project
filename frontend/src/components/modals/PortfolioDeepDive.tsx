import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  CartesianGrid,
} from 'recharts'
import Modal from './Modal'
import type { BondAllocation, OptimizerResult } from '../../types'

interface Props {
  onClose: () => void
  result:  OptimizerResult | null
  loading: boolean
}

const SKELETON_ROWS = 8
const COLS = ['CUSIP', 'Sector', 'Rating', 'Weight %', 'Spread (bps)', 'Duration', 'Alloc ($M)']

const SECTOR_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444',
  '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
]

function mostCommonRating(allocs: BondAllocation[]): string {
  const counts: Record<string, number> = {}
  for (const a of allocs) {
    if (a.rating) counts[a.rating] = (counts[a.rating] ?? 0) + 1
  }
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
  return sorted[0]?.[0] ?? '—'
}

function sectorData(allocs: BondAllocation[]) {
  const map: Record<string, number> = {}
  for (const a of allocs) {
    const s = a.sector || 'Unknown'
    map[s] = (map[s] ?? 0) + a.h_opt
  }
  return Object.entries(map)
    .map(([sector, total]) => ({ sector, totalM: total / 1e6 }))
    .sort((a, b) => b.totalM - a.totalM)
    .slice(0, 12)   // top 12 sectors
}

export default function PortfolioDeepDive({ onClose, result, loading }: Props) {
  const isOptimal = result?.status === 'optimal'
  const allocs    = isOptimal ? (result?.allocations ?? []) : []
  const sectors   = sectorData(allocs)

  const avgDuration = allocs.length
    ? (allocs.reduce((s, a) => s + a.duration * a.h_opt, 0) / allocs.reduce((s, a) => s + a.h_opt, 0)).toFixed(2)
    : '—'
  const avgSpread = allocs.length
    ? (allocs.reduce((s, a) => s + a.spread_bps * a.h_opt, 0) / allocs.reduce((s, a) => s + a.h_opt, 0)).toFixed(1)
    : '—'

  return (
    <Modal title="Portfolio Deep-Dive" subtitle="Full bond-level breakdown of the optimized portfolio" onClose={onClose}>
      <div className="space-y-6">

        {/* Summary strip */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Total Bonds',   value: isOptimal ? String(allocs.length) : undefined },
            { label: 'Avg Duration',  value: isOptimal ? `${avgDuration} yrs`  : undefined },
            { label: 'Avg Spread',    value: isOptimal ? `${avgSpread} bps`     : undefined },
            { label: 'Avg Rating',    value: isOptimal ? mostCommonRating(allocs) : undefined },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-gray-500 text-xs mb-1">{label}</p>
              {value !== undefined
                ? <p className="text-white font-mono font-semibold text-sm">{value}</p>
                : <div className="h-5 w-16 bg-gray-700 rounded animate-pulse" />}
            </div>
          ))}
        </div>

        {/* Bond table */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">
            Bond Universe
            {isOptimal && <span className="text-gray-500 font-normal ml-2">({allocs.length} positions)</span>}
          </h3>
          <div className="overflow-x-auto rounded-xl border border-gray-700 max-h-72 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0">
                <tr className="bg-gray-800 border-b border-gray-700">
                  {COLS.map(c => (
                    <th key={c} className="px-4 py-2.5 text-left text-gray-400 font-medium whitespace-nowrap">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isOptimal
                  ? allocs.map((a, i) => (
                    <tr key={a.cusip} className={`border-b border-gray-800 hover:bg-gray-800/40 ${i % 2 === 0 ? '' : 'bg-gray-900/40'}`}>
                      <td className="px-4 py-2.5 font-mono text-amber-400">{a.cusip}</td>
                      <td className="px-4 py-2.5 text-gray-300 max-w-[140px] truncate">{a.sector}</td>
                      <td className="px-4 py-2.5">
                        <span className="px-1.5 py-0.5 bg-gray-700 rounded text-gray-300 font-mono">{a.rating || '—'}</span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-gray-200">{(a.weight * 100).toFixed(2)}%</td>
                      <td className="px-4 py-2.5 font-mono text-blue-400">{a.spread_bps.toFixed(1)}</td>
                      <td className="px-4 py-2.5 font-mono text-gray-300">{a.duration.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-emerald-400">${(a.h_opt / 1e6).toFixed(2)}M</td>
                    </tr>
                  ))
                  : Array.from({ length: SKELETON_ROWS }).map((_, i) => (
                    <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                      {COLS.map(c => (
                        <td key={c} className="px-4 py-3">
                          <div
                            className="h-3 bg-gray-700/60 rounded animate-pulse"
                            style={{ width: `${50 + (i * 7 + c.length * 3) % 40}%` }}
                          />
                        </td>
                      ))}
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>
          {!isOptimal && (
            <p className="text-gray-600 text-xs mt-2 text-center">
              {loading ? 'Optimizer running…' : 'Bond-level data will populate from the optimizer output.'}
            </p>
          )}
        </div>

        {/* Quarterly Cashflow chart */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-white font-medium text-sm">Quarterly Cashflow</h3>
            <span className="text-gray-600 text-xs">FABN obligations · asset receipts · net balance</span>
          </div>
          {isOptimal && (result?.cashflows ?? []).length > 0 ? (() => {
            const cfData = result!.cashflows.map(row => ({
              period:      row.period,
              fabn_cf:     row.fabn_cf,
              asset_cf:    row.asset_cf,
              facility_bal: row.facility_bal,   // optimizer's running cumulative balance
            }))
            const fmtM = (v: number) => {
              const abs = Math.abs(v)
              const sign = v < 0 ? '−' : ''
              return abs >= 1_000_000
                ? `${sign}$${(abs / 1_000_000).toFixed(1)}M`
                : `${sign}$${(abs / 1_000).toFixed(0)}k`
            }
            return (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={cfData} margin={{ top: 8, right: 16, bottom: 0, left: 16 }} barCategoryGap="25%" barGap={3}>
                    <CartesianGrid stroke="#1f2937" vertical={false} />
                    <XAxis dataKey="period" tick={{ fill: '#6b7280', fontSize: 10 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={fmtM} width={56} />
                    <Tooltip
                      contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                      formatter={(value: number, name: string) => [
                        fmtM(value),
                        name === 'fabn_cf'       ? 'FABN obligation' :
                        name === 'asset_cf'      ? 'Asset receipts'  : 'Total balance',
                      ]}
                    />
                    <Bar dataKey="fabn_cf"  fill="#ef4444" opacity={0.75} maxBarSize={22} radius={[3,3,0,0]} />
                    <Bar dataKey="asset_cf" fill="#10b981" opacity={0.80} maxBarSize={22} radius={[3,3,0,0]} />
                    <Bar dataKey="facility_bal" maxBarSize={22} radius={[3,3,0,0]}>
                      {cfData.map((row, idx) => (
                        <Cell key={idx} fill={row.facility_bal >= 0 ? '#3b82f6' : '#f97316'} opacity={0.80} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="flex items-center gap-5 justify-center mt-2 text-xs text-gray-500">
                  <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-2.5 rounded-sm bg-red-500/75" />FABN obligation</span>
                  <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-2.5 rounded-sm bg-emerald-500/80" />Asset receipts</span>
                  <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-2.5 rounded-sm bg-blue-500/80" />Total balance (surplus)</span>
                  <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-2.5 rounded-sm bg-orange-500/80" />Total balance (deficit)</span>
                </div>
              </div>
            )
          })() : (
            <div className="h-20 bg-gray-800/40 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
              <p className="text-gray-600 text-sm">
                {loading ? 'Optimizer running…' : 'Quarterly cashflow chart — run optimizer to populate'}
              </p>
            </div>
          )}
        </div>

        {/* Sector allocation chart */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Weight Distribution by Sector</h3>
          {isOptimal && sectors.length > 0 ? (
            <div style={{ height: Math.max(180, sectors.length * 32) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={sectors}
                  layout="vertical"
                  margin={{ top: 4, right: 60, bottom: 4, left: 120 }}
                >
                  <XAxis
                    type="number"
                    tickFormatter={v => `$${v.toFixed(0)}M`}
                    tick={{ fill: '#6b7280', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="sector"
                    width={115}
                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    formatter={(v: number) => [`$${v.toFixed(1)}M`, 'Allocation']}
                    contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                    labelStyle={{ color: '#f3f4f6' }}
                    itemStyle={{ color: '#10b981' }}
                  />
                  <Bar dataKey="totalM" radius={[0, 4, 4, 0]} maxBarSize={22}>
                    {sectors.map((_, idx) => (
                      <Cell key={idx} fill={SECTOR_COLORS[idx % SECTOR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-40 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
              <p className="text-gray-600 text-sm">
                {loading ? 'Optimizer running…' : 'Sector allocation chart — populate from optimizer'}
              </p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
