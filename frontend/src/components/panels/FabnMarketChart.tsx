import {
  ComposedChart, Line, Area, ReferenceLine,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import type { FabnMarketPoint } from '../../types'

interface Props {
  data: FabnMarketPoint[]
  creditingRate?: number   // FABN's fixed crediting rate, in % (e.g. 3.205)
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const prime   = payload.find((p: any) => p.dataKey === 'prime_rate')
  const fabn    = payload.find((p: any) => p.dataKey === 'fabn_ytm')
  const treas   = payload.find((p: any) => p.dataKey === 'treasury_ytm')
  const spread  = payload.find((p: any) => p.dataKey === 'spread_bps')
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-3 text-xs shadow-xl min-w-[170px]">
      <p className="text-gray-400 font-medium mb-2">{label}</p>
      {prime  && <p className="text-gray-400 mb-0.5">Prime Rate <span className="font-mono float-right">{prime.value.toFixed(2)}%</span></p>}
      {fabn   && <p className="text-amber-400 mb-0.5">FABN YTM <span className="font-mono float-right">{fabn.value.toFixed(2)}%</span></p>}
      {treas  && <p className="text-blue-400 mb-0.5">Treasury YTM <span className="font-mono float-right">{treas.value.toFixed(2)}%</span></p>}
      {spread && <p className="text-emerald-400 font-semibold">Spread <span className="font-mono float-right">{spread.value.toFixed(0)} bps</span></p>}
    </div>
  )
}

export default function FabnMarketChart({ data, creditingRate }: Props) {
  if (data.length === 0) {
    return (
      <div className="h-52 bg-gray-800/40 rounded-xl border border-gray-700 border-dashed flex items-center justify-center">
        <p className="text-gray-600 text-sm">Loading FABN market history…</p>
      </div>
    )
  }

  return (
    <div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#1f2937" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickFormatter={(d: string) => d.slice(0, 4)}
              interval="preserveStartEnd"
              minTickGap={80}
            />
            <YAxis
              yAxisId="left"
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              width={44}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fill: '#6b7280', fontSize: 10 }}
              tickFormatter={(v: number) => `${v.toFixed(0)}`}
              width={40}
            />
            <Tooltip content={<ChartTooltip />} />

            {creditingRate !== undefined && (
              <ReferenceLine
                yAxisId="left"
                y={creditingRate}
                stroke="#a855f7"
                strokeDasharray="3 3"
                strokeWidth={1.5}
                label={{ value: `Crediting ${creditingRate.toFixed(3)}%`, fill: '#a855f7', fontSize: 9, position: 'insideBottomRight' }}
              />
            )}

            <Area
              yAxisId="right"
              type="monotone"
              dataKey="spread_bps"
              stroke="none"
              fill="#10b981"
              fillOpacity={0.12}
            />
            <Line
              yAxisId="left"
              type="stepAfter"
              dataKey="prime_rate"
              stroke="#6b7280"
              strokeWidth={1.5}
              dot={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="treasury_ytm"
              stroke="#3b82f6"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="fabn_ytm"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-4 justify-center mt-1.5 text-xs text-gray-500 flex-wrap">
        <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-gray-500" />Prime Rate</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-amber-400" />FABN YTM</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-blue-400 border-dashed" />Treasury YTM</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500/40" />Spread (bps)</span>
        {creditingRate !== undefined && (
          <span className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-purple-400 border-dashed" />FABN Crediting Rate</span>
        )}
      </div>
    </div>
  )
}
