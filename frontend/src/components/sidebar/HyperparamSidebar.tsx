import type { HyperParams } from '../../types'

interface Props {
  open: boolean
  onClose: () => void
  params: HyperParams
  onChange: (p: HyperParams) => void
}

interface SliderProps {
  label: string
  symbol?: string
  value: number
  min: number
  max: number
  step: number
  format?: (v: number) => string
  onChange: (v: number) => void
}

function Slider({ label, symbol, value, min, max, step, format, onChange }: SliderProps) {
  const display = format ? format(value) : String(value)
  return (
    <div className="mb-4">
      <div className="flex justify-between items-baseline mb-1">
        <label className="text-gray-400 text-xs">
          {symbol && <span className="text-amber-400 mr-1">{symbol}</span>}
          {label}
        </label>
        <span className="text-white text-xs font-mono font-medium">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer accent-amber-400"
      />
      <div className="flex justify-between text-gray-600 text-xs mt-0.5">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  )
}

function Section({ title }: { title: string }) {
  return (
    <div className="mt-5 mb-3">
      <p className="text-amber-400 text-xs font-semibold uppercase tracking-widest">{title}</p>
      <div className="mt-1 h-px bg-gray-800" />
    </div>
  )
}

export default function HyperparamSidebar({ open, onClose, params, onChange }: Props) {
  function set<K extends keyof HyperParams>(key: K, value: HyperParams[K]) {
    onChange({ ...params, [key]: value })
  }

  return (
    <>
      {/* backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* drawer */}
      <aside
        className={`fixed top-0 left-0 h-full w-72 bg-gray-950 border-r border-gray-800 z-50
          transform transition-transform duration-300 ease-in-out flex flex-col
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-white font-semibold text-sm">Model Parameters</h2>
            <p className="text-gray-500 text-xs mt-0.5">Optimization hyperparameters</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-800"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <Section title="CVaR Optimizer" />
          <Slider
            label="Confidence Level"
            symbol="α"
            value={params.cvar_alpha}
            min={0.5} max={0.95} step={0.01}
            format={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => set('cvar_alpha', v)}
          />
          <Slider
            label="CVaR Budget"
            symbol="κ"
            value={params.cvar_kappa}
            min={100} max={1000} step={10}
            format={v => `${v} bps`}
            onChange={v => set('cvar_kappa', v)}
          />
          <Slider
            label="Scenarios"
            symbol="T"
            value={params.cvar_scenarios}
            min={100} max={5000} step={100}
            onChange={v => set('cvar_scenarios', v)}
          />

          <Section title="Momentum Signal" />
          <Slider
            label="Lookback Window"
            value={params.momentum_lookback}
            min={5} max={63} step={1}
            format={v => `${v}d`}
            onChange={v => set('momentum_lookback', v)}
          />
          <Slider
            label="Forward Window"
            value={params.momentum_forward}
            min={5} max={63} step={1}
            format={v => `${v}d`}
            onChange={v => set('momentum_forward', v)}
          />

          <Section title="CIR Interest Rate Model" />
          <Slider
            label="Reversion Speed"
            symbol="κ"
            value={params.cir_kappa}
            min={0.05} max={0.50} step={0.01}
            format={v => v.toFixed(2)}
            onChange={v => set('cir_kappa', v)}
          />
          <Slider
            label="Long-Run Mean"
            symbol="θ"
            value={params.cir_theta}
            min={0.02} max={0.08} step={0.001}
            format={v => `${(v * 100).toFixed(1)}%`}
            onChange={v => set('cir_theta', v)}
          />
          <Slider
            label="Volatility"
            symbol="σ"
            value={params.cir_sigma}
            min={0.005} max={0.05} step={0.001}
            format={v => `${(v * 100).toFixed(1)}%`}
            onChange={v => set('cir_sigma', v)}
          />
        </div>

        <div className="px-5 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-gray-900 font-semibold text-sm rounded-xl transition-colors"
          >
            Apply Parameters
          </button>
          <p className="text-gray-600 text-xs text-center mt-2">Changes will apply on next optimization run</p>
        </div>
      </aside>
    </>
  )
}
