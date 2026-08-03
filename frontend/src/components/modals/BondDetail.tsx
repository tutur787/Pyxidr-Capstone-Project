import { useEffect, useRef, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import Modal from './Modal'
import type { BondSummary, BondDetailData, OptimizerResult } from '../../types'

interface Props {
  onClose: () => void
  date:    string
  result:  OptimizerResult | null
}

function fmtPrice(n: number | null): string {
  return n !== null ? n.toFixed(3) : '—'
}

function fmtPct(n: number | null | undefined, digits = 2): string {
  return n !== null && n !== undefined ? `${n.toFixed(digits)}%` : '—'
}

function fmtUsd(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '−' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

function StatTile({ label, value, sublabel }: { label: string; value: string; sublabel?: string }) {
  return (
    <div className="bg-surface-2 rounded-2xl p-4 border border-border">
      <p className="text-text-muted text-xs mb-1">{label}</p>
      <p className="text-text-primary font-mono font-semibold text-sm">{value}</p>
      {sublabel && <p className="text-text-muted text-[10px] mt-0.5">{sublabel}</p>}
    </div>
  )
}

export default function BondDetail({ onClose, date, result }: Props) {
  const [bonds, setBonds] = useState<BondSummary[]>([])
  const [bondsLoading, setBondsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selectedCusip, setSelectedCusip] = useState<string | null>(null)
  const [detail, setDetail] = useState<BondDetailData | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const pickerRef = useRef<HTMLDivElement>(null)

  // Picker list — refetch on date change since universe membership shifts with maturities
  useEffect(() => {
    let cancelled = false
    setBondsLoading(true)
    fetch(`/api/bonds?date=${date}`)
      .then(r => r.json())
      .then((data: BondSummary[]) => { if (!cancelled) setBonds(data) })
      .catch(() => { if (!cancelled) setBonds([]) })
      .finally(() => { if (!cancelled) setBondsLoading(false) })
    return () => { cancelled = true }
  }, [date])

  // Full detail — fetched lazily once a bond is selected
  useEffect(() => {
    if (!selectedCusip) { setDetail(null); return }
    let cancelled = false
    setDetailLoading(true)
    setDetailError(null)
    fetch(`/api/bonds/${selectedCusip}?date=${date}`)
      .then(async r => {
        if (r.status === 404) throw new Error(`${selectedCusip} not found in the universe for ${date}`)
        if (!r.ok) throw new Error(`Request failed (${r.status})`)
        return r.json() as Promise<BondDetailData>
      })
      .then(data => { if (!cancelled) setDetail(data) })
      .catch((err: Error) => { if (!cancelled) { setDetail(null); setDetailError(err.message) } })
      .finally(() => { if (!cancelled) setDetailLoading(false) })
    return () => { cancelled = true }
  }, [selectedCusip, date])

  // Click-outside to close the picker
  useEffect(() => {
    if (!pickerOpen) return
    function handleClick(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [pickerOpen])

  const q = search.trim().toLowerCase()
  const filteredBonds = q
    ? bonds.filter(b =>
        b.cusip.toLowerCase().includes(q) ||
        b.sector.toLowerCase().includes(q) ||
        b.rating_sp.toLowerCase().includes(q))
    : bonds

  const isOptimal = result?.status === 'optimal'
  const allocRow  = isOptimal && result ? result.allocations.find(a => a.cusip === selectedCusip) : undefined
  const resRow    = isOptimal && result ? result.reservation_prices.find(r => r.cusip === selectedCusip) : undefined

  const cashflowData = (detail?.cashflow_schedule ?? []).map(pt => ({
    period: pt.period,
    cf:     pt.cf_per_100_face,
  }))

  return (
    <Modal title="Bond Detail" subtitle="Look up any bond in the collateral universe" onClose={onClose}>
      <div className="space-y-6">

        {/* Bond picker */}
        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setPickerOpen(o => !o)}
            className="w-full flex items-center justify-between gap-2 px-4 py-2.5 rounded-2xl border border-border bg-surface-2 hover:border-border-strong transition-colors"
          >
            <span className="font-mono text-sm text-text-primary">
              {selectedCusip ?? (bondsLoading ? 'Loading bond universe…' : `Select a bond… (${bonds.length} available)`)}
            </span>
            <span className="text-text-muted text-xs">▾</span>
          </button>

          {pickerOpen && (
            <div className="glass absolute left-0 top-full mt-2 w-full border border-border rounded-2xl shadow-2xl z-[200] max-h-80 overflow-hidden flex flex-col">
              <div className="p-2 border-b border-border">
                <input
                  autoFocus
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search CUSIP, sector, or rating…"
                  className="w-full bg-surface-2 border border-border rounded-xl px-3 py-1.5 text-sm text-text-primary
                    placeholder-text-muted focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all"
                />
              </div>
              <div className="overflow-y-auto">
                {filteredBonds.length === 0 && (
                  <p className="text-text-muted text-xs px-4 py-3">No bonds match "{search}"</p>
                )}
                {filteredBonds.map(b => (
                  <button
                    key={b.cusip}
                    onClick={() => { setSelectedCusip(b.cusip); setPickerOpen(false); setSearch('') }}
                    className={`w-full text-left px-4 py-2 hover:bg-surface-2 transition-colors flex items-center justify-between gap-3
                      ${b.cusip === selectedCusip ? 'bg-brand/10' : ''}`}
                  >
                    <div className="min-w-0">
                      <p className="font-mono text-sm text-text-primary truncate">{b.cusip}</p>
                      <p className="text-text-muted text-xs truncate">{b.sector}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-text-secondary text-xs">{b.rating_sp || '—'}</p>
                      <p className="text-text-muted text-xs">{b.maturity ? b.maturity.slice(0, 7) : ''}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {!selectedCusip && (
          <div className="h-40 bg-surface-2/40 rounded-2xl border border-border border-dashed flex items-center justify-center">
            <p className="text-text-muted text-sm">Pick a bond above to see its detail</p>
          </div>
        )}

        {selectedCusip && detailLoading && (
          <div className="h-40 flex items-center justify-center">
            <p className="text-text-muted text-sm animate-pulse">Loading {selectedCusip}…</p>
          </div>
        )}

        {selectedCusip && detailError && !detailLoading && (
          <div className="p-4 rounded-2xl border border-red-500/20 bg-red-500/5">
            <p className="text-red-400 text-sm">{detailError}</p>
          </div>
        )}

        {selectedCusip && detail && !detailLoading && (
          <>
            {/* Identity header */}
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-amber-400 font-semibold text-lg">{detail.cusip}</p>
                <p className="text-text-muted text-sm">{detail.sector}</p>
              </div>
              <div className="text-right">
                <p className="text-text-secondary text-sm">{detail.rating_sp || '—'} / {detail.rating_moodys || '—'}</p>
                <p className="text-text-muted text-xs">Matures {detail.maturity || '—'}</p>
              </div>
            </div>

            {/* Stat tiles */}
            <div className="grid grid-cols-4 gap-3">
              <StatTile label="Mid Price" value={fmtPrice(detail.mid_price)} sublabel="per $100 face" />
              <StatTile label="Bid / Ask" value={`${fmtPrice(detail.bid_price)} / ${fmtPrice(detail.ask_price)}`} />
              <StatTile label="Book Yield" value={fmtPct(detail.book_yield_pct)} />
              <StatTile label="Coupon" value={fmtPct(detail.coupon_pct)} />
              <StatTile label="Duration" value={`${detail.duration.toFixed(2)} yrs`} />
              <StatTile label="Spread" value={`${detail.spread_bps.toFixed(1)} bps`} />
              <StatTile label="RBC Factor" value={fmtPct(detail.rbc_factor_pct)} />
              <StatTile label="Bid-Ask Cost" value={`${detail.bid_ask_cost_bps.toFixed(1)} bps`} />
              <StatTile label="Par Amount" value={fmtUsd(detail.par_amount)} />
              <StatTile label="Coupon Income" value={fmtPct(detail.coupon_income_pct)} />
              <StatTile label="Amort Income" value={fmtPct(detail.amort_income_pct)} />
              <StatTile label="Current Holding" value={fmtUsd(detail.h_curr)} sublabel="equal-weight baseline" />
            </div>

            {/* Optimizer cross-reference */}
            <div>
              <h3 className="text-text-primary font-medium text-sm mb-3">Optimizer Cross-Reference</h3>
              {allocRow ? (
                <div className="grid grid-cols-4 gap-3">
                  <StatTile label="Optimal Alloc" value={fmtUsd(allocRow.h_opt)} />
                  <StatTile label="Weight" value={fmtPct(allocRow.weight * 100)} />
                  <StatTile label="Delta vs Current" value={fmtUsd(allocRow.delta_usd)} />
                  <StatTile label="Reduced Cost" value={allocRow.reduced_cost.toFixed(6)} />
                </div>
              ) : (
                <div className="p-4 rounded-2xl border border-border bg-surface-2/40">
                  <p className="text-text-muted text-sm">
                    {isOptimal
                      ? 'Not selected in the current optimization run (h_opt = $0).'
                      : "Run the optimizer to see this bond's allocation."}
                  </p>
                </div>
              )}
            </div>

            {/* Reservation price */}
            <div>
              <h3 className="text-text-primary font-medium text-sm mb-3">Reservation Price</h3>
              {resRow ? (
                <div className="grid grid-cols-4 gap-3">
                  <StatTile label="Market Price" value={fmtPrice(resRow.mkt_price)} />
                  <StatTile label="Reservation Price" value={fmtPrice(resRow.reservation_price)} />
                  <StatTile label="Gap" value={`${resRow.gap >= 0 ? '+' : ''}${resRow.gap.toFixed(3)}`} sublabel={`${resRow.gap_pct.toFixed(2)}%`} />
                  <StatTile label="Hurdle Rate" value={fmtPct(resRow.hurdle_rate)} />
                </div>
              ) : (
                <div className="p-4 rounded-2xl border border-border bg-surface-2/40">
                  <p className="text-text-muted text-sm">
                    Not in the current top/bottom-25 mispricing shortlist for this run.
                  </p>
                </div>
              )}
            </div>

            {/* vs. portfolio averages */}
            {isOptimal && result && (
              <div>
                <h3 className="text-text-primary font-medium text-sm mb-3">vs. Portfolio Averages</h3>
                <div className="grid grid-cols-3 gap-3">
                  <StatTile
                    label="Duration"
                    value={`${detail.duration.toFixed(2)} yrs`}
                    sublabel={`portfolio: ${result.duration.toFixed(2)} yrs`}
                  />
                  <StatTile
                    label="Spread"
                    value={`${detail.spread_bps.toFixed(1)} bps`}
                    sublabel={`portfolio: ${result.spread_bps.toFixed(1)} bps`}
                  />
                  <StatTile
                    label="RBC Factor"
                    value={fmtPct(detail.rbc_factor_pct)}
                    sublabel={`portfolio C1: ${(result.rbc_c1_usage * 100).toFixed(2)}%`}
                  />
                </div>
              </div>
            )}

            {/* Cashflow schedule */}
            <div>
              <h3 className="text-text-primary font-medium text-sm mb-3">Cashflow Schedule</h3>
              {cashflowData.length > 0 ? (
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={cashflowData} margin={{ top: 8, right: 16, bottom: 0, left: 16 }}>
                      <CartesianGrid stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="period" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
                      <YAxis
                        tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                        tickFormatter={(v: number) => v.toFixed(1)}
                        width={48}
                      />
                      <Tooltip
                        contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                        formatter={(v: number) => [`${v.toFixed(3)} / $100 face`, 'Cashflow']}
                      />
                      <Bar dataKey="cf" fill="var(--brand-accent)" radius={[3, 3, 0, 0]} maxBarSize={22} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-20 bg-surface-2/40 rounded-2xl border border-border border-dashed flex items-center justify-center">
                  <p className="text-text-muted text-sm">No remaining cashflows for this bond</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
