export interface PortfolioKPIs {
  value: number
  total_return: number
  yield_pct: number
  duration: number
  cvar_pct: number
  sharpe: number
  n_bonds: number
  ytd_return: number
  spread_bps: number
  rbc_c1_usage: number
}

export interface RatePoint {
  date: string
  rate_2y: number
  rate_10y: number
}

export interface NewsItem {
  date: string
  headline: string
  source: string
  sentiment: 'positive' | 'negative' | 'neutral'
  score: number
  issuer: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export type TabId = 'portfolio-deep-dive' | 'suggested-trades' | 'strategy-tracking' | 'risk' | 'derivative-usage'

export interface HyperParams {
  cvar_alpha: number
  cvar_kappa: number
  cvar_scenarios: number
  momentum_lookback: number
  momentum_forward: number
  cir_kappa: number
  cir_theta: number
  cir_sigma: number
}
