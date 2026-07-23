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
          <span className="text-text-secondary text-xs">{label}</span>
        </div>
        <span className="text-text-primary font-mono text-sm font-bold">{format(value)}</span>
      </div>
      <p className="text-text-muted text-xs mb-2 leading-relaxed">{description}</p>
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
      <div className="flex justify-between text-text-muted text-xs mt-1">
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
      <p className="text-text-muted text-xs mt-0.5">{subtitle}</p>
      <div className="mt-2 h-px bg-surface-2" />
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
        className={`fixed top-0 left-0 h-full w-80 bg-surface-0 border-r border-border z-50
          transform transition-transform duration-300 ease-in-out flex flex-col
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-border">
          <div>
            <h2 className="text-text-primary font-semibold text-sm">Optimizer Parameters</h2>
            <p className="text-text-muted text-xs mt-0.5 leading-relaxed">
              Controls passed to the SAP optimizer via <span className="font-mono text-text-muted">/api/optimize</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors w-7 h-7 flex items-center justify-center rounded-xl hover:bg-surface-2 mt-0.5"
          >
            ✕
          </button>
        </div>

        {/* Scrollable params */}
        <div className="flex-1 overflow-y-auto px-5 py-2">

          <SectionHeader
            title="Objective Weights"
            subtitle="Scale each term in the SAP objective: maximize NII − lambda·RBC − turnover + savings + swap NII − swap capital cost"
          />

          <ParamSlider
            symbol="γ"
            label="Cost of capital (WACC)"
            description="Insurer WACC on required capital. Sets λ_cap = γ × 3, the coefficient on RBC = Σθᵢhᵢ in the SAP objective. Calibrated default 0.15 (15%). Higher = penalise RBC usage more strongly."
            value={params.gamma_w}
            min={0} max={1.0} step={0.01}
            format={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => set('gamma_w', v)}
          />

          <ParamSlider
            symbol="λ"
            label="Savings rate scalar (currently inactive)"
            description="Scales the lending-facility reinvestment rate: r_save = r_FABN × λ. The facility surplus base rate is currently 0.0 (no free parking), so this slider has no effect on any output until that base rate design changes."
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
            symbol="φ_cvar"
            label="CVaR risk budget"
            description="Primary risk control: worst-5% tail forced-sale loss (from historical rate/spread shock scenarios) must stay under φ_cvar × H. Replaces the old PV-shortfall cap. Lower = tighter risk budget, fewer/shorter-duration eligible bonds."
            value={params.phi_cvar}
            min={0.005} max={0.02} step={0.0005}
            format={v => `${(v * 100).toFixed(2)}%`}
            onChange={v => set('phi_cvar', v)}
          />

          <ParamSlider
            symbol="ε_D"
            label="Duration Gap Tolerance (relaxed — CVaR governs)"
            description="Maximum allowed deviation between portfolio duration and FABN liability duration, in years. Currently relaxed to an inert 100yr band while the CVaR risk constraint governs risk instead — this slider has no effect until CVaR is disabled."
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

          <SectionHeader
            title="Risk Signal"
            subtitle="Informational only — does not gate the optimizer"
          />

          <ParamSlider
            symbol="pctl"
            label="Trading-signal percentile"
            description="Worth-trading trigger: 21d rolling yield vol (σ_t) vs its own trailing-year distribution. Fires when σ_t exceeds this percentile of that distribution — a rank-based cutoff, so it always selects the same fraction of historical days regardless of the vol regime's shape. Size-of-Prize default: 75th (top quartile). This only drives the banner/chart in Risk and Suggested Trades — the optimizer always re-solves regardless."
            value={params.vol_percentile}
            min={50} max={95} step={5}
            format={v => `p${v.toFixed(0)}`}
            onChange={v => set('vol_percentile', v)}
          />

        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-border">
          <button
            onClick={() => { onApply?.(); onClose() }}
            className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-gray-900 font-semibold text-sm rounded-2xl transition-colors"
          >
            Apply & Close
          </button>
          <p className="text-text-muted text-xs text-center mt-2">
            Parameters will be used on the next optimizer run
          </p>
        </div>
      </aside>
    </>
  )
}
