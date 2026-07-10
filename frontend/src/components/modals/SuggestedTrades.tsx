import Modal from './Modal'
import type { OptimizerResult, Trade } from '../../types'

interface Props {
  onClose: () => void
  result:  OptimizerResult | null
  loading: boolean
}

function fmtDelta(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `${n < 0 ? '−' : '+'}$${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1_000)     return `${n < 0 ? '−' : '+'}$${(abs / 1e3).toFixed(0)}k`
  return `${n < 0 ? '−' : '+'}$${abs.toFixed(0)}`
}

function TradeCard({ trade }: { trade: Trade }) {
  const isBuy = trade.action === 'BUY'

  return (
    <div className={`rounded-xl p-3.5 border flex items-start gap-3 ${
      isBuy
        ? 'bg-emerald-500/5 border-emerald-500/15'
        : 'bg-red-500/5 border-red-500/15'
    }`}>
      {/* Action badge */}
      <span className={`flex-shrink-0 px-2 py-0.5 rounded-md text-xs font-bold mt-0.5 ${
        isBuy
          ? 'bg-emerald-500/20 text-emerald-400'
          : 'bg-red-500/20 text-red-400'
      }`}>
        {isBuy ? '▲ BUY' : '▼ SELL'}
      </span>

      {/* Details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-white text-xs font-mono font-semibold truncate">{trade.cusip}</p>
          <span className={`font-mono text-sm font-bold flex-shrink-0 ${
            isBuy ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {fmtDelta(trade.delta_usd)}
          </span>
        </div>
        <p className="text-gray-500 text-xs truncate mt-0.5">{trade.sector || '—'}</p>
        <div className="flex gap-3 mt-1.5 text-xs text-gray-600">
          <span>Δ <span className={`font-mono ${isBuy ? 'text-emerald-500' : 'text-red-500'}`}>
            {trade.delta_weight_pct >= 0 ? '+' : ''}{trade.delta_weight_pct.toFixed(2)}%
          </span></span>
          <span>Sprd <span className="text-blue-400 font-mono">{trade.spread_bps.toFixed(0)} bps</span></span>
          <span>Dur <span className="text-gray-400 font-mono">{trade.duration.toFixed(1)} yr</span></span>
          {trade.rating && <span className="text-gray-500 font-mono">{trade.rating}</span>}
        </div>
      </div>
    </div>
  )
}

function SectionHeader({
  label, count, color,
}: { label: string; count: number; color: 'green' | 'red' }) {
  return (
    <div className={`flex items-center gap-2 mb-2 ${color === 'green' ? 'text-emerald-400' : 'text-red-400'}`}>
      <span className="text-xs font-bold uppercase tracking-wider">{label}</span>
      <span className={`text-xs px-1.5 py-0.5 rounded-full font-mono ${
        color === 'green'
          ? 'bg-emerald-500/15 text-emerald-400'
          : 'bg-red-500/15 text-red-400'
      }`}>{count}</span>
      <div className={`flex-1 h-px ${color === 'green' ? 'bg-emerald-900/60' : 'bg-red-900/60'}`} />
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="rounded-xl p-3.5 border border-gray-700 bg-gray-800/40 flex items-start gap-3 animate-pulse">
      <div className="w-14 h-6 rounded-md bg-gray-700 flex-shrink-0" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3 bg-gray-700 rounded w-2/5" />
        <div className="h-2.5 bg-gray-700 rounded w-3/5" />
        <div className="h-2 bg-gray-700 rounded w-4/5" />
      </div>
    </div>
  )
}

export default function SuggestedTrades({ onClose, result, loading }: Props) {
  const isOptimal = result?.status === 'optimal'
  const allTrades: Trade[] = isOptimal ? (result?.trades ?? []) : []

  const buys  = allTrades.filter(t => t.action === 'BUY')
  const sells = allTrades.filter(t => t.action === 'SELL')

  return (
    <Modal title="Suggested Trades" subtitle="Optimization-driven rebalancing recommendations" onClose={onClose}>
      <div className="space-y-5">

        {/* Summary banner */}
        <div className={`p-3.5 rounded-xl border text-xs ${
          isOptimal
            ? 'bg-gray-800/60 border-gray-700'
            : 'bg-amber-500/5 border-amber-500/20'
        }`}>
          {isOptimal ? (
            <div className="flex items-center gap-6">
              <span className="text-gray-400">
                Optimizer rebalancing vs equal-weight baseline:
              </span>
              <span className="text-emerald-400 font-semibold">{buys.length} increases</span>
              <span className="text-red-400 font-semibold">{sells.length} reductions / exits</span>
              <span className="text-gray-600">threshold $100k · top 15 each side</span>
            </div>
          ) : (
            <p className="text-amber-400 font-medium">
              {loading ? '⟳ Running optimizer…' : '★ Run the optimizer to generate rebalancing trades'}
            </p>
          )}
        </div>

        {loading && !isOptimal ? (
          /* Loading skeleton — show both sides */
          <div className="grid grid-cols-2 gap-4">
            <div>
              <SectionHeader label="Increase / Enter" count={0} color="green" />
              <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}</div>
            </div>
            <div>
              <SectionHeader label="Reduce / Exit" count={0} color="red" />
              <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}</div>
            </div>
          </div>
        ) : isOptimal ? (
          /* Two-column BUY / SELL layout */
          <div className="grid grid-cols-2 gap-4">
            {/* BUYs */}
            <div>
              <SectionHeader label="Increase / Enter" count={buys.length} color="green" />
              {buys.length > 0
                ? <div className="space-y-2">{buys.map((t, i) => <TradeCard key={`buy-${i}`} trade={t} />)}</div>
                : <p className="text-gray-600 text-xs py-4 text-center">No buys above threshold</p>
              }
            </div>

            {/* SELLs */}
            <div>
              <SectionHeader label="Reduce / Exit" count={sells.length} color="red" />
              {sells.length > 0
                ? <div className="space-y-2">{sells.map((t, i) => <TradeCard key={`sell-${i}`} trade={t} />)}</div>
                : <p className="text-gray-600 text-xs py-4 text-center">No sells above threshold</p>
              }
            </div>
          </div>
        ) : (
          <div className="py-10 text-center text-gray-600 text-sm">
            No trades to show — run the optimizer first.
          </div>
        )}

        {/* Chart placeholder */}
        <div className="h-36 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
          <p className="text-gray-600 text-sm">Trade impact chart — pre/post weight comparison</p>
        </div>
      </div>
    </Modal>
  )
}
