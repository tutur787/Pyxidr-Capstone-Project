import { useState, useEffect } from 'react'
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
import type { TabId, HyperParams, Fabn } from './types'

export default function App() {
  const { date, advanceDate, isAtMin, isAtMax, formatDisplay } = useDate()
  const [activeModal, setActiveModal] = useState<TabId | null>(null)
  const [hyperParams, setHyperParams] = useState<HyperParams>(defaultHyperParams)
  const [fabns, setFabns] = useState<Fabn[]>(STUB_FABNS)
  const [selectedFabns, setSelectedFabns] = useState<Fabn[]>([])

  useEffect(() => {
    fetch('/api/fabns')
      .then(r => r.json())
      .then((data: Fabn[]) => {
        if (data && data.length > 0) {
          setFabns(data)
        }
      })
      .catch(() => {}) // keep stubs on failure
  }, [])

  function closeModal() { setActiveModal(null) }

  return (
    <div className="min-h-screen flex flex-col bg-gray-950 text-gray-100">
      <div className="sticky top-0 z-30">
        <Header
          date={date}
          formattedDate={formatDisplay(date)}
          onAdvance={advanceDate}
          isAtMin={isAtMin}
          isAtMax={isAtMax}
          hyperParams={hyperParams}
          onHyperParamsChange={setHyperParams}
          fabns={fabns}
          selectedFabns={selectedFabns}
          onFabnChange={setSelectedFabns}
        />

        <TabBar onTabClick={setActiveModal} />
      </div>

      {/* main layout */}
      <main className="flex gap-3 p-3 overflow-hidden" style={{ height: 'calc(100vh - 100px)' }}>
        {/* Left: Portfolio KPI — full height */}
        <div className="flex flex-col" style={{ flex: '2' }}>
          <PortfolioKPI date={date} />
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
      {activeModal === 'portfolio-deep-dive' && <PortfolioDeepDive onClose={closeModal} />}
      {activeModal === 'suggested-trades' && <SuggestedTrades onClose={closeModal} />}
      {activeModal === 'strategy-tracking' && <StrategyTracking onClose={closeModal} />}
      {activeModal === 'risk' && <Risk onClose={closeModal} />}
      {activeModal === 'derivative-usage' && <DerivativeUsage onClose={closeModal} />}
    </div>
  )
}
