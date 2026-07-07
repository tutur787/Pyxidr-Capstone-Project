import { useState } from 'react'
import Modal from './Modal'
import type { OptimizerResult, Trade, AppliedTrade } from '../../types'

interface Props {
  onClose:          () => void
  result:           OptimizerResult | null
  loading:          boolean
  appliedTrades:    AppliedTrade[]
  onApplyTrade:     (trade: Trade) => Promise<void>
  onApplyAllTrades: (trades: Trade[]) => Promise<void>
  onResetPortfolio: () => Promise<void>
  applyInProgress:  boolean  // global lock — prevents concurrent apply operations
}

function fmtDelta(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `${n < 0 ? '−' : '+'}$${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1_000)     return `${n < 0 ? '−' : '+'}$${(abs / 1e3).toFixed(0)}k`
  return `${n < 0 ? '−' : '+'}$${abs.toFixed(0)}`
}

function fmtAbs(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `$${(abs / 1e6).toFixed(1)}M`
  if (abs >= 1_000)     return `$${(abs / 1e3).toFixed(0)}k`
  return `$${abs.toFixed(0)}`
}

function TradeCard({
  trade,
  applied,
  onApply,
  onFundedApply,
  fundLabel,
  canFund,
  applyInProgress,
}: {
  trade:            Trade
  applied:          boolean
  onApply?:         (t: Trade) => Promise<void>  // SELL cards only
  onFundedApply?:   () => Promise<void>           // BUY cards only (funded or pre-funded)
  fundLabel?:       string
  canFund?:         boolean
  applyInProgress:  boolean
}) {
  const isBuy = trade.action === 'BUY'
  const [pending, setPending] = useState(false)
  const disabled = pending || applyInProgress

  async function handleSell() {
    if (applied || disabled || !onApply) return
    setPending(true)
    try { await onApply(trade) } finally { setPending(false) }
  }

  async function handleFundedBuy() {
    if (applied || disabled || !onFundedApply) return
    setPending(true)
    try { await onFundedApply() } finally { setPending(false) }
  }

  const mktPrice    = trade.mid_price
  const shadowPrice = mktPrice * (1 + trade.duration * trade.sap_score_bps / 10_000)
  const priceDiff   = shadowPrice - mktPrice

  return (
    <div className={`rounded-2xl p-3.5 border flex items-start gap-3 ${
      isBuy
        ? 'bg-emerald-500/5 border-emerald-500/15'
        : 'bg-red-500/5 border-red-500/15'
    } ${applied ? 'opacity-60' : ''}`}>

      {/* Action badge */}
      <span className={`flex-shrink-0 px-2 py-0.5 rounded-lg text-xs font-bold mt-0.5 ${
        isBuy ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
      }`}>
        {isBuy ? '▲ BUY' : '▼ SELL'}
      </span>

      {/* Details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-text-primary text-xs font-mono font-semibold truncate">{trade.cusip}</p>
          <span className={`font-mono text-sm font-bold flex-shrink-0 ${
            isBuy ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {fmtDelta(trade.delta_usd)}
          </span>
        </div>
        <p className="text-text-muted text-xs truncate mt-0.5">{trade.sector || '—'}</p>
        <div className="flex gap-3 mt-1.5 text-xs text-text-muted flex-wrap">
          <span title="Net SAP contribution rate: NII minus capital cost, per $ invested">
            SAP <span className={`font-mono font-semibold ${trade.sap_score_bps >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
              {trade.sap_score_bps >= 0 ? '+' : ''}{trade.sap_score_bps.toFixed(1)} bps
            </span>
          </span>
          <span>Δ <span className={`font-mono ${isBuy ? 'text-emerald-500' : 'text-red-500'}`}>
            {trade.delta_weight_pct >= 0 ? '+' : ''}{trade.delta_weight_pct.toFixed(2)}%
          </span></span>
          <span>Sprd <span className="text-blue-400 font-mono">{trade.spread_bps.toFixed(0)} bps</span></span>
          <span>Dur <span className="text-text-muted font-mono">{trade.duration.toFixed(1)} yr</span></span>
          {trade.rating && <span className="text-text-muted font-mono">{trade.rating}</span>}
        </div>
        <div className="flex gap-4 mt-1.5 text-xs flex-wrap">
          <span className="text-text-muted">
            Price (Mkt){' '}
            <span className="font-mono text-text-secondary">${mktPrice.toFixed(2)}</span>
          </span>
          <span
            className="text-text-muted"
            title="LP-implied fair value: price at which this bond's net SAP contribution = 0. Above mkt = cheap (buy); below mkt = rich (sell)."
          >
            Price (Shadow){' '}
            <span className={`font-mono font-semibold ${priceDiff >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              ${shadowPrice.toFixed(2)}
            </span>
            <span className={`ml-1 ${priceDiff >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
              ({priceDiff >= 0 ? '+' : ''}{priceDiff.toFixed(2)})
            </span>
          </span>
        </div>
      </div>

      {/* Action button */}
      <div className="flex-shrink-0 mt-0.5">
        {applied ? (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-semibold bg-surface-3/60 text-text-muted">
            ✓ Applied
          </span>
        ) : isBuy ? (
          canFund ? (
            <button
              onClick={handleFundedBuy}
              disabled={disabled}
              title={fundLabel}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors text-center leading-tight ${
                disabled
                  ? 'bg-emerald-500/10 text-emerald-500 cursor-not-allowed'
                  : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/20 hover:border-emerald-500/40'
              }`}
            >
              {pending ? (
                <><span className="animate-spin inline-block w-3 h-3 border border-emerald-400 border-t-transparent rounded-full" />Applying…</>
              ) : fundLabel ?? 'Buy'}
            </button>
          ) : (
            <span
              className="inline-flex items-center px-2 py-1 rounded-lg text-xs text-text-muted border border-border/50 cursor-default text-center leading-tight"
              title="Apply sells (any sells, your choice) first to free up capacity for this buy"
            >
              {fundLabel}
            </span>
          )
        ) : (
          <button
            onClick={handleSell}
            disabled={disabled}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
              disabled
                ? 'bg-amber-500/10 text-amber-500 cursor-not-allowed'
                : 'bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border border-amber-500/20 hover:border-amber-500/40'
            }`}
          >
            {pending ? (
              <><span className="animate-spin inline-block w-3 h-3 border border-amber-400 border-t-transparent rounded-full" />Selling…</>
            ) : 'Sell'}
          </button>
        )}
      </div>
    </div>
  )
}

function SectionHeader({ label, count, color }: { label: string; count: number; color: 'green' | 'red' }) {
  return (
    <div className={`flex items-center gap-2 mb-2 ${color === 'green' ? 'text-emerald-400' : 'text-red-400'}`}>
      <span className="text-xs font-bold uppercase tracking-wider">{label}</span>
      <span className={`text-xs px-1.5 py-0.5 rounded-full font-mono ${
        color === 'green' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
      }`}>{count}</span>
      <div className={`flex-1 h-px ${color === 'green' ? 'bg-emerald-900/60' : 'bg-red-900/60'}`} />
    </div>
  )
}

function TradingSignalBanner({ result }: { result: OptimizerResult }) {
  const { current_vol_bps, threshold_vol_bps, ratio_to_median, percentile, worth_trading, degraded } = result.trading_signal
  if (current_vol_bps == null || worth_trading == null) return null
  return (
    <div
      className={`p-3.5 rounded-2xl border flex items-center gap-3 text-xs ${
        worth_trading ? 'bg-brand-highlight/5 border-brand-highlight/25' : 'bg-surface-2/60 border-border'
      }`}
      title={`Historically-driven signal (informational only): 21-day rolling volatility of the cross-sectional median book yield vs. the ${percentile.toFixed(0)}th percentile of its own trailing-year distribution — the Size-of-Prize volatility-threshold trigger. Does not gate the optimizer.`}
    >
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

function SkeletonCard() {
  return (
    <div className="rounded-2xl p-3.5 border border-border bg-surface-2/40 flex items-start gap-3 animate-pulse">
      <div className="w-14 h-6 rounded-lg bg-surface-3 flex-shrink-0" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3 bg-surface-3 rounded-lg w-2/5" />
        <div className="h-2.5 bg-surface-3 rounded-lg w-3/5" />
        <div className="h-2 bg-surface-3 rounded-lg w-4/5" />
      </div>
    </div>
  )
}

export default function SuggestedTrades({
  onClose, result, loading, appliedTrades, onApplyTrade, onApplyAllTrades,
  onResetPortfolio, applyInProgress,
}: Props) {
  const isOptimal  = result?.status === 'optimal'
  const allTrades: Trade[] = isOptimal ? (result?.trades ?? []) : []
  const buys  = allTrades.filter(t => t.action === 'BUY')
  const sells = allTrades.filter(t => t.action === 'SELL')
  const appliedCusips = new Set(appliedTrades.map(a => a.cusip))

  const [resetConfirm, setResetConfirm] = useState(false)
  const [resetPending, setResetPending] = useState(false)

  async function handleReset() {
    if (!resetConfirm) { setResetConfirm(true); return }
    setResetPending(true)
    try { await onResetPortfolio() }
    finally { setResetPending(false); setResetConfirm(false) }
  }

  // Net capacity freed by individually-applied sells (minus any applied buys). Any BUY
  // whose delta fits within this shared pool can be applied — the user picks which sells
  // and which buys to execute, in any order, rather than the optimizer pre-pairing them.
  const netSellCapacity = Math.max(0,
    appliedTrades.filter(t => t.action === 'SELL').reduce((s, t) => s + Math.abs(t.delta_usd), 0) -
    appliedTrades.filter(t => t.action === 'BUY').reduce((s, t) => s + Math.abs(t.delta_usd), 0)
  )

  const buyFundings = buys.map(buyTrade => {
    const canFund = netSellCapacity >= buyTrade.delta_usd
    return {
      canFund,
      label: canFund ? 'Buy' : `Need ${fmtAbs(buyTrade.delta_usd - netSellCapacity)} more sells`,
    }
  })

  return (
    <Modal title="Suggested Trades" subtitle="Optimization-driven rebalancing recommendations" onClose={onClose}>
      <div className="space-y-5">

        {/* Volatility-triggered trading signal (Size-of-Prize methodology) */}
        {isOptimal && result && <TradingSignalBanner result={result} />}

        {/* Applied-trades summary strip */}
        {appliedTrades.length > 0 && (
          <div className="flex items-center gap-3 px-3.5 py-2.5 rounded-2xl bg-amber-500/5 border border-amber-500/20 text-xs">
            <span className="text-amber-400 font-semibold">
              {appliedTrades.length} trade{appliedTrades.length > 1 ? 's' : ''} applied this session
            </span>
            <span className="text-text-muted flex-1">
              {appliedTrades.map(a => a.cusip).join(', ')}
            </span>
            <button
              onClick={handleReset}
              disabled={resetPending}
              className={`px-2.5 py-1 rounded-lg font-semibold transition-colors ${
                resetConfirm
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
                  : 'bg-surface-3 text-text-muted hover:text-text-primary hover:bg-surface-3'
              } ${resetPending ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {resetPending ? 'Resetting…' : resetConfirm ? 'Confirm reset?' : 'Reset portfolio'}
            </button>
            {resetConfirm && !resetPending && (
              <button onClick={() => setResetConfirm(false)} className="text-text-muted hover:text-text-muted transition-colors">
                Cancel
              </button>
            )}
          </div>
        )}

        {/* Status banner */}
        <div className={`p-3.5 rounded-2xl border text-xs ${
          isOptimal ? 'bg-surface-2/60 border-border' : 'bg-amber-500/5 border-amber-500/20'
        }`}>
          {isOptimal ? (
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-text-muted">Optimizer rebalancing vs current baseline:</span>
              <span className="text-emerald-400 font-semibold">{buys.length} increases</span>
              <span className="text-red-400 font-semibold">{sells.length} reductions / exits</span>
              <span className="text-text-muted">threshold $100k · top 15 each side · ranked by SAP score</span>
              <span className="text-text-muted ml-auto italic">Apply any sells to free capacity, then any buy that fits — stays ≤ $500M</span>
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
            {/* BUYs — any buy can be applied once accumulated sell capacity covers its delta */}
            <div>
              <SectionHeader label="Increase / Enter" count={buys.length} color="green" />
              {buys.length > 0
                ? <div className="space-y-2">{buys.map((t, i) => {
                    const { label, canFund } = buyFundings[i]
                    return (
                      <TradeCard
                        key={`buy-${i}`}
                        trade={t}
                        applied={appliedCusips.has(t.cusip)}
                        canFund={canFund}
                        fundLabel={label}
                        onFundedApply={() => onApplyAllTrades([t])}
                        applyInProgress={applyInProgress}
                      />
                    )
                  })}</div>
                : <p className="text-text-muted text-xs py-4 text-center">No buys above threshold</p>
              }
            </div>

            {/* SELLs — individual apply */}
            <div>
              <SectionHeader label="Reduce / Exit" count={sells.length} color="red" />
              {sells.length > 0
                ? <div className="space-y-2">{sells.map((t, i) => (
                    <TradeCard
                      key={`sell-${i}`}
                      trade={t}
                      applied={appliedCusips.has(t.cusip)}
                      onApply={onApplyTrade}
                      applyInProgress={applyInProgress}
                    />
                  ))}</div>
                : <p className="text-text-muted text-xs py-4 text-center">No sells above threshold</p>
              }
            </div>
          </div>
        ) : (
          <div className="py-10 text-center text-text-muted text-sm">
            No trades to show — run the optimizer first.
          </div>
        )}
      </div>
    </Modal>
  )
}
