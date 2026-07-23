import type { PortfolioKPIs, RatePoint, NewsItem, HyperParams, Fabn } from '../types'

export const stubKPIs: PortfolioKPIs = {
  value: 250_000_000,
  total_return: 1.52,
  yield_pct: 5.83,
  duration: 4.21,
  cvar_pct: 2.87,
  sharpe: 1.34,
  n_bonds: 104,
  ytd_return: 3.41,
  spread_bps: 71,
  rbc_c1_usage: 0.62,
}

function sineRate(base: number, amp: number, i: number, period: number) {
  return +(base + amp * Math.sin((2 * Math.PI * i) / period) + (Math.random() - 0.5) * 0.04).toFixed(3)
}

export function generateStubRates(anchorDate: string, n = 90): RatePoint[] {
  const points: RatePoint[] = []
  const d = new Date(anchorDate)
  d.setDate(d.getDate() - n)
  for (let i = 0; i < n; i++) {
    const cur = new Date(d)
    cur.setDate(cur.getDate() + i)
    points.push({
      date: cur.toISOString().slice(0, 10),
      rate_2y: sineRate(5.1, 0.3, i, 40),
      rate_10y: sineRate(4.3, 0.2, i, 60),
    })
  }
  return points
}

export const stubNews: NewsItem[] = [
  { date: '', headline: 'Fed signals pause in rate hikes amid cooling inflation data', source: 'Reuters', sentiment: 'positive', score: 0.71, issuer: 'Macro' },
  { date: '', headline: 'Royal Bank of Canada reports Q1 earnings beat on strong credit', source: 'Bloomberg', sentiment: 'positive', score: 0.84, issuer: 'RBC' },
  { date: '', headline: 'NAIC updates RBC C1 factor tables for 2024 reporting cycle', source: 'Insurance Journal', sentiment: 'neutral', score: 0.02, issuer: 'Regulatory' },
  { date: '', headline: 'IG spreads tighten 8 bps on risk-on sentiment', source: 'FT', sentiment: 'positive', score: 0.65, issuer: 'Macro' },
  { date: '', headline: 'JPMorgan warns of elevated duration risk in long-end bonds', source: 'WSJ', sentiment: 'negative', score: -0.48, issuer: 'JPM' },
  { date: '', headline: 'FABN issuance hits record in Q1 2024', source: 'Bloomberg', sentiment: 'positive', score: 0.58, issuer: 'FABN' },
  { date: '', headline: 'MetLife increases FABN program by $2B amid strong demand', source: 'Reuters', sentiment: 'positive', score: 0.73, issuer: 'MET' },
  { date: '', headline: 'Credit quality of IG corporates stable despite macro headwinds', source: "Moody's", sentiment: 'neutral', score: 0.11, issuer: 'Macro' },
]

export const defaultHyperParams: HyperParams = {
  gamma_w:        0.15,   // matches pipeline calibration
  lambda_w:       1.0,    // currently a no-op — facility reinvestment base rate is 0.0
  eps_D:          0.3,    // relaxed to an inert 100yr band while CVaR governs (always, currently)
  w_max:          0.05,
  n_min:          20,
  vol_percentile: 75,     // trading-signal trigger: top-quartile of trailing-year vol
  phi_cvar:       0.01,   // CVaR risk budget: worst-5% tail loss <= phi_cvar * H
}

export const KNOWN_FABNS: Fabn[] = [
  // The one real FABN this whole app models: ATH 3.205 03/08/27 (Athene Global Funding).
  {
    cusip:    '04685A3L3',
    coupon:   0.03205,
    maturity: '2027-03-08',
    rating:   'A+',
    sector:   'Athene Global Funding',
    status:   'active',
  },
  // Future issuances — not modeled yet, shown as placeholders rather than omitted.
  {
    cusip:    'Next FABN — 2026',
    coupon:   null,
    maturity: '',
    rating:   '',
    sector:   'Not yet issued',
    status:   'coming_soon',
  },
  {
    cusip:    'Next FABN — 2027',
    coupon:   null,
    maturity: '',
    rating:   '',
    sector:   'Not yet issued',
    status:   'coming_soon',
  },
]

export const DATE_MIN = '2024-03-01'
export const DATE_MAX = '2026-02-26'
