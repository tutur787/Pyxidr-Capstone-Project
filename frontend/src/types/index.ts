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
  gamma_w:        number
  lambda_w:       number  // currently a no-op — facility reinvestment base rate is 0.0
  eps_D:          number  // relaxed to an inert 100yr band while CVaR governs (always, currently)
  w_max:          number
  n_min:          number
  vol_percentile: number  // trading-signal threshold: worth_trading when 21d vol > this percentile of its trailing-year distribution
  phi_cvar:       number  // CVaR risk budget: worst-5% tail forced-sale loss <= phi_cvar × H
}

export interface Fabn {
  cusip:    string
  coupon:   number | null
  maturity: string
  rating:   string
  sector:   string
  status?:  'active' | 'coming_soon'  // absent = treated as 'active'
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
  score_bps:    number
  mid_price:    number   // per $100 face value
  reduced_cost: number   // Gurobi reduced cost: SAP δ per $ of h[i]
}

export interface Trade {
  cusip:            string
  sector:           string
  rating:           string
  action:           'BUY' | 'SELL'
  delta_weight_pct: number
  delta_usd:        number
  h_opt:            number
  spread_bps:       number
  duration:         number
  sap_score_bps:    number  // net SAP contribution rate in bps per $ (NII − capital cost)
  mid_price:        number  // market price per $100 face value
}

export interface AppliedTrade {
  cusip:     string
  action:    'BUY' | 'SELL'
  delta_usd: number
  h_opt:     number
  appliedAt: string  // YYYY-MM-DD of the optimization date when applied
}

export interface HistoryEntry {
  date:             string   // YYYY-MM-DD
  sap_opt:          number   // SAP objective (optimizer)
  sap_static:       number   // SAP objective (equal-weight benchmark)
  alpha:            number   // sap_opt - sap_static
  yield_pct:        number
  duration:         number
  duration_gap:     number
  spread_bps:       number
  n_bonds_selected: number
  txn_cost:         number   // turnover/trading cost for this rebalance
  market_value:     number   // Σ(h_opt_i × mid_price_i / 100) — total portfolio market value
}

export interface ConstraintResult {
  label: string
  value: number
  bound: number | null  // null = informational row, no hard bound (e.g. relaxed duration band)
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

export interface FacilityShadowPrice {
  period: string
  dual:   number
}

export interface IssuerShadowPrice {
  issuer: string
  dual:   number
}

export interface ReservationPrice {
  cusip:             string
  mkt_price:         number
  reservation_price: number
  gap:               number       // reservation_price - mkt_price ($/100 face)
  gap_pct:           number
  hurdle_rate:       number       // % — r*_i = book_yield_i - reduced_cost_i
  selected:          boolean
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

export interface FabnMarketPoint {
  date:          string
  fabn_ytm:      number
  treasury_ytm:  number
  spread_bps:    number
  prime_rate:    number
}

export interface SwapAllocation {
  tenor_years: number
  notional:    number   // $
  fixed_rate:  number   // e.g. 0.0450
  net_income:  number   // $ per year
  dur_contrib: number   // years (swap contribution to portfolio duration)
}

export interface CvarHistogramBin {
  bin_mid_pct: number
  count:       number
}

export interface SectorBreakdownEntry {
  sector:     string
  weight_pct: number
}

export interface SectorConcentration {
  top_sector:     string
  top_weight_pct: number
  breakdown:      SectorBreakdownEntry[]
}

export interface VolPoint {
  date:        string
  vol_21_bps:  number
}

export interface TradingSignal {
  series:             VolPoint[]
  current_vol_bps:    number | null
  median_vol_bps:     number | null   // trailing-year median of the rolling vol (for context)
  threshold_vol_bps:  number | null   // the `percentile`-th percentile of the trailing-year vol distribution
  ratio_to_median:    number | null
  percentile:         number          // e.g. 75 = top-quartile cutoff
  worth_trading:      boolean | null
  n_obs:              number
  lookback_n:         number
  degraded:           boolean
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
  duration_gap:     number   // bond-only |D_avg - D_FABN|, ignores swap overlay contribution
  duration_target:  number   // D_FABN — the liability duration target
  r_FABN:           number   // FABN crediting rate (e.g. 0.03205)
  r_float:          number   // 3M Treasury / SOFR proxy
  rbc_bar:          number   // required-capital multiplier (e.g. 3.0)
  cvar_pct:         number | null  // historical-simulation CVaR(95%), % of market value, quarterly horizon
  cvar_var_pct:     number | null  // VaR(95%) — the tail percentile boundary (less conservative than CVaR)
  cvar_n_obs:       number         // # of historical daily observations used
  cvar_degraded:    boolean        // true if n_obs is too small to trust the tail estimate
  cvar_method:      string
  cvar_histogram:   CvarHistogramBin[]
  trading_signal:   TradingSignal
  sector_concentration: SectorConcentration
  allocations:      BondAllocation[]
  trades:           Trade[]
  constraints:      ConstraintResult[]
  cashflows:        CashflowRow[]
  shadow_prices:    ShadowPriceRow[]
  imr_schedule:     ImrPeriod[]
  imr_total_gain:   number
  imr_contributions: ImrContribution[]
  static_comparison: StaticComparison
  swap_allocations:  SwapAllocation[]
  swap_notional_total:  number
  swap_cap_notional:    number
  swap_c3_capital_cost: number
  // Shadow-price / reservation-price analytics (notebook Section 3B / 3B-ii)
  marginal_dollar_unconstrained: number | null
  pi_facility:         FacilityShadowPrice[]
  pi_issuer_binding:   IssuerShadowPrice[]
  reservation_prices:  ReservationPrice[]
  error?:           string
}
