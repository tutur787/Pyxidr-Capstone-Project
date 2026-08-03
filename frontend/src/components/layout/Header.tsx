import { useState, useRef, useEffect } from 'react'
import HyperparamSidebar from '../sidebar/HyperparamSidebar'
import SettingsModal from '../modals/SettingsModal'
import type { HyperParams, Fabn } from '../../types'
import { DATE_MIN, DATE_MAX } from '../../data/stubs'

interface Props {
  date: string
  formattedDate: string
  onAdvance: (delta: number) => void
  onJumpToDate: (iso: string) => void
  isAtMin: boolean
  isAtMax: boolean
  hyperParams: HyperParams
  onHyperParamsChange: (p: HyperParams) => void
  fabns: Fabn[]
  selectedFabns: Fabn[]
  onFabnChange: (fabns: Fabn[]) => void
  onApply: () => void
}

// ── Lightweight inline calendar popover ───────────────────────────────────────
const DAY_LABELS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

function CalendarPopover({
  date,
  onSelect,
}: {
  date: string
  onSelect: (iso: string) => void
}) {
  const [calMonth, setCalMonth] = useState(date.slice(0, 7)) // YYYY-MM

  // Keep calendar in sync when the date is changed externally via arrows
  useEffect(() => { setCalMonth(date.slice(0, 7)) }, [date])

  const [yearStr, monthStr] = calMonth.split('-')
  const year  = Number(yearStr)
  const month = Number(monthStr) // 1-indexed

  function shiftMonth(delta: number) {
    const d = new Date(year, month - 1 + delta, 1)
    setCalMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }

  const monthLabel = new Date(year, month - 1).toLocaleDateString('en-US', {
    month: 'long', year: 'numeric',
  })

  const firstWeekday = new Date(year, month - 1, 1).getDay()
  const daysInMonth  = new Date(year, month, 0).getDate()

  // Can we navigate to prev/next month? Only if any day there is within bounds.
  const prevMonthFirstISO = `${new Date(year, month - 2, 1).getFullYear()}-${String(new Date(year, month - 2, 1).getMonth() + 1).padStart(2, '0')}-01`
  const nextMonthLastISO  = (() => {
    const d = new Date(year, month + 1, 0) // last day of next month
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })()

  return (
    <div className="glass absolute top-full mt-2 left-1/2 -translate-x-1/2 border border-border rounded-2xl shadow-2xl p-3 z-[200] w-72">
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => shiftMonth(-1)}
          disabled={prevMonthFirstISO < DATE_MIN.slice(0, 8) + '01' && `${year}-${String(month).padStart(2,'0')}` <= DATE_MIN.slice(0, 7)}
          className="text-text-muted hover:text-brand disabled:opacity-30 disabled:cursor-not-allowed p-1 rounded-full hover:bg-surface-2 transition-colors text-sm font-bold"
        >
          ←
        </button>
        <span className="text-text-primary text-sm font-mono font-medium">{monthLabel}</span>
        <button
          onClick={() => shiftMonth(1)}
          disabled={nextMonthLastISO > DATE_MAX}
          className="text-text-muted hover:text-brand disabled:opacity-30 disabled:cursor-not-allowed p-1 rounded-full hover:bg-surface-2 transition-colors text-sm font-bold"
        >
          →
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="grid grid-cols-7 mb-1">
        {DAY_LABELS.map(d => (
          <div key={d} className="text-text-muted text-xs text-center py-0.5">{d}</div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-y-0.5">
        {/* Empty offset cells */}
        {Array.from({ length: firstWeekday }).map((_, i) => (
          <div key={`empty-${i}`} />
        ))}

        {/* Day cells */}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const day = i + 1
          const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
          const isSelected = iso === date
          const isDisabled = iso < DATE_MIN || iso > DATE_MAX
          return (
            <button
              key={day}
              disabled={isDisabled}
              onClick={() => onSelect(iso)}
              className={`text-xs rounded-full py-1.5 w-full text-center transition-colors
                ${isSelected
                  ? 'bg-brand text-white font-bold'
                  : isDisabled
                    ? 'text-text-muted opacity-40 cursor-not-allowed'
                    : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'}`}
            >
              {day}
            </button>
          )
        })}
      </div>

      <p className="text-text-muted text-xs text-center mt-3">
        Range: {DATE_MIN} → {DATE_MAX}
      </p>
    </div>
  )
}

export default function Header({
  date, formattedDate, onAdvance, onJumpToDate, isAtMin, isAtMax,
  hyperParams, onHyperParamsChange,
  fabns, selectedFabns, onFabnChange,
  onApply,
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [fabnOpen, setFabnOpen] = useState(false)
  const [showCalendar, setShowCalendar] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  // Click-outside for FABN dropdown
  const fabnRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!fabnOpen) return
    function handleClick(e: MouseEvent) {
      if (fabnRef.current && !fabnRef.current.contains(e.target as Node)) {
        setFabnOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [fabnOpen])

  // Click-outside for profile dropdown
  const profileRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!profileOpen) return
    function handleClick(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [profileOpen])

  // Click-outside for calendar
  const calendarRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!showCalendar) return
    function handleClick(e: MouseEvent) {
      if (calendarRef.current && !calendarRef.current.contains(e.target as Node)) {
        setShowCalendar(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showCalendar])

  function toggleFabn(f: Fabn) {
    const already = selectedFabns.some(s => s.cusip === f.cusip)
    onFabnChange(already ? selectedFabns.filter(s => s.cusip !== f.cusip) : [...selectedFabns, f])
  }

  const fabnLabel =
    selectedFabns.length === 0 ? 'Select FABN…' :
    selectedFabns.length === 1 ? `FABN · ${selectedFabns[0].cusip}` :
    `${selectedFabns.length} FABNs selected`

  const fabnSub =
    selectedFabns.length === 1
      ? `${selectedFabns[0].maturity?.slice(0, 7) ?? ''}${selectedFabns[0].rating ? ` · ${selectedFabns[0].rating}` : ''}`
      : selectedFabns.length > 1
        ? selectedFabns.map(f => f.cusip).join(', ')
        : ''

  return (
    <>
      <header className="glass flex items-center justify-between px-4 py-3 border-b border-border z-30 relative">
        {/* Left: burger + FABN selector */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="flex flex-col gap-1.5 p-2 rounded-full hover:bg-surface-2 transition-colors group"
            aria-label="Open parameters"
          >
            <span className="block w-5 h-0.5 bg-text-muted group-hover:bg-brand transition-colors" />
            <span className="block w-5 h-0.5 bg-text-muted group-hover:bg-brand transition-colors" />
            <span className="block w-5 h-0.5 bg-text-muted group-hover:bg-brand transition-colors" />
          </button>

          {/* FABN selector */}
          <div className="relative" ref={fabnRef}>
            <button
              onClick={() => setFabnOpen(o => !o)}
              className="flex items-center gap-2 px-2 py-1.5 rounded-xl hover:bg-surface-2 transition-colors group"
              aria-label="Select FABN"
            >
              <span className="text-brand text-lg group-hover:text-brand-hover transition-colors">▦</span>
              <div className="text-left hidden sm:block max-w-[260px]">
                <p className="text-text-primary font-semibold text-sm leading-none font-mono truncate">{fabnLabel}</p>
                {fabnSub && (
                  <p className="text-text-muted text-xs mt-0.5 font-mono truncate">{fabnSub}</p>
                )}
              </div>
              <span className="text-text-muted text-xs ml-1">▾</span>
            </button>

            {fabnOpen && (
              <div className="glass absolute left-0 top-full mt-2 w-80 border border-border rounded-2xl shadow-2xl py-2 z-[200] max-h-72 overflow-y-auto">
                <div className="px-4 py-1.5 border-b border-border mb-1 flex items-center justify-between">
                  <p className="text-text-muted text-xs font-semibold uppercase tracking-wider">Select FABNs</p>
                  {selectedFabns.length > 0 && (
                    <button
                      onClick={() => onFabnChange([])}
                      className="text-text-muted hover:text-text-secondary text-xs transition-colors"
                    >
                      Clear all
                    </button>
                  )}
                </div>
                {fabns.map(f => {
                  const checked   = selectedFabns.some(s => s.cusip === f.cusip)
                  const comingSoon = f.status === 'coming_soon'
                  return (
                    <button
                      key={f.cusip}
                      onClick={() => !comingSoon && toggleFabn(f)}
                      disabled={comingSoon}
                      className={`w-full text-left px-4 py-2.5 transition-colors flex items-start gap-3
                        ${comingSoon ? 'opacity-50 cursor-not-allowed' : 'hover:bg-surface-2'}
                        ${checked ? 'bg-brand/10' : ''}`}
                    >
                      {comingSoon ? (
                        <div className="mt-0.5 w-4 h-4 flex-shrink-0" />
                      ) : (
                        <div className={`mt-0.5 w-4 h-4 rounded-full flex-shrink-0 border flex items-center justify-center
                          ${checked ? 'bg-brand border-brand' : 'border-border-strong'}`}>
                          {checked && <span className="text-white text-xs font-bold leading-none">✓</span>}
                        </div>
                      )}
                      <div className="flex-1 min-w-0 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className={`font-mono text-sm font-semibold ${checked ? 'text-brand' : 'text-text-primary'}`}>
                            {f.cusip}
                          </p>
                          <p className="text-text-muted text-xs mt-0.5 truncate">{f.sector}</p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          {comingSoon ? (
                            <span className="text-text-muted text-xs px-2 py-0.5 rounded-full border border-border">Coming soon</span>
                          ) : (
                            <>
                              <p className="text-text-secondary text-xs">{f.maturity ? f.maturity.slice(0, 10) : ''}</p>
                              <p className="text-text-muted text-xs mt-0.5">
                                {f.rating}{f.coupon != null ? ` · ${(f.coupon * 100).toFixed(2)}%` : ''}
                              </p>
                            </>
                          )}
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Center: date navigator + calendar popover */}
        <div className="relative" ref={calendarRef}>
          <div className="flex items-center gap-2 bg-surface-1 rounded-2xl px-4 py-2 border border-border">
            {/* One-day back */}
            <button
              onClick={() => onAdvance(-1)}
              disabled={isAtMin}
              className="text-text-muted hover:text-brand disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm font-bold w-6 h-6 flex items-center justify-center rounded-full hover:bg-surface-2"
            >
              ←
            </button>

            {/* Calendar toggle — clicking the emoji or date text opens the picker */}
            <button
              onClick={() => setShowCalendar(v => !v)}
              className="flex items-center gap-2 min-w-[140px] justify-center rounded-full px-1 py-0.5 hover:bg-surface-2 transition-colors"
              title="Click to open calendar"
            >
              <span className={`text-xs transition-colors ${showCalendar ? 'text-brand-hover' : 'text-brand'}`}>📅</span>
              <span className="text-text-primary font-mono text-sm font-medium">{formattedDate}</span>
            </button>

            {/* One-day forward */}
            <button
              onClick={() => onAdvance(1)}
              disabled={isAtMax}
              className="text-text-muted hover:text-brand disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm font-bold w-6 h-6 flex items-center justify-center rounded-full hover:bg-surface-2"
            >
              →
            </button>
          </div>

          {showCalendar && (
            <CalendarPopover
              date={date}
              onSelect={iso => { onJumpToDate(iso); setShowCalendar(false) }}
            />
          )}
        </div>

        {/* Right: menu */}
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => setProfileOpen(p => !p)}
            className="flex items-center gap-2 px-3 py-2 rounded-2xl hover:bg-surface-2 transition-colors border border-transparent hover:border-border"
            aria-label="Open menu"
          >
            <div className="w-8 h-8 rounded-full bg-brand flex items-center justify-center text-white font-bold text-sm">
              ⚙
            </div>
            <span className="text-text-muted text-xs ml-1">▾</span>
          </button>

          {profileOpen && (
            <div className="glass absolute right-0 top-full mt-2 w-52 border border-border rounded-2xl shadow-2xl py-2 z-[200]">
              <div className="px-4 py-2 border-b border-border">
                <p className="text-text-muted text-xs">Simulated date</p>
                <p className="text-brand text-xs font-mono">{date}</p>
              </div>
              <div className="px-2 pt-1">
                <button
                  onClick={() => { setSettingsOpen(true); setProfileOpen(false) }}
                  className="w-full text-left px-2 py-1.5 text-text-secondary hover:text-text-primary hover:bg-surface-2 rounded-xl text-sm transition-colors"
                >
                  Settings
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      <HyperparamSidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        params={hyperParams}
        onChange={onHyperParamsChange}
        onApply={onApply}
      />

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </>
  )
}
