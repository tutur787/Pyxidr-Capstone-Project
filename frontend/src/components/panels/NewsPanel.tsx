import { stubNews } from '../../data/stubs'

interface Props {
  date: string
}

const SENTIMENT_STYLES = {
  positive: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  negative: 'bg-red-500/10 text-red-400 border-red-500/20',
  neutral: 'bg-gray-700/50 text-gray-400 border-gray-600/30',
}

const SENTIMENT_ICONS = {
  positive: '▲',
  negative: '▼',
  neutral: '●',
}

export default function NewsPanel({ date }: Props) {
  const news = stubNews.map(n => ({ ...n, date }))

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-white font-semibold text-sm">Market News</h2>
          <p className="text-gray-500 text-xs mt-0.5">Simulated at {date}</p>
        </div>
        <span className="text-amber-400 text-xs border border-amber-500/20 px-2 py-0.5 rounded-full bg-amber-500/5">
          {news.length} items
        </span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1 min-h-0">
        {news.map((item, i) => (
          <div
            key={i}
            className="p-3 bg-gray-800/50 rounded-lg border border-gray-700/50 hover:border-gray-600 transition-colors cursor-default"
          >
            <div className="flex items-start justify-between gap-2 mb-1.5">
              <span className={`text-xs px-1.5 py-0.5 rounded border font-medium flex-shrink-0 ${SENTIMENT_STYLES[item.sentiment]}`}>
                {SENTIMENT_ICONS[item.sentiment]} {item.sentiment}
              </span>
              <span className="text-gray-600 text-xs flex-shrink-0">{item.source}</span>
            </div>
            <p className="text-gray-300 text-xs leading-relaxed">{item.headline}</p>
            <div className="flex items-center justify-between mt-1.5">
              <span className="text-gray-600 text-xs">{item.issuer}</span>
              <span className={`text-xs font-mono font-medium ${item.score >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {item.score >= 0 ? '+' : ''}{item.score.toFixed(2)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
