import Modal from './Modal'

interface Props { onClose: () => void }

export default function DerivativeUsage({ onClose }: Props) {
  return (
    <Modal title="Derivative Usage" subtitle="Hedging instruments and overlay strategies" onClose={onClose}>
      <div className="space-y-5">
        <div className="p-4 bg-gray-800 rounded-xl border border-gray-700">
          <p className="text-gray-400 text-sm leading-relaxed">
            This section will display derivative overlay positions used to hedge interest rate and credit risk exposure
            within the FABN portfolio. Expected instruments include interest rate swaps (duration hedges),
            credit default swaps (CDS), and Treasury futures.
          </p>
        </div>

        {/* placeholder metrics */}
        <div className="grid grid-cols-3 gap-3">
          {['IR Swap DV01', 'CDS Notional', 'Futures Delta'].map(label => (
            <div key={label} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-gray-500 text-xs mb-2">{label}</p>
              <div className="h-5 w-20 bg-gray-700 rounded animate-pulse" />
              <div className="h-3 w-12 bg-gray-700/50 rounded animate-pulse mt-1.5" />
            </div>
          ))}
        </div>

        {/* positions table skeleton */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Open Derivative Positions</h3>
          <div className="overflow-x-auto rounded-xl border border-gray-700">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-800 border-b border-gray-700">
                  {['Instrument', 'Type', 'Notional', 'Maturity', 'Mark-to-Market'].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-gray-400 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i} className="border-b border-gray-800">
                    {Array.from({ length: 5 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-3 bg-gray-700/50 rounded animate-pulse" style={{ width: `${40 + (i + j) * 9 % 45}%` }} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-gray-600 text-xs mt-2 text-center">Derivative positions will populate once hedging strategies are configured.</p>
        </div>

        <div>
          <h3 className="text-white font-medium text-sm mb-3">Hedge Effectiveness</h3>
          <div className="h-40 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
            <p className="text-gray-600 text-sm">Duration gap pre/post hedge — time series chart</p>
          </div>
        </div>
      </div>
    </Modal>
  )
}
