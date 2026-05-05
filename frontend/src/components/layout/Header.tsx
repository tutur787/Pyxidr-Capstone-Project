import { useState } from 'react'
import HyperparamSidebar from '../sidebar/HyperparamSidebar'
import type { HyperParams } from '../../types'

interface Props {
  date: string
  formattedDate: string
  onAdvance: (delta: number) => void
  isAtMin: boolean
  isAtMax: boolean
  hyperParams: HyperParams
  onHyperParamsChange: (p: HyperParams) => void
}

export default function Header({ date, formattedDate, onAdvance, isAtMin, isAtMax, hyperParams, onHyperParamsChange }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  return (
    <>
      <header className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-800 z-30 relative">
        {/* Left: burger + title */}
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
          <div className="flex items-center gap-2">
            <span className="text-amber-400 text-lg">▦</span>
            <h1 className="text-white font-semibold text-base tracking-wide">FABN Portfolio Simulator</h1>
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
        <div className="relative">
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
            <div className="absolute right-0 top-full mt-2 w-52 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl py-2 z-50">
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

      {/* backdrop for profile dropdown */}
      {profileOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setProfileOpen(false)} />
      )}
    </>
  )
}
