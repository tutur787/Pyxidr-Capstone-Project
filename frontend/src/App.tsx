import { useState, useEffect, useCallback } from 'react'
import Header from './components/layout/Header'
import TabBar from './components/layout/TabBar'
import PortfolioKPI from './components/panels/PortfolioKPI'
import MarketsPanel from './components/panels/MarketsPanel'
import NewsPanel from './components/panels/NewsPanel'
import AIChat from './components/panels/AIChat'
import PortfolioDeepDive from './components/modals/PortfolioDeepDive'
import SuggestedTrades from './components/modals/SuggestedTrades'
import StrategyTracking from './components/modals/StrategyTracking'
import Risk from './components/modals/Risk'
import DerivativeUsage from './components/modals/DerivativeUsage'
import { useDate } from './hooks/useDate'
import { defaultHyperParams, STUB_FABNS } from './data/stubs'
import type { TabId, HyperParams, Fabn, OptimizerResult, Trade, AppliedTrade, HistoryEntry } from './types'

export default function App() {
  const { date, advanceDate, jumpToDate, isAtMin, isAtMax, formatDisplay } = useDate()
  const [activeModal, setActiveModal] = useState<TabId | null>(null)
  const [hyperParams, setHyperParams] = useState<HyperParams>(defaultHyperParams)
  const [fabns, setFabns] = useState<Fabn[]>(STUB_FABNS)
  const [selectedFabns, setSelectedFabns] = useState<Fabn[]>([])

  // Optimizer state
  const [optimizerResult, setOptimizerResult]   = useState<OptimizerResult | null>(null)
  const [optimizerLoading, setOptimizerLoading] = useState(false)
  const [optimizerError, setOptimizerError]     = useState<string | null>(null)

  // Applied-trade state (persists across dates until explicit reset)
  const [appliedTrades, setAppliedTrades] = useState<AppliedTrade[]>([])

  // Session history — one entry per date visited, updated on each optimizer run
  const [history, setHistory] = useState<HistoryEntry[]>([])

  useEffect(() => {
    fetch('/api/fabns')
      .then(r => r.json())
      .then((data: Fabn[]) => {
        if (data && data.length > 0) setFabns(data)
      })
      .catch(() => {}) // keep stubs on failure
  }, [])

  // ── Optimizer ──────────────────────────────────────────────────────────────
  const runOptimizer = useCallback(async (d: string, p: HyperParams) => {
    setOptimizerLoading(true)
    setOptimizerError(null)
    const url =
      `/api/optimize?date=${d}` +
      `&gamma_w=${p.gamma_w}` +
      `&lambda_w=${p.lambda_w}` +
      `&eps_D=${p.eps_D}` +
      `&w_max=${p.w_max}` +
      `&n_min=${p.n_min}`
    try {
      const res  = await fetch(url)
      const data: OptimizerResult = await res.json()
      if (data.status === 'optimal') {
        setOptimizerResult(data)
        setHistory(prev => {
          const marketValue = data.allocations.reduce((s, a) => s + a.h_opt * a.mid_price / 100, 0)
          const entry: HistoryEntry = {
            date:             data.date,
            sap_opt:          data.nev,
            sap_static:       data.static_comparison.sap,
            alpha:            data.nev - data.static_comparison.sap,
            yield_pct:        data.yield_pct,
            duration:         data.duration,
            duration_gap:     data.duration_gap,
            spread_bps:       data.spread_bps,
            n_bonds_selected: data.n_bonds_selected,
            txn_cost:         data.txn_cost,
            market_value:     marketValue,
          }
          // Replace any existing entry for this date, then keep sorted
          return [...prev.filter(h => h.date !== data.date), entry]
            .sort((a, b) => a.date.localeCompare(b.date))
        })
      } else if (data.status === 'infeasible') {
        setOptimizerError('Model infeasible — try relaxing constraints (ε_D, w_max, n_min)')
        setOptimizerResult(null)
      } else {
        setOptimizerError(data.error ?? 'Optimizer returned an error')
        setOptimizerResult(null)
      }
    } catch {
      setOptimizerError('Could not reach the optimizer backend')
    } finally {
      setOptimizerLoading(false)
    }
  }, [])

  const applyTrade = useCallback(async (trade: Trade) => {
    await fetch('/api/portfolio/apply-trade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cusip: trade.cusip, h_opt: trade.h_opt }),
    })
    setAppliedTrades(prev => [...prev, {
      cusip:     trade.cusip,
      action:    trade.action,
      delta_usd: trade.delta_usd,
      h_opt:     trade.h_opt,
      appliedAt: date,
    }])
    runOptimizer(date, hyperParams)
  }, [date, hyperParams, runOptimizer])

  const resetPortfolio = useCallback(async () => {
    await fetch('/api/portfolio/reset', { method: 'POST' })
    setAppliedTrades([])
    setHistory([])
    runOptimizer(date, hyperParams)
  }, [date, hyperParams, runOptimizer])

  // Re-run on date change
  useEffect(() => {
    runOptimizer(date, hyperParams)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date])

  function closeModal() { setActiveModal(null) }

  return (
    <div className="min-h-screen flex flex-col bg-gray-950 text-gray-100">
      <div className="sticky top-0 z-30">
        <Header
          date={date}
          formattedDate={formatDisplay(date)}
          onAdvance={advanceDate}
          onJumpToDate={jumpToDate}
          isAtMin={isAtMin}
          isAtMax={isAtMax}
          hyperParams={hyperParams}
          onHyperParamsChange={setHyperParams}
          fabns={fabns}
          selectedFabns={selectedFabns}
          onFabnChange={setSelectedFabns}
          onApply={() => runOptimizer(date, hyperParams)}
        />

        <TabBar onTabClick={setActiveModal} />

        {/* Optimizer loading / error banner */}
        {optimizerLoading && (
          <div className="px-4 py-1.5 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-amber-400 text-xs font-medium animate-pulse">
              Optimizing portfolio for {date}…
            </span>
          </div>
        )}
        {!optimizerLoading && optimizerError && (
          <div className="px-4 py-1.5 bg-red-500/10 border-b border-red-500/20 flex items-center gap-2">
            <span className="text-red-400 text-xs">⚠ {optimizerError}</span>
          </div>
        )}
      </div>

      {/* main layout */}
      <main className="flex gap-3 p-3 overflow-hidden" style={{ height: 'calc(100vh - 100px)' }}>
        {/* Left: Portfolio KPI — full height */}
        <div className="flex flex-col" style={{ flex: '2' }}>
          <PortfolioKPI
            date={date}
            optimizerResult={optimizerResult}
            optimizerLoading={optimizerLoading}
            history={history}
          />
        </div>

        {/* Right: two rows stacked */}
        <div className="flex flex-col gap-3" style={{ flex: '2' }}>
          {/* Top row: Markets + News side by side */}
          <div className="flex gap-3 flex-1 min-h-0">
            <div className="flex-1 min-w-0">
              <MarketsPanel date={date} />
            </div>
            <div className="flex-1 min-w-0">
              <NewsPanel date={date} />
            </div>
          </div>

          {/* Bottom row: AI Chat */}
          <div className="flex-shrink-0" style={{ height: '280px' }}>
            <AIChat />
          </div>
        </div>
      </main>

      {/* Modals */}
      {activeModal === 'portfolio-deep-dive' && (
        <PortfolioDeepDive
          onClose={closeModal}
          result={optimizerResult}
          loading={optimizerLoading}
        />
      )}
      {activeModal === 'suggested-trades' && (
        <SuggestedTrades
          onClose={closeModal}
          result={optimizerResult}
          loading={optimizerLoading}
          appliedTrades={appliedTrades}
          onApplyTrade={applyTrade}
          onResetPortfolio={resetPortfolio}
        />
      )}
      {activeModal === 'strategy-tracking' && (
        <StrategyTracking
          onClose={closeModal}
          result={optimizerResult}
          history={history}
          appliedTrades={appliedTrades}
        />
      )}
      {activeModal === 'risk' && (
        <Risk
          onClose={closeModal}
          result={optimizerResult}
          loading={optimizerLoading}
        />
      )}
      {activeModal === 'derivative-usage' && <DerivativeUsage onClose={closeModal} />}
    </div>
  )
}
