import Modal from './Modal'

interface Props { onClose: () => void }

const RISK_METRICS = [
  { label: 'CVaR (75%)', value: '2.87%', status: 'Within budget', ok: true },
  { label: 'VaR (95%)', value: '1.94%', status: 'Normal range', ok: true },
  { label: 'Duration Gap', value: '0.12 yrs', status: 'Compliant (C3)', ok: true },
  { label: 'RBC C1 Usage', value: '62%', status: 'Below 80% threshold', ok: true },
  { label: 'BBB+ Allocation', value: '34%', status: 'Below 40% cap', ok: true },
  { label: 'Financials Sector', value: '41%', status: 'At sector cap', ok: false },
]

export default function Risk({ onClose }: Props) {
  return (
    <Modal title="Risk" subtitle="CVaR, RBC constraints, and concentration limits" onClose={onClose}>
      <div className="space-y-5">
        {/* constraint status grid */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Constraint Status</h3>
          <div className="grid grid-cols-2 gap-3">
            {RISK_METRICS.map((m, i) => (
              <div key={i} className={`p-4 rounded-xl border ${m.ok ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-amber-500/5 border-amber-500/20'}`}>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-gray-400 text-xs">{m.label}</p>
                  <span className={`text-xs ${m.ok ? 'text-emerald-400' : 'text-amber-400'}`}>{m.ok ? '✓' : '⚠'}</span>
                </div>
                <p className={`font-mono font-semibold text-lg ${m.ok ? 'text-emerald-400' : 'text-amber-400'}`}>{m.value}</p>
                <p className={`text-xs mt-0.5 ${m.ok ? 'text-emerald-500/70' : 'text-amber-500/70'}`}>{m.status}</p>
              </div>
            ))}
          </div>
        </div>

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
