import { useState, useRef, useEffect } from 'react'
import HyperparamSidebar from '../sidebar/HyperparamSidebar'
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
    <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl p-3 z-[200] w-72">
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => shiftMonth(-1)}
          disabled={prevMonthFirstISO < DATE_MIN.slice(0, 8) + '01' && `${year}-${String(month).padStart(2,'0')}` <= DATE_MIN.slice(0, 7)}
          className="text-gray-400 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed p-1 rounded hover:bg-gray-700 transition-colors text-sm font-bold"
        >
          ←
        </button>
        <span className="text-white text-sm font-mono font-medium">{monthLabel}</span>
        <button
          onClick={() => shiftMonth(1)}
          disabled={nextMonthLastISO > DATE_MAX}
          className="text-gray-400 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed p-1 rounded hover:bg-gray-700 transition-colors text-sm font-bold"
        >
          →
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="grid grid-cols-7 mb-1">
        {DAY_LABELS.map(d => (
          <div key={d} className="text-gray-600 text-xs text-center py-0.5">{d}</div>
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
              className={`text-xs rounded py-1.5 w-full text-center transition-colors
                ${isSelected
                  ? 'bg-amber-500 text-gray-900 font-bold'
                  : isDisabled
                    ? 'text-gray-700 cursor-not-allowed'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'}`}
            >
              {day}
            </button>
          )
        })}
      </div>

      <p className="text-gray-600 text-xs text-center mt-3">
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
      <header className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-800 z-30 relative">
        {/* Left: burger + FABN selector */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="flex flex-col gap-1.5 p-2 rounded-lg hover:bg-gray-800 transition-colors group"
            aria-label="Open parameters"
          >
            <span className="block w-5 h-0.5 bg-gray-400 group-hover:bg-amber-400 transition-colors" />
            <span className="block w-5 h-0.5 bg-gray-400 group-hover:bg-amber-400 transition-colors" />
            <span className="block w-5 h-0.5 bg-gray-400 group-hover:bg-amber-400 transition-colors" />
          </button>

          {/* FABN selector */}
          <div className="relative" ref={fabnRef}>
            <button
              onClick={() => setFabnOpen(o => !o)}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-800 transition-colors group"
              aria-label="Select FABN"
            >
              <span className="text-amber-400 text-lg group-hover:text-amber-300 transition-colors">▦</span>
              <div className="text-left hidden sm:block max-w-[260px]">
                <p className="text-white font-semibold text-sm leading-none font-mono truncate">{fabnLabel}</p>
                {fabnSub && (
                  <p className="text-gray-500 text-xs mt-0.5 font-mono truncate">{fabnSub}</p>
                )}
              </div>
              <span className="text-gray-500 text-xs ml-1">▾</span>
            </button>

            {fabnOpen && (
              <div className="absolute left-0 top-full mt-2 w-80 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl py-2 z-[200] max-h-72 overflow-y-auto">
                <div className="px-4 py-1.5 border-b border-gray-700 mb-1 flex items-center justify-between">
                  <p className="text-gray-500 text-xs font-semibold uppercase tracking-wider">Select FABNs</p>
                  {selectedFabns.length > 0 && (
                    <button
                      onClick={() => onFabnChange([])}
                      className="text-gray-600 hover:text-gray-400 text-xs transition-colors"
                    >
                      Clear all
                    </button>
                  )}
                </div>
                {fabns.map(f => {
                  const checked = selectedFabns.some(s => s.cusip === f.cusip)
                  return (
                    <button
                      key={f.cusip}
                      onClick={() => toggleFabn(f)}
                      className={`w-full text-left px-4 py-2.5 hover:bg-gray-700 transition-colors flex items-start gap-3
                        ${checked ? 'bg-amber-500/10' : ''}`}
                    >
                      <div className={`mt-0.5 w-4 h-4 rounded flex-shrink-0 border flex items-center justify-center
                        ${checked ? 'bg-amber-500 border-amber-500' : 'border-gray-600'}`}>
                        {checked && <span className="text-gray-900 text-xs font-bold leading-none">✓</span>}
                      </div>
                      <div className="flex-1 min-w-0 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className={`font-mono text-sm font-semibold ${checked ? 'text-amber-400' : 'text-white'}`}>
                            {f.cusip}
                          </p>
                          <p className="text-gray-500 text-xs mt-0.5 truncate">{f.sector}</p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <p className="text-gray-300 text-xs">{f.maturity ? f.maturity.slice(0, 10) : ''}</p>
                          <p className="text-gray-500 text-xs mt-0.5">
                            {f.rating}{f.coupon != null ? ` · ${(f.coupon * 100).toFixed(2)}%` : ''}
                          </p>
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
          <div className="flex items-center gap-2 bg-gray-800 rounded-xl px-4 py-2 border border-gray-700">
            {/* One-day back */}
            <button
              onClick={() => onAdvance(-1)}
              disabled={isAtMin}
              className="text-gray-400 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm font-bold w-6 h-6 flex items-center justify-center rounded hover:bg-gray-700"
            >
              ←
            </button>

            {/* Calendar toggle — clicking the emoji or date text opens the picker */}
            <button
              onClick={() => setShowCalendar(v => !v)}
              className="flex items-center gap-2 min-w-[140px] justify-center rounded-lg px-1 py-0.5 hover:bg-gray-700 transition-colors"
              title="Click to open calendar"
            >
              <span className={`text-xs transition-colors ${showCalendar ? 'text-amber-300' : 'text-amber-400'}`}>📅</span>
              <span className="text-white font-mono text-sm font-medium">{formattedDate}</span>
            </button>

            {/* One-day forward */}
            <button
              onClick={() => onAdvance(1)}
              disabled={isAtMax}
              className="text-gray-400 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm font-bold w-6 h-6 flex items-center justify-center rounded hover:bg-gray-700"
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

        {/* Right: profile */}
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => setProfileOpen(p => !p)}
            className="flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-gray-800 transition-colors border border-transparent hover:border-gray-700"
          >
            <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center text-gray-900 font-bold text-sm">
              J
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-white text-sm font-medium leading-none">John Doe</p>
              <p className="text-gray-500 text-xs mt-0.5">Portfolio Manager</p>
            </div>
            <span className="text-gray-500 text-xs ml-1">▾</span>
          </button>

          {profileOpen && (
            <div className="absolute right-0 top-full mt-2 w-52 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl py-2 z-[200]">
              <div className="px-4 py-2 border-b border-gray-700">
                <p className="text-white text-sm font-medium">John Doe</p>
                <p className="text-gray-400 text-xs">johndoe@example.com</p>
              </div>
              <div className="px-4 py-2">
                <p className="text-gray-500 text-xs">Simulated date</p>
                <p className="text-amber-400 text-xs font-mono">{date}</p>
              </div>
              <div className="px-2 pt-1 border-t border-gray-700">
                <button className="w-full text-left px-2 py-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg text-sm transition-colors">
                  Settings
                </button>
                <button className="w-full text-left px-2 py-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg text-sm transition-colors">
                  Sign out
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
    </>
  )
}
