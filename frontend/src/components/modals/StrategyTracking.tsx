import Modal from './Modal'

interface Props { onClose: () => void }

const STRATEGIES = [
  { name: 'Spread Carry', status: 'Active', signal: 'Positive', return: '+1.52%', sharpe: '1.34' },
  { name: 'Return Momentum (21d)', status: 'Active', signal: 'Strong', return: '+0.84%', sharpe: '1.71' },
  { name: 'Spread Momentum (21d)', status: 'Inactive', signal: 'Mean Revert', return: '-0.12%', sharpe: '0.23' },
  { name: 'CVaR Optimization', status: 'Active', signal: 'Optimal', return: '+1.21%', sharpe: '1.58' },
  { name: 'Duration Matching (C3)', status: 'Active', signal: 'Compliant', return: '—', sharpe: '—' },
]

export default function StrategyTracking({ onClose }: Props) {
  return (
    <Modal title="Strategy Tracking" subtitle="Performance attribution across portfolio strategies" onClose={onClose}>
      <div className="space-y-5">
        <div className="overflow-x-auto rounded-xl border border-gray-700">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-800 border-b border-gray-700">
                {['Strategy', 'Status', 'Signal', 'Return', 'Sharpe'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-gray-400 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {STRATEGIES.map((s, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                  <td className="px-4 py-3 text-white font-medium">{s.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium
                      ${s.status === 'Active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gray-700 text-gray-500'}`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-300">{s.signal}</td>
                  <td className={`px-4 py-3 font-mono font-medium ${s.return.startsWith('+') ? 'text-emerald-400' : s.return.startsWith('-') ? 'text-red-400' : 'text-gray-500'}`}>{s.return}</td>
                  <td className="px-4 py-3 font-mono text-gray-300">{s.sharpe}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h3 className="text-white font-medium text-sm mb-3">Cumulative Return by Strategy</h3>
          <div className="h-48 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
            <p className="text-gray-600 text-sm">Strategy performance chart — time-series comparison</p>
          </div>
        </div>

        <div>
          <h3 className="text-white font-medium text-sm mb-3">Quintile Return Analysis</h3>
          <div className="h-36 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
            <p className="text-gray-600 text-sm">Q1–Q5 forward return bar chart (momentum signal)</p>
          </div>
        </div>
      </div>
    </Modal>
  )
}
