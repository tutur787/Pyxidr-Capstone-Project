import type { HyperParams } from '../../types'

interface Props {
  open: boolean
  onClose: () => void
  params: HyperParams
  onChange: (p: HyperParams) => void
  onApply?: () => void
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

export default function HyperparamSidebar({ open, onClose, params, onChange, onApply }: Props) {
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
              Controls passed to the SAP optimizer via <span className="font-mono text-gray-400">/api/optimize</span>
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
            subtitle="Scale each term in the SAP objective: maximize NII − lambda·RBC − turnover − liq_penalty + savings"
          />

          <ParamSlider
            symbol="γ"
            label="Cost of capital (WACC)"
            description="Insurer WACC on required capital. Sets λ_cap = γ × 1.5, the coefficient on RBC = Σθᵢhᵢ in the SAP objective. Calibrated default 0.15 (15%). Higher = penalise RBC usage more strongly."
            value={params.gamma_w}
            min={0} max={1.0} step={0.01}
            format={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => set('gamma_w', v)}
          />

          <ParamSlider
            symbol="λ"
            label="Savings rate scalar"
            description="Scales the lending-facility reinvestment rate: r_save = r_FABN × λ. Default 1.0 = surplus earns r_FABN (3.205%). Higher = more savings income, rewarding CF surplus accumulation."
            value={params.lambda_w}
            min={0.5} max={2.0} step={0.05}
            format={v => v.toFixed(2)}
            onChange={v => set('lambda_w', v)}
          />

          <SectionHeader
            title="Constraints"
            subtitle="Hard bounds enforced during optimisation"
          />

          <ParamSlider
            symbol="ε_D"
            label="Duration Gap Tolerance"
            description="Maximum allowed deviation between portfolio duration and FABN liability duration, in years. Calibrated default is 0.3 yr."
            value={params.eps_D}
            min={0.05} max={2.0} step={0.05}
            format={v => `${v.toFixed(2)} yr`}
            onChange={v => set('eps_D', v)}
          />

          <ParamSlider
            symbol="w_max"
            label="Maximum single bond weight"
            description="Upper bound on the fraction of the portfolio allocated to any single bond. Lower = more diversification required."
            value={params.w_max}
            min={0.01} max={0.20} step={0.01}
            format={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => set('w_max', v)}
          />

          <ParamSlider
            symbol="n_min"
            label="Minimal bond count"
            description="Minimum number of distinct bonds that must be held in the portfolio."
            value={params.n_min}
            min={5} max={100} step={1}
            format={v => String(Math.round(v))}
            onChange={v => set('n_min', Math.round(v))}
          />

        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-800">
          <button
            onClick={() => { onApply?.(); onClose() }}
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
