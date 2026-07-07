import Modal from './Modal'
import { useTheme } from '../../contexts/ThemeContext'
import type { ThemePreference } from '../../contexts/ThemeContext'

interface Props {
  onClose: () => void
}

const THEME_OPTIONS: { value: ThemePreference; label: string; icon: string }[] = [
  { value: 'light',  label: 'Light',  icon: '☀︎' },
  { value: 'dark',   label: 'Dark',   icon: '☾' },
  { value: 'system', label: 'System', icon: '⚙' },
]

export default function SettingsModal({ onClose }: Props) {
  const { theme, setTheme } = useTheme()

  return (
    <Modal title="Settings" subtitle="Appearance and workspace preferences" onClose={onClose}>
      <div className="space-y-6">
        <section>
          <h3 className="text-text-primary font-medium text-sm mb-1">Appearance</h3>
          <p className="text-text-muted text-xs mb-3">
            Choose how the dashboard looks. System follows your OS setting.
          </p>
          <div className="inline-flex bg-surface-2 border border-border rounded-2xl p-1 gap-1">
            {THEME_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setTheme(opt.value)}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors
                  ${theme === opt.value
                    ? 'bg-brand text-white shadow-sm'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-1'}`}
              >
                <span aria-hidden="true">{opt.icon}</span>
                {opt.label}
              </button>
            ))}
          </div>
        </section>

        <div className="border-t border-border" />

        <section>
          <h3 className="text-text-primary font-medium text-sm mb-1">Brand</h3>
          <p className="text-text-muted text-xs">
            Colors follow the Pyxidr palette — primary blue and magenta accent, adapted for both light and dark surfaces.
          </p>
          <div className="flex items-center gap-3 mt-3">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-brand border border-border" />
              <span className="text-text-secondary text-xs">Primary</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-[var(--brand-highlight)] border border-border" />
              <span className="text-text-secondary text-xs">Highlight</span>
            </div>
          </div>
        </section>
      </div>
    </Modal>
  )
}
