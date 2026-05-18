import { useState, useRef, useEffect } from 'react'
import HyperparamSidebar from '../sidebar/HyperparamSidebar'
import type { HyperParams, Fabn } from '../../types'

interface Props {
  date: string
  formattedDate: string
  onAdvance: (delta: number) => void
  isAtMin: boolean
  isAtMax: boolean
  hyperParams: HyperParams
  onHyperParamsChange: (p: HyperParams) => void
  fabns: Fabn[]
  selectedFabns: Fabn[]
  onFabnChange: (fabns: Fabn[]) => void
}

export default function Header({
  date, formattedDate, onAdvance, isAtMin, isAtMax,
  hyperParams, onHyperParamsChange,
  fabns, selectedFabns, onFabnChange,
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [fabnOpen, setFabnOpen] = useState(false)

  // Click-outside for FABN dropdown — avoids the z-index stacking-context bug
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

  function toggleFabn(f: Fabn) {
    const already = selectedFabns.some(s => s.cusip === f.cusip)
    onFabnChange(already ? selectedFabns.filter(s => s.cusip !== f.cusip) : [...selectedFabns, f])
  }

  // Header label
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

          {/* FABN selector — ref-based click-outside, no backdrop */}
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
                      {/* Checkbox indicator */}
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

        {/* Center: date navigator */}
        <div className="flex items-center gap-2 bg-gray-800 rounded-xl px-4 py-2 border border-gray-700">
          <button
            onClick={() => onAdvance(-1)}
            disabled={isAtMin}
            className="text-gray-400 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm font-bold w-6 h-6 flex items-center justify-center rounded hover:bg-gray-700"
          >
            ←
          </button>
          <div className="flex items-center gap-2 min-w-[140px] justify-center">
            <span className="text-amber-400 text-xs">📅</span>
            <span className="text-white font-mono text-sm font-medium">{formattedDate}</span>
          </div>
          <button
            onClick={() => onAdvance(1)}
            disabled={isAtMax}
            className="text-gray-400 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-sm font-bold w-6 h-6 flex items-center justify-center rounded hover:bg-gray-700"
          >
            →
          </button>
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
      />
    </>
  )
}
