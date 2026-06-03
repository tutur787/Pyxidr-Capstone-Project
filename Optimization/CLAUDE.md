# FABN Portfolio Optimization — Engineering & Math Guide

This folder optimizes a bond portfolio that backs a **Funding Agreement-Backed Note (FABN)**
liability for a U.S. life insurer (Athene-style). The work is a capstone **MVP**: demonstrate that
constraint-aware, re-optimizable allocation beats a static strategy, while respecting regulatory
capital (NAIC RBC), asset-liability duration matching, and liquidity.

There are **two generations** of objective function in this folder:

1. **Market-value NEV** (older notebooks) — income = OAS spread, maximize economic value.
2. **SAP statutory** (`FABN_Optimizer_SAP.ipynb`, current direction) — income = book yield
   (coupon + amortization) at amortized cost, maximize *stable statutory earnings per unit of
   required capital*. This follows `SAP.pdf` and the boss's review feedback.

---

## File map

| File | Role |
|---|---|
| `FABN_Data_Pipeline.ipynb` | **Shared input builder.** Pulls BigQuery, produces the `pipeline` dict every optimizer consumes. Run via `%run` from each optimizer. |
| `FABN_Optimizer_SAP.ipynb` | **Current optimizer.** SAP statutory objective (Phase 1, single-period). Built from the EB notebook. |
| `FABN_Optimizer_Gurobi_Clean_V_EB.ipynb` | Prior best market-value optimizer: RBC priced into objective, two-sided lending facility, conservative bond exclusion. Base for the SAP notebook. |
| `FABN_Optimizer_Gurobi_Clean_v2.ipynb` | Market-value optimizer with lending facility + PV-shortfall cap. ⚠️ Credits *discounted future bond CFs as "sale proceeds"* at FABN maturity — economically questionable; superseded. |
| `FABN_Optimizer_Gurobi_Clean.ipynb` | v1 clean optimizer (soft CF-shortfall penalty). |
| `FABN_Optimizer_Gurobi.ipynb` | Original skeleton/prototype. |
| `RBC Equations.md`, `Proposed Equation.md`, `RBC_Reformulation_Summary.md` | Supporting derivations (NAIC RBC components, LP reformulation). |
| `C1_table =.py` | C-1 charge factor lookup table (S&P / Moody's → factor). |

**Run order (any optimizer):** `Date Selection → Section 0 (%run pipeline) → 1A unpack → 1B/1C overrides → 2 model → 3 results → 4 analytics`.

---

## Data sources (BigQuery, project `insurance-backed-securities`)

| Dataset.Table | Used for |
|---|---|
| `Securities.Agg_Fixed_Field` | Static attributes: amt out, coupon, maturity, ratings (S&P/Moody's), BBG duration, sector, coupon freq. Defines the **bond universe** (N=303). |
| `Securities.Agg_Spread_Long` | Daily OAS spread per CUSIP → `spread`. |
| `Securities.Asset_Cashflows` | Coupon + principal schedule per CUSIP → cashflow matrices. Per **100 face**. |
| `Mid_Price.mid_long_raw` | Daily mid price → book/purchase value `price`, `book_yield`. |
| `Bid_Price.bid_long_raw` | Daily bid → transaction cost `tau`. |
| `Ask_Price.ask_long_raw` | Daily ask → `tau`. ⚠️ `Price` column is **STRING**; cast with `SAFE_CAST(... AS FLOAT64)`. |

Price panel covers **303 CUSIPs × 498 business days, 2024-03-01 → 2026-02-26** (≈2 years) —
this enables the Phase-2 dynamic backtest.

---

## The `pipeline` dict (outputs of `FABN_Data_Pipeline.ipynb`)

Dimensions: `N` bonds, `T` daily payment dates, `Q` quarters. All per-bond arrays are length `N`,
aligned to `CUSIPS` order.

| Key | Shape | Meaning |
|---|---|---|
| `CUSIPS`, `fixed` | — | universe order; full attribute DataFrame |
| `spread` | (N,) | OAS spread, decimal (`spread_clean`, sector-median filled) |
| `durs` | (N,) | modified duration (years), from cashflow IRR; BBG fallback |
| `theta` | (N,) | **C-1 RBC charge factor `f_i`** (rating-based) |
| `price` | (N,) | mid price per 100 face = book value `P_i` |
| `book_yield` | (N,) | effective-interest yield `y_i` (see §Book yield below) |
| `coupon_inc` | (N,) | current coupon yield = annual coupon / `P_i` (statutory `C_i`) |
| `amort_inc` | (N,) | amortization/accretion yield = `book_yield − coupon_inc` (statutory `A_i`) |
| `tau` | (N,) | transaction cost = `(ask − bid)/(2·mid)` (bid-ask half-spread) |
| `h_curr` | (N,) | current allocation (equal-weight placeholder until real book loaded) |
| `bond_cf` | (T,N) | daily asset cashflows, **per $1 face** (raw /100) |
| `qtr_bond_cf` | (Q,N) | quarterly asset cashflows, per $1 face |
| `qtr_fabn_cf` | (Q,) | FABN liability cashflows ($) at budget `H` |
| `t_vec`, `qtr_idx` | — | time-in-years vector; quarter labels |
| scalars | — | `H`, `r_FABN`, `D_FABN`, `C_curr`, `C_min`, `RBC_bar`, `dt`, weights, `eps_D` |

### Key derivations in the pipeline

**Duration (§5).** Macaulay → modified duration using each bond's own yield
`y_i = rf(T_i) + spread_i`, where `rf` is the interpolated FRED Treasury curve at the bond's
maturity tenor. `D_mod = D_mac / (1 + y_i)`.

**C-1 factor `theta` (§6).** S&P composite rating → NAIC C-1 charge; fallback Moody's → BBB default.

**Book yield `book_yield` (§9.5, new).** The **effective-interest yield**: the IRR `y_i` solving
$$\sum_t CF_{i,t}\,(1+y_i)^{-t} = P_i/100$$
(`bond_cf` is per $1 face, so target PV is price/100). Solved with `scipy.optimize.brentq` on
`[-0.5, 1.0]`; falls back to `rf + spread` if no root. This is the SAP book yield: it bundles
coupon income and the amortization of any premium/discount toward par.

**Coupon / amortization split.** `coupon_inc = annual_coupon / (price/100)`;
`amort_inc = book_yield − coupon_inc`. A premium bond (price > 100) has `amort_inc < 0`
(premium amortized away); a discount bond has `amort_inc > 0` (discount accreted).

**FABN liability & `D_FABN` (§8).** Semi-annual 3.205% coupon, issued 2022-09-06, matures
2027-09-06. Future payments after `optimization_date` define `qtr_fabn_cf` and the modified
duration target `D_FABN` (≈2.49 yrs at 2025-01-15).

---

## The SAP objective (`FABN_Optimizer_SAP.ipynb`)

Decision variable: `h_i ≥ 0` = dollars allocated to bond `i` (long-only).

### Objective (MVP simplified, §7 of `SAP.pdf`)

$$
\max_{h}\;\Big(\text{Statutory NII} \;-\; \lambda\cdot RBC \;-\; \eta\cdot\text{LiquidityPenalty} \;-\; \tau\text{-Turnover}\Big)
$$

| Term | LP expression | Notes |
|---|---|---|
| **Statutory NII** | $\sum_i (y_i - r^{FABN})\,h_i$ | `nii_rate = book_yield − r_FABN` (net basis; `income_basis` flag switches to gross). NII per $ = `book_yield` = `coupon_inc + amort_inc`. |
| **$\lambda\cdot RBC$** | $\lambda_{cap}\sum_i \theta_i h_i$ | `RBC = Σ f_i h_i`; `λ_cap = cost_of_capital × RBC_bar`. Annual cost-of-capital on required capital. |
| **$\eta\cdot$ Liquidity** | $\eta\sum_q DF_q\, s^{net}_q$ | PV of lending-facility shortfall = facility usage (§5). |
| **$\tau\cdot$ Turnover** | $\sum_i \tau_i(tc^+_i + tc^-_i)$ | `tau` = real bid-ask half-spread (§6). |
| **+ Savings income** | $r_{save}\,\delta\sum_{q<Q-1} B_q$ | surplus reinvestment income (facility carry); part of NII economically. |

**Headline metric:** statutory earnings / required capital = `nii_val / (RBC_bar · RBC_val)`.

### Constraints (LP, all linear)

| Constraint | Formula | Reformulation |
|---|---|---|
| Budget | $\sum_i h_i = H$ | — |
| Duration band | $\lvert \sum_i D_i h_i - D^{FABN}H\rvert \le \varepsilon_D H$ | `d_pos − d_neg = ΣD h − D_FABN·H`; `d_pos,d_neg ≤ eps_D·H` |
| Turnover decomp | $h_i - h_i^{curr} = tc^+_i - tc^-_i$ | $\lvert h_i-h_i^{curr}\rvert = tc^+_i + tc^-_i$ |
| Facility dynamics | $B_q - s^{net}_q = (1+r_{save}\delta)B_{q-1} + CF^A_q - CF^L_q$ | surplus accumulates in `B`, residual shortfall in `s_net` (both ≥ 0) |
| PV shortfall cap | $\sum_q DF_q\, s^{net}_q \le \phi_{sf}\cdot PV(\text{liab})$ | hard ceiling, `phi_sf=1%` |
| Issuer concentration | $\sum_{i\in\text{issuer}} h_i \le \delta H$ | `delta=5%`, grouped by CUSIP[:6] |
| Hold-to-maturity | `h_i.ub = 0` if bond CFs extend past FABN maturity | bonds that mature after the liability can't fund it |

### Parameters to tune (Section 1B)

`cost_of_capital` (WACC, default 8%), `eta` (liquidity weight), `r_save`/`r_borrow`,
`phi_sf` (shortfall cap), `delta` (issuer cap), `income_basis` ("net"/"gross").

### Linearization rules (used throughout)

- Absolute value `|x|` → `x = d⁺ − d⁻`, `|x| = d⁺ + d⁻`, `d⁺,d⁻ ≥ 0`.
- `max(0, x)` → non-negative slack with a `≥` constraint or balance equation.

---

## How SAP differs from the market-value optimizers (rationale)

| Aspect | Market-value (v2 / EB) | SAP (current) |
|---|---|---|
| Income | OAS `spread` (EB: duration-weighted `score·durs·h`) | book yield `(y_i − r_FABN)·h` = coupon + amortization |
| Why | maximize economic/market value | SAP holds at amortized cost; earnings are accrual, not MTM |
| Capital | EB: `γ·RBC_bar·C1·D_FABN` in objective; v2: hard RBC constraint | `λ·RBC`, `λ = cost_of_capital·RBC_bar` (clean §4 mapping) |
| Transaction cost | hardcoded 5/20 bps proxy | real bid-ask half-spread per bond |
| Bonds past FABN maturity | v2 fabricates discounted "sale proceeds" ⚠️; EB excludes | excludes (conservative) |
| Excluded by design | — | AVR & IMR (§10) — future extension only |

⚠️ **Do not reintroduce the v2 "liquidation proceeds" trick**: collapsing a bond's future
cashflows into an earlier quarter via PV discounting and counting them as cash available to pay the
liability overstates coverage. Future cashflows are not cash-in-hand on the sale date.

---

## Phase 2 (planned, not yet built): dynamic backtest

Wrap the single-period solve in `solve_sap(optimization_date, h_prev)` and roll it across the
498-day price panel (monthly/quarterly rebalance), feeding each solution as the next period's
`h_curr` so turnover `Σ|h_{i,t} − h_{i,t−1}|` becomes real. Compare cumulative statutory earnings
**dynamic vs static buy-and-hold** — the document's core thesis.

---

## Conventions & gotchas

- Cashflows from `Asset_Cashflows` are **per 100 face**; the pipeline divides by 100 → per $1 face.
  When `h_i` is dollars, `bond_cf[:,i]·h_i` gives liability-coverage dollars.
- `price` is per 100 face; book value per $1 face is `price/100`.
- Ask price is **STRING** in BigQuery — always `SAFE_CAST`.
- All notebooks require Gurobi (`gurobipy`) with a valid WLS license (`.env` at repo root) and GCP
  ADC auth (`gcloud auth application-default login`). FRED access via `pandas_datareader`.
- `optimization_date` valid range: 2022-09-07 → 2027-09-05 (FABN issue → maturity), and must have
  price/spread coverage in BigQuery (data starts 2024-03).
- Many model parameters (`H`, `C_curr`, `C_min`, `RBC_bar`) are **placeholders pending Athene
  confirmation** — see comments in the pipeline Parameters cell.
