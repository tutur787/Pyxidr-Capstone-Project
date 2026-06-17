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
  gamma_w:  number
  lambda_w: number
  eps_D:    number
  w_max:    number
  n_min:    number
}

export interface Fabn {
  cusip:    string
  coupon:   number | null
  maturity: string
  rating:   string
  sector:   string
}

export interface BondAllocation {
  cusip:      string
  sector:     string
  rating:     string
  h_opt:      number
  h_curr:     number
  delta_usd:  number
  weight:     number
  spread_bps: number
  duration:   number
  score_bps:  number
}

export interface Trade {
  cusip:            string
  sector:           string
  rating:           string
  action:           'BUY' | 'SELL'
  delta_weight_pct: number
  delta_usd:        number
  spread_bps:       number
  duration:         number
}

export interface ConstraintResult {
  label: string
  value: number
  bound: number
  pass:  boolean
}

export interface CashflowRow {
  period:        string
  fabn_cf:       number
  asset_cf:      number
  surplus:       number
  shortfall_net: number
  facility_bal:  number
}

export interface ShadowPriceRow {
  label: string
  dual:  number | null
  unit:  string
}

export interface ImrPeriod {
  period:      string
  imr_balance: number
  imr_release: number
}

export interface ImrContribution {
  cusip:         string
  sale_usd:      number
  mid_price:     number
  realized_gain: number
}

export interface StaticComparison {
  nii:          number
  capital_cost: number
  sap:          number
  duration:     number
  n_bonds:      number
}

export interface OptimizerResult {
  status:           'optimal' | 'infeasible' | 'error'
  date:             string
  n_bonds_universe: number
  n_bonds_selected: number
  spread_bps:       number
  duration:         number
  yield_pct:        number
  rbc_c1_usage:     number
  rbc_ratio:        number
  nev:              number
  spread_income:    number
  capital_cost:     number
  c1_cost:          number
  c3_cost:          number
  txn_cost:         number
  duration_gap:     number
  allocations:      BondAllocation[]
  trades:           Trade[]
  constraints:      ConstraintResult[]
  cashflows:        CashflowRow[]
  shadow_prices:    ShadowPriceRow[]
  imr_schedule:     ImrPeriod[]
  imr_total_gain:   number
  imr_contributions: ImrContribution[]
  static_comparison: StaticComparison
  error?:           string
}
