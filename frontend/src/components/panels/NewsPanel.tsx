import { useEffect, useState } from 'react'
import { stubNews } from '../../data/stubs'
import type { NewsItem } from '../../types'

interface Props {
  date: string
}

const SENTIMENT_STYLES = {
  positive: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  negative: 'bg-red-500/10 text-red-400 border-red-500/20',
  neutral:  'bg-surface-3/50 text-text-muted border-border-strong/30',
}

const SENTIMENT_ICONS = { positive: '▲', negative: '▼', neutral: '●' }

export default function NewsPanel({ date }: Props) {
  const [news, setNews]       = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [live, setLive]       = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetch(`/api/news?date=${date}`)
      .then(r => r.json())
      .then((items: NewsItem[]) => {
        if (cancelled) return
        if (items && items.length > 0) {
          setNews(items)
          setLive(true)
        } else {
          setNews(stubNews.map(n => ({ ...n, date })))
          setLive(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNews(stubNews.map(n => ({ ...n, date })))
          setLive(false)
        }
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [date])

  return (
    <div className="bg-surface-1 rounded-2xl border border-border p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-text-primary font-semibold text-sm">Market News</h2>
          <p className="text-text-muted text-xs mt-0.5">{date}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-amber-400 text-xs border border-amber-500/20 px-2 py-0.5 rounded-full bg-amber-500/5">
            {news.length} items
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full border ${live
            ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
            : 'text-text-muted border-border bg-surface-2'}`}>
            {live ? '● Alpaca' : '○ Stub'}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-text-muted text-sm animate-pulse">Fetching news…</span>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2 pr-1 min-h-0">
          {news.map((item, i) => (
            <div
              key={i}
              className="p-3 bg-surface-2/50 rounded-xl border border-border/50 hover:border-border-strong transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <span className={`text-xs px-1.5 py-0.5 rounded-lg border font-medium flex-shrink-0 ${SENTIMENT_STYLES[item.sentiment]}`}>
                  {SENTIMENT_ICONS[item.sentiment]} {item.sentiment}
                </span>
                <span className="text-text-muted text-xs flex-shrink-0">{item.source}</span>
              </div>
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary text-xs leading-relaxed hover:text-amber-400 transition-colors"
                >
                  {item.headline}
                </a>
              ) : (
                <p className="text-text-secondary text-xs leading-relaxed">{item.headline}</p>
              )}
              <div className="flex items-center justify-between mt-1.5">
                <span className="text-text-muted text-xs">{item.issuer}</span>
                <span className="text-text-muted text-xs font-mono">{item.date}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
