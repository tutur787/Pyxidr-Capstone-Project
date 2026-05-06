import type { HyperParams } from '../../types'

interface Props {
  open: boolean
  onClose: () => void
  params: HyperParams
  onChange: (p: HyperParams) => void
}

interface SliderProps {
  symbol: string
  label: string
  description: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  onChange: (v: number) => void
}

function ParamSlider({ symbol, label, description, value, min, max, step, format, onChange }: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100

  return (
    <div className="mb-5">
      <div className="flex items-baseline justify-between mb-1">
        <div className="flex items-baseline gap-1.5">
          <span className="text-amber-400 font-mono text-sm font-semibold">{symbol}</span>
          <span className="text-gray-300 text-xs">{label}</span>
        </div>
        <span className="text-white font-mono text-sm font-bold">{format(value)}</span>
      </div>
      <p className="text-gray-600 text-xs mb-2 leading-relaxed">{description}</p>
      <div className="relative">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-amber-400"
          style={{
            background: `linear-gradient(to right, #f59e0b ${pct}%, #374151 ${pct}%)`,
          }}
        />
      </div>
      <div className="flex justify-between text-gray-700 text-xs mt-1">
        <span>{format(min)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  )
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mt-6 mb-4">
      <p className="text-amber-400 text-xs font-semibold uppercase tracking-widest">{title}</p>
      <p className="text-gray-600 text-xs mt-0.5">{subtitle}</p>
      <div className="mt-2 h-px bg-gray-800" />
    </div>
  )
}

export default function HyperparamSidebar({ open, onClose, params, onChange }: Props) {
  function set<K extends keyof HyperParams>(key: K, value: number) {
    onChange({ ...params, [key]: value })
  }

  return (
    <>
      {open && (
        <div className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm" onClick={onClose} />
      )}

      <aside
        className={`fixed top-0 left-0 h-full w-80 bg-gray-950 border-r border-gray-800 z-50
          transform transition-transform duration-300 ease-in-out flex flex-col
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-white font-semibold text-sm">Optimizer Parameters</h2>
            <p className="text-gray-500 text-xs mt-0.5 leading-relaxed">
              Controls passed to <span className="font-mono text-gray-400">update_user_params()</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-800 mt-0.5"
          >
            ✕
          </button>
        </div>

        {/* Scrollable params */}
        <div className="flex-1 overflow-y-auto px-5 py-2">

          <SectionHeader
            title="Objective Weights"
            subtitle="Scale each term in the NEV objective: maximize spread_income − capital_cost − txn_cost − cf_penalty"
          />

          <ParamSlider
            symbol="γ"
            label="Capital Cost Weight"
            description="Scales the full RBC capital cost term (C1 credit risk + α·C3 duration cost). Higher = penalise regulatory capital usage more."
            value={params.gamma_w}
            min={0} max={5} step={0.05}
            format={v => v.toFixed(2)}
            onChange={v => set('gamma_w', v)}
          />

          <ParamSlider
            symbol="β"
            label="Momentum Signal Weight"
            description="Adds β × momentum_score to each bond's spread in the objective. 0 = pure spread optimisation; positive values tilt toward recent price momentum."
            value={params.beta_w}
            min={0} max={2} step={0.05}
            format={v => v.toFixed(2)}
            onChange={v => set('beta_w', v)}
          />

          <ParamSlider
            symbol="α"
            label="C3 Duration Cost Weight"
            description="Weight on the C3 interest-rate risk term inside the capital cost: C3 = α × (d⁺ + d⁻). 0 = duration gap is only a hard constraint (ε_D), not penalised in the objective."
            value={params.alpha_w}
            min={0} max={2} step={0.05}
            format={v => v.toFixed(2)}
            onChange={v => set('alpha_w', v)}
          />

          <ParamSlider
            symbol="λ"
            label="CF Shortfall Penalty"
            description="Penalty per dollar of quarterly cashflow shortfall relative to the FABN liability schedule. Higher = stricter asset–liability cashflow matching."
            value={params.lambda_w}
            min={0} max={10} step={0.1}
            format={v => v.toFixed(1)}
            onChange={v => set('lambda_w', v)}
          />

          <SectionHeader
            title="Constraints"
            subtitle="Hard bounds enforced during optimisation"
          />

          <ParamSlider
            symbol="ε_D"
            label="Duration Gap Tolerance"
            description="Maximum allowed deviation between portfolio duration and FABN liability duration, in years. Tighter = closer asset–liability duration match."
            value={params.eps_D}
            min={0.05} max={3.0} step={0.05}
            format={v => `${v.toFixed(2)} yr`}
            onChange={v => set('eps_D', v)}
          />

          {/* Current values summary */}
          <div className="mt-6 mb-4 p-3 bg-gray-900 rounded-xl border border-gray-800">
            <p className="text-gray-500 text-xs font-medium mb-2 uppercase tracking-wider">Current call</p>
            <pre className="text-gray-400 text-xs font-mono leading-relaxed whitespace-pre-wrap">
{`update_user_params(
  gamma_w  = ${params.gamma_w.toFixed(2)},
  beta_w   = ${params.beta_w.toFixed(2)},
  alpha_w  = ${params.alpha_w.toFixed(2)},
  lambda_w = ${params.lambda_w.toFixed(1)},
  eps_D    = ${params.eps_D.toFixed(2)},
)`}
            </pre>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-gray-900 font-semibold text-sm rounded-xl transition-colors"
          >
            Apply & Close
          </button>
          <p className="text-gray-700 text-xs text-center mt-2">
            Parameters will be used on the next optimizer run
          </p>
        </div>
      </aside>
    </>
  )
}
