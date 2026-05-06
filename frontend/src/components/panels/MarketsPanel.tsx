import { useEffect, useState } from 'react'

interface Quote {
  symbol: string
  name: string
  price: number
  change: number
  change_pct: number
  direction: 'up' | 'down'
  date?: string
}

interface Props {
  date: string
}

const STUBS: Quote[] = [
  { symbol: 'SPY',  name: 'S&P 500 ETF',   price: 478.32, change:  2.14, change_pct:  0.45, direction: 'up'   },
  { symbol: 'AAPL', name: 'Apple Inc.',     price: 182.63, change: -0.87, change_pct: -0.47, direction: 'down' },
  { symbol: 'MSFT', name: 'Microsoft',      price: 374.51, change:  1.92, change_pct:  0.52, direction: 'up'   },
  { symbol: 'NVDA', name: 'NVIDIA',         price: 621.44, change:  8.33, change_pct:  1.36, direction: 'up'   },
  { symbol: 'JPM',  name: 'JPMorgan Chase', price: 196.87, change: -1.23, change_pct: -0.62, direction: 'down' },
]

function TickerRow({ q, live }: { q: Quote; live: boolean }) {
  const up  = q.direction === 'up'
  const clr = up ? 'text-emerald-400' : 'text-red-400'
  const bg  = up ? 'bg-emerald-500/8' : 'bg-red-500/8'
  const border = up ? 'border-emerald-500/15' : 'border-red-500/15'

  return (
    <div className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${border} ${bg} hover:brightness-110 transition-all`}>
      {/* Left: symbol + name */}
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-white font-mono font-bold text-sm w-12 flex-shrink-0">{q.symbol}</span>
        <span className="text-gray-500 text-xs truncate hidden sm:block">{q.name}</span>
      </div>

      {/* Right: price + change */}
      <div className="flex items-center gap-4 flex-shrink-0">
        <span className="text-white font-mono font-semibold text-sm tabular-nums">
          ${q.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <div className={`flex items-center gap-1 min-w-[90px] justify-end ${clr}`}>
          <span className="text-xs font-bold">{up ? '▲' : '▼'}</span>
          <span className="font-mono text-xs tabular-nums">
            {up ? '+' : ''}{q.change.toFixed(2)}
          </span>
          <span className="font-mono text-xs tabular-nums opacity-80">
            ({up ? '+' : ''}{q.change_pct.toFixed(2)}%)
          </span>
        </div>
      </div>
    </div>
  )
}

export default function MarketsPanel({ date }: Props) {
  const [quotes, setQuotes]   = useState<Quote[]>(STUBS)
  const [loading, setLoading] = useState(true)
  const [live, setLive]       = useState(false)
  const [asOf, setAsOf]       = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch(`/api/markets?date=${date}`)
      .then(r => r.json())
      .then((data: Quote[]) => {
        if (cancelled) return
        if (data && data.length > 0) {
          setQuotes(data)
          setLive(true)
          setAsOf(data[0]?.date ?? date)
        } else {
          setQuotes(STUBS)
          setLive(false)
          setAsOf(date)
        }
      })
      .catch(() => {
        if (!cancelled) { setQuotes(STUBS); setLive(false); setAsOf(date) }
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [date])

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-white font-semibold text-sm">Markets</h2>
          <p className="text-gray-500 text-xs mt-0.5">{live ? `As of ${asOf}` : `Sim date ${date}`}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${live
          ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
          : 'text-gray-500 border-gray-700 bg-gray-800'}`}>
          {live ? '● Alpaca' : '○ Stub'}
        </span>
      </div>

      {/* Column labels */}
      <div className="flex items-center justify-between px-3 mb-1.5">
        <span className="text-gray-600 text-xs">Symbol</span>
        <div className="flex gap-4">
          <span className="text-gray-600 text-xs">Price</span>
          <span className="text-gray-600 text-xs min-w-[90px] text-right">Change</span>
        </div>
      </div>

      {/* Tickers */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-gray-600 text-sm animate-pulse">Fetching quotes…</span>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5 flex-1">
          {quotes.map(q => <TickerRow key={q.symbol} q={q} live={live} />)}
        </div>
      )}
    </div>
  )
}
