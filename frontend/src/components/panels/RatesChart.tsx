import { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from 'recharts'
import { generateStubRates } from '../../data/stubs'

interface Props {
  date: string
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-gray-400 mb-1.5 font-mono">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }} className="font-mono">
          {p.name}: {p.value.toFixed(3)}%
        </p>
      ))}
    </div>
  )
}

export default function RatesChart({ date }: Props) {
  const data = useMemo(() => generateStubRates(date, 90), [date])

  const thinned = data.filter((_, i) => i % 3 === 0)

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-white font-semibold text-sm">Treasury Rates</h2>
          <p className="text-gray-500 text-xs mt-0.5">90-day trailing window</p>
        </div>
        <div className="flex gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-red-400">
            <span className="w-3 h-0.5 bg-red-400 rounded inline-block" />2Y
          </span>
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-3 h-0.5 bg-emerald-400 rounded inline-block" />10Y
          </span>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={thinned} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => v.slice(5)}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `${v}%`}
              domain={['auto', 'auto']}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="rate_2y"
              name="2Y"
              stroke="#f87171"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: '#f87171' }}
            />
            <Line
              type="monotone"
              dataKey="rate_10y"
              name="10Y"
              stroke="#34d399"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: '#34d399' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
