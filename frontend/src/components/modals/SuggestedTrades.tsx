import { useState } from 'react'
import Modal from './Modal'
import type { OptimizerResult, Trade, AppliedTrade } from '../../types'

interface Props {
  onClose:          () => void
  result:           OptimizerResult | null
  loading:          boolean
  appliedTrades:    AppliedTrade[]
  onApplyTrade:     (trade: Trade) => Promise<void>
  onResetPortfolio: () => Promise<void>
}

function fmtDelta(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `${n < 0 ? '−' : '+'}$${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1_000)     return `${n < 0 ? '−' : '+'}$${(abs / 1e3).toFixed(0)}k`
  return `${n < 0 ? '−' : '+'}$${abs.toFixed(0)}`
}

function TradeCard({
  trade,
  applied,
  onApply,
}: {
  trade:    Trade
  applied:  boolean
  onApply:  (t: Trade) => Promise<void>
}) {
  const isBuy = trade.action === 'BUY'
  const [pending, setPending] = useState(false)

  async function handleApply() {
    if (applied || pending) return
    setPending(true)
    try {
      await onApply(trade)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={`rounded-xl p-3.5 border flex items-start gap-3 ${
      isBuy
        ? 'bg-emerald-500/5 border-emerald-500/15'
        : 'bg-red-500/5 border-red-500/15'
    } ${applied ? 'opacity-60' : ''}`}>
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
        <div className="flex gap-3 mt-1.5 text-xs text-gray-600 flex-wrap">
          <span title="Net SAP contribution rate: NII minus capital cost, per $ invested">
            SAP <span className={`font-mono font-semibold ${trade.sap_score_bps >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
              {trade.sap_score_bps >= 0 ? '+' : ''}{trade.sap_score_bps.toFixed(1)} bps
            </span>
          </span>
          <span>Δ <span className={`font-mono ${isBuy ? 'text-emerald-500' : 'text-red-500'}`}>
            {trade.delta_weight_pct >= 0 ? '+' : ''}{trade.delta_weight_pct.toFixed(2)}%
          </span></span>
          <span>Sprd <span className="text-blue-400 font-mono">{trade.spread_bps.toFixed(0)} bps</span></span>
          <span>Dur <span className="text-gray-400 font-mono">{trade.duration.toFixed(1)} yr</span></span>
          {trade.rating && <span className="text-gray-500 font-mono">{trade.rating}</span>}
        </div>
        {/* Price row */}
        {(() => {
          const mktPrice    = trade.mid_price
          const shadowPrice = mktPrice * (1 + trade.duration * trade.sap_score_bps / 10_000)
          const spread      = shadowPrice - mktPrice
          return (
            <div className="flex gap-4 mt-1.5 text-xs flex-wrap">
              <span className="text-gray-600">
                Price (Mkt){' '}
                <span className="font-mono text-gray-300">${mktPrice.toFixed(2)}</span>
              </span>
              <span
                className="text-gray-600"
                title="LP-implied fair value: price at which this bond's net SAP contribution = 0. Above mkt = cheap (buy); below mkt = rich (sell)."
              >
                Price (Shadow){' '}
                <span className={`font-mono font-semibold ${spread >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  ${shadowPrice.toFixed(2)}
                </span>
                <span className={`ml-1 ${spread >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                  ({spread >= 0 ? '+' : ''}{spread.toFixed(2)})
                </span>
              </span>
            </div>
          )
        })()}
      </div>

      {/* Apply button */}
      <div className="flex-shrink-0 mt-0.5">
        {applied ? (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold bg-gray-700/60 text-gray-400">
            ✓ Applied
          </span>
        ) : (
          <button
            onClick={handleApply}
            disabled={pending}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-colors
              ${pending
                ? 'bg-amber-500/10 text-amber-500 cursor-not-allowed'
                : 'bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border border-amber-500/20 hover:border-amber-500/40'
              }`}
          >
            {pending ? (
              <><span className="animate-spin inline-block w-3 h-3 border border-amber-400 border-t-transparent rounded-full" />Applying…</>
            ) : 'Apply'}
          </button>
        )}
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

export default function SuggestedTrades({
  onClose, result, loading, appliedTrades, onApplyTrade, onResetPortfolio,
}: Props) {
  const isOptimal = result?.status === 'optimal'
  const allTrades: Trade[] = isOptimal ? (result?.trades ?? []) : []

  const buys  = allTrades.filter(t => t.action === 'BUY')
  const sells = allTrades.filter(t => t.action === 'SELL')

  // Set of CUSIPs applied this session for instant visual feedback
  const appliedCusips = new Set(appliedTrades.map(a => a.cusip))

  const [resetConfirm, setResetConfirm] = useState(false)
  const [resetPending, setResetPending] = useState(false)

  async function handleReset() {
    if (!resetConfirm) { setResetConfirm(true); return }
    setResetPending(true)
    try {
      await onResetPortfolio()
    } finally {
      setResetPending(false)
      setResetConfirm(false)
    }
  }

  return (
    <Modal title="Suggested Trades" subtitle="Optimization-driven rebalancing recommendations" onClose={onClose}>
      <div className="space-y-5">

        {/* Applied-trades summary strip */}
        {appliedTrades.length > 0 && (
          <div className="flex items-center gap-3 px-3.5 py-2.5 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs">
            <span className="text-amber-400 font-semibold">
              {appliedTrades.length} trade{appliedTrades.length > 1 ? 's' : ''} applied this session
            </span>
            <span className="text-gray-600 flex-1">
              {appliedTrades.map(a => a.cusip).join(', ')}
            </span>
            <button
              onClick={handleReset}
              disabled={resetPending}
              className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                resetConfirm
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
                  : 'bg-gray-700 text-gray-400 hover:text-gray-200 hover:bg-gray-600'
              } ${resetPending ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {resetPending ? 'Resetting…' : resetConfirm ? 'Confirm reset?' : 'Reset portfolio'}
            </button>
            {resetConfirm && !resetPending && (
              <button
                onClick={() => setResetConfirm(false)}
                className="text-gray-600 hover:text-gray-400 transition-colors"
              >
                Cancel
              </button>
            )}
          </div>
        )}

        {/* Status banner */}
        <div className={`p-3.5 rounded-xl border text-xs ${
          isOptimal
            ? 'bg-gray-800/60 border-gray-700'
            : 'bg-amber-500/5 border-amber-500/20'
        }`}>
          {isOptimal ? (
            <div className="flex items-center gap-6">
              <span className="text-gray-400">
                Optimizer rebalancing vs current baseline:
              </span>
              <span className="text-emerald-400 font-semibold">{buys.length} increases</span>
              <span className="text-red-400 font-semibold">{sells.length} reductions / exits</span>
              <span className="text-gray-600">threshold $100k · top 15 each side · ranked by SAP score</span>
            </div>
          ) : (
            <p className="text-amber-400 font-medium">
              {loading ? '⟳ Running optimizer…' : '★ Run the optimizer to generate rebalancing trades'}
            </p>
          )}
        </div>

        {loading && !isOptimal ? (
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
          <div className="grid grid-cols-2 gap-4">
            {/* BUYs */}
            <div>
              <SectionHeader label="Increase / Enter" count={buys.length} color="green" />
              {buys.length > 0
                ? <div className="space-y-2">{buys.map((t, i) => (
                    <TradeCard
                      key={`buy-${i}`}
                      trade={t}
                      applied={appliedCusips.has(t.cusip)}
                      onApply={onApplyTrade}
                    />
                  ))}</div>
                : <p className="text-gray-600 text-xs py-4 text-center">No buys above threshold</p>
              }
            </div>

            {/* SELLs */}
            <div>
              <SectionHeader label="Reduce / Exit" count={sells.length} color="red" />
              {sells.length > 0
                ? <div className="space-y-2">{sells.map((t, i) => (
                    <TradeCard
                      key={`sell-${i}`}
                      trade={t}
                      applied={appliedCusips.has(t.cusip)}
                      onApply={onApplyTrade}
                    />
                  ))}</div>
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
