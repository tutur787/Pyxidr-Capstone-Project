import Modal from './Modal'

interface Props { onClose: () => void }

const STUB_TRADES = [
  { action: 'BUY', issuer: 'MetLife Inc.', cusip: '59156RBH4', weight: '+2.3%', spread: '85 bps', reason: 'Strong momentum signal, under-weight vs. benchmark' },
  { action: 'SELL', issuer: 'JPMorgan Chase', cusip: '46647PAP3', weight: '-1.8%', spread: '42 bps', reason: 'Spread compression, rebalance duration exposure' },
  { action: 'BUY', issuer: 'Prudential Financial', cusip: '74432QBF8', weight: '+1.5%', spread: '78 bps', reason: 'Positive sentiment, high carry relative to C1 factor' },
  { action: 'HOLD', issuer: 'Royal Bank of Canada', cusip: '78012KYT3', weight: '—', spread: '61 bps', reason: 'Optimal weight per CVaR optimizer output' },
]

export default function SuggestedTrades({ onClose }: Props) {
  return (
    <Modal title="Suggested Trades" subtitle="Optimization-driven rebalancing recommendations" onClose={onClose}>
      <div className="space-y-4">
        <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-xl">
          <p className="text-amber-400 text-xs font-medium">★ Priority rebalancing — CVaR budget at 62% utilization</p>
          <p className="text-gray-400 text-xs mt-1">These are placeholder trades. Connect the optimizer to populate real signals.</p>
        </div>

        <div className="space-y-3">
          {STUB_TRADES.map((trade, i) => (
            <div key={i} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex items-start gap-4">
              <span className={`flex-shrink-0 px-2.5 py-1 rounded-lg text-xs font-semibold mt-0.5
                ${trade.action === 'BUY' ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' :
                  trade.action === 'SELL' ? 'bg-red-500/15 text-red-400 border border-red-500/20' :
                  'bg-gray-700 text-gray-400 border border-gray-600'}`}>
                {trade.action}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-white text-sm font-medium truncate">{trade.issuer}</p>
                  <span className="text-gray-500 font-mono text-xs flex-shrink-0">{trade.cusip}</span>
                </div>
                <p className="text-gray-400 text-xs mt-1">{trade.reason}</p>
                <div className="flex gap-4 mt-2">
                  <span className="text-gray-500 text-xs">Δ Weight: <span className="text-amber-400 font-mono">{trade.weight}</span></span>
                  <span className="text-gray-500 text-xs">Spread: <span className="text-gray-300 font-mono">{trade.spread}</span></span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="h-40 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center mt-4">
          <p className="text-gray-600 text-sm">Trade impact chart — pre/post optimization comparison</p>
        </div>
      </div>
    </Modal>
  )
}
