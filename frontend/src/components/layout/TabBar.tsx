import type { TabId } from '../../types'

interface Tab {
  id: TabId
  label: string
  star?: boolean
  order: number
}

const TABS: Tab[] = [
  { id: 'portfolio-deep-dive', label: 'Portfolio Deep-Dive', order: 1 },
  { id: 'suggested-trades', label: 'Suggested Trades', star: true, order: 2 },
  { id: 'strategy-tracking', label: 'Strategy Tracking', order: 3 },
  { id: 'risk', label: 'Risk', order: 4 },
  { id: 'derivative-usage', label: 'Derivative Usage', order: 5 },
  { id: 'bond-detail', label: 'Bond Detail', order: 6 },
]

interface Props {
  onTabClick: (id: TabId) => void
}

export default function TabBar({ onTabClick }: Props) {
  return (
    <nav className="flex items-center justify-center gap-2 px-4 py-2.5 bg-surface-1 border-b border-border">
      {TABS.map(tab => (
        <button
          key={tab.id}
          onClick={() => onTabClick(tab.id)}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium text-text-muted
            border border-border hover:border-amber-500/60 hover:text-amber-400 hover:bg-amber-500/5
            transition-all duration-150 active:scale-95"
        >
          {tab.star && <span className="text-amber-400 text-xs">★</span>}
          {tab.label}
        </button>
      ))}
    </nav>
  )
}
