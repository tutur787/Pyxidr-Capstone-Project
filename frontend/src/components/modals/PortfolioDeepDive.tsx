import Modal from './Modal'

interface Props { onClose: () => void }

const SKELETON_ROWS = 8
const COLS = ['CUSIP', 'Issuer', 'Coupon', 'Maturity', 'Weight', 'Spread (bps)', 'Duration', 'Rating']

export default function PortfolioDeepDive({ onClose }: Props) {
  return (
    <Modal title="Portfolio Deep-Dive" subtitle="Full bond-level breakdown of the optimized portfolio" onClose={onClose}>
      <div className="space-y-6">
        {/* summary strip */}
        <div className="grid grid-cols-4 gap-3">
          {['Total Bonds', 'Avg Duration', 'Avg Spread', 'Avg Rating'].map((label, i) => (
            <div key={label} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-gray-500 text-xs mb-1">{label}</p>
              <div className="h-5 w-16 bg-gray-700 rounded animate-pulse" />
            </div>
          ))}
        </div>

        {/* bond table skeleton */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Bond Universe</h3>
          <div className="overflow-x-auto rounded-xl border border-gray-700">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-800 border-b border-gray-700">
                  {COLS.map(c => (
                    <th key={c} className="px-4 py-2.5 text-left text-gray-400 font-medium whitespace-nowrap">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/40">
                    {COLS.map(c => (
                      <td key={c} className="px-4 py-3">
                        <div className={`h-3 bg-gray-700/60 rounded animate-pulse`} style={{ width: `${50 + (i * 7 + c.length * 3) % 40}%` }} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-gray-600 text-xs mt-2 text-center">Bond-level data will populate from the backend optimization output.</p>
        </div>

        {/* weight distribution placeholder */}
        <div>
          <h3 className="text-white font-medium text-sm mb-3">Weight Distribution by Sector</h3>
          <div className="h-40 bg-gray-800 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
            <p className="text-gray-600 text-sm">Chart placeholder — sector allocation bar chart</p>
          </div>
        </div>
      </div>
    </Modal>
  )
}
