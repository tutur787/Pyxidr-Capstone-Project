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
  url?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export type TabId = 'portfolio-deep-dive' | 'suggested-trades' | 'strategy-tracking' | 'risk' | 'derivative-usage'

export interface HyperParams {
  gamma_w: number   // capital cost weight (C1 + C3)
  beta_w: number    // momentum signal weight
  alpha_w: number   // C3 duration cost weight inside capital cost
  lambda_w: number  // cashflow shortfall penalty weight
  eps_D: number     // duration gap tolerance (years)
}
