import Modal from './Modal'
import type { ConstraintResult, OptimizerResult } from '../../types'

interface Props {
  onClose: () => void
  result:  OptimizerResult | null
  loading: boolean
}

function fmtConstraintValue(c: ConstraintResult): string {
  switch (c.label) {
    case 'Budget':
      return `$${(c.value / 1e6).toFixed(1)}M`
    case 'Solvency (RBC)':
      return `${c.value.toFixed(3)}x`
    case 'Duration Gap':
      return `${c.value.toFixed(3)} yrs`
    case 'PV Shortfall':
      return `$${(c.value / 1e3).toFixed(1)}k`
    default:
      return String(c.value)
  }
}

function fmtConstraintBound(c: ConstraintResult): string {
  switch (c.label) {
    case 'Budget':
      return `= $${(c.bound / 1e6).toFixed(0)}M`
    case 'Solvency (RBC)':
      return `≥ ${c.bound.toFixed(1)}x`
    case 'Duration Gap':
      return `≤ ${c.bound.toFixed(2)} yrs`
    case 'PV Shortfall':
      return `≤ $${(c.bound / 1e3).toFixed(1)}k`
    default:
      return String(c.bound)
  }
}

function ConstraintCard({ c }: { c: ConstraintResult }) {
  return (
    <div className={`p-4 rounded-xl border ${c.pass
      ? 'bg-emerald-500/5 border-emerald-500/20'
      : 'bg-red-500/5 border-red-500/20'}`}>
      <div className="flex items-center justify-between mb-1">
        <p className="text-gray-400 text-xs">{c.label}</p>
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

// Stub cards that remain until more analytics are connected
const STUB_METRICS = [
  { label: 'CVaR (95%)',        value: '2.87%', status: 'Within budget', ok: true  },
  { label: 'Sector Cap (max)', value: '—',     status: 'Requires sector data', ok: true },
]

function StubCard({ label, value, status, ok }: { label: string; value: string; status: string; ok: boolean }) {
  return (
    <div className={`p-4 rounded-xl border ${ok
      ? 'bg-gray-800/60 border-gray-700'
      : 'bg-amber-500/5 border-amber-500/20'}`}>
      <div className="flex items-center justify-between mb-1">
        <p className="text-gray-400 text-xs">{label}</p>
        <span className={`text-xs ${ok ? 'text-gray-600' : 'text-amber-400'}`}>{ok ? '○' : '⚠'}</span>
      </div>
      <p className="font-mono font-semibold text-lg text-gray-500">{value}</p>
      <p className="text-xs mt-0.5 text-gray-600">{status}</p>
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
            <h3 className="text-white font-medium text-sm">Constraint Status</h3>
            {isOptimal && (
              <span className="text-emerald-400 text-xs px-2 py-0.5 bg-emerald-500/10 rounded-full border border-emerald-500/20">
                ● Live from optimizer
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {isOptimal && constraints.length > 0
              ? constraints.map((c, i) => <ConstraintCard key={i} c={c} />)
              : Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="p-4 rounded-xl border bg-gray-800/60 border-gray-700 animate-pulse">
                  <div className="h-3 bg-gray-700 rounded w-2/3 mb-2" />
                  <div className="h-6 bg-gray-700 rounded w-1/2 mb-1" />
                  <div className="h-2 bg-gray-700 rounded w-3/4" />
                </div>
              ))
            }
            {/* Stub cards always shown below live constraints */}
            {STUB_METRICS.map(m => <StubCard key={m.label} {...m} />)}
          </div>
        </div>

        {/* RBC breakdown */}
        {isOptimal && result && (
          <div>
            <h3 className="text-white font-medium text-sm mb-3">RBC Capital Breakdown</h3>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="bg-gray-800/40 rounded-xl p-3 border border-gray-700">
                <p className="text-gray-500 mb-1">RBC Ratio</p>
                <p className="text-emerald-400 font-mono font-bold text-base">{result.rbc_ratio.toFixed(2)}x</p>
                <p className="text-gray-600 mt-0.5">min 1.5x</p>
              </div>
              <div className="bg-gray-800/40 rounded-xl p-3 border border-gray-700">
                <p className="text-gray-500 mb-1">C-1 Capital</p>
                <p className="text-amber-400 font-mono font-bold text-base">${(result.c1_cost / 1e6).toFixed(2)}M</p>
                <p className="text-gray-600 mt-0.5">{(result.rbc_c1_usage * 100).toFixed(1)}% of budget</p>
              </div>
              <div className="bg-gray-800/40 rounded-xl p-3 border border-gray-700">
                <p className="text-gray-500 mb-1">Duration Gap</p>
                <p className="text-blue-400 font-mono font-bold text-base">{result.duration_gap.toFixed(3)} yr</p>
                <p className="text-gray-600 mt-0.5">ε_D tolerance</p>
              </div>
            </div>
          </div>
        )}

        {/* CVaR distribution placeholder */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Return Distribution & CVaR Boundary</h3>
          <div className="h-48 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
            <p className="text-gray-600 text-sm">Histogram of scenario returns with VaR / CVaR lines</p>
          </div>
        </div>

        {/* CIR scenarios placeholder */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Interest Rate Scenarios (CIR Model)</h3>
          <div className="h-40 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
            <p className="text-gray-600 text-sm">50-path CIR simulation with mean reversion bands</p>
          </div>
        </div>
      </div>
    </Modal>
  )
}
