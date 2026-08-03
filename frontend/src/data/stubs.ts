import type { NewsItem, HyperParams, Fabn } from '../types'

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
]

export const DATE_MIN = '2024-03-01'
export const DATE_MAX = '2026-02-26'
