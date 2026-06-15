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
| `FABN_Optimizer_SAP.ipynb` | **Current optimizer (Phase 1).** SAP statutory objective, single-period. Built from the EB notebook. |
| `FABN_Optimizer_SAP_Backtest.ipynb` | **Phase 2.** Daily dynamic backtest: re-optimizes every trading day with a buy/sell decomposition (retained lots at locked book yield, new buys at market), netting trading cost, capital, lending revenue & borrowing cost; compares dynamic vs static. Self-contained. |
| `FABN_Optimizer_Gurobi_Clean_V_EB.ipynb` | Prior best market-value optimizer: RBC priced into objective, two-sided lending facility, conservative bond exclusion. Base for the SAP notebook. |
| `FABN_Optimizer_Gurobi_Clean_v2.ipynb` | Market-value optimizer with lending facility + PV-shortfall cap. ⚠️ Credits *discounted future bond CFs as "sale proceeds"* at FABN maturity — economically questionable; superseded. |
| `FABN_Optimizer_Gurobi_Clean.ipynb` | v1 clean optimizer (soft CF-shortfall penalty). |
| `FABN_Optimizer_Gurobi.ipynb` | Original skeleton/prototype. |
| `RBC Equations.md`, `Proposed Equation.md`, `RBC_Reformulation_Summary.md` | Supporting derivations (NAIC RBC components, LP reformulation). |
| `C1_table =.py` | C-1 charge factor lookup table (S&P / Moody's → factor). |
| `fabn_finance.py` | **Shared, unit-tested math** (single source of truth): book-yield IRR, Macaulay/modified duration, coupon/amortization split, C-1 lookup, and the Phase-2 `IMRLedger`. Both the pipeline and the backtest import from here. |
| `tests/test_fabn_finance.py` | **pytest** suite (18 tests): par/premium/discount book yield, zero-coupon duration, `book_yield = coupon_inc + amort_inc` identity, C-1 fallbacks, and the IMR conservation identity. Run `pytest tests/ -v` from this folder. |
| `METHODOLOGY.md` | Financial methodology & assumptions: every formula with its code home, the SAP objective, the soft-band / post-FABN relaxation, the IMR rule, placeholders pending Athene, and how the math is verified. |

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

## Phase 2 — daily dynamic backtest (`FABN_Optimizer_SAP_Backtest.ipynb`, implemented)

A **daily** re-optimization backtest. Self-contained: loads universe, cashflows, C-1 table, the
full daily price panels, and FRED history **once**, then **precomputes** per-(day, bond) arrays:
market book yield `Y[d,i]` (effective-interest IRR vs that day's mid), modified duration `DUR`,
bid-ask cost `TAU`, eligibility `ELIG`/`alive`. The IRR precompute (Section 1) is the slow step;
`STEP>1` sub-samples days for a quick trial (`STEP=1` = every trading day, ~498).

**Daily decision via buy/sell decomposition** (`solve_day`). Holding `h_i = h_prev_i + b_i − s_i`
with buys `b_i≥0`, sells `0≤s_i≤h_prev_i`:
$$\max_{b,s\ge0}\ T\!\sum_i\!\big[(h^{prev}_i-s_i)(y^{bk}_i-r^F)+b_i(y^{mkt}_i-r^F)\big]-T\lambda\!\sum_i\theta_i h_i-\sum_i\tau_i(b_i+s_i)+r_{save}\delta\!\sum_q B_q-r_{borrow}\delta\!\sum_q s^{net}_q$$
- **Retained lots earn the locked book yield `y^bk`; new buys earn market `y^mkt`** — so the swap
  trigger is the true *pickup minus the locked yield given up*, not market-vs-market. Linear in
  `(b_i,s_i)`.
- **All four economics enter the trade decision:** trading cost `τ_i(b_i+s_i)` (real bid-ask, both
  sides), capital-cost change `Tλθ_i h_i`, **lending revenue** `r_save·δ·ΣB_q`, **borrowing cost**
  `r_borrow·δ·Σs^net_q`.
- **Horizon `T` = years remaining to FABN maturity.** Income/capital are valued over the life a
  holding would actually earn over (you hold unless something better appears), so a one-time trade
  cost is judged against horizon income — this is what makes worthwhile opportunities get taken
  instead of churning (1-day income could never repay a spread) or freezing.
- `λ = cost_of_capital × RBC_bar`. Constraints: budget, sell-cap `s_i≤h_prev_i`, **soft** duration
  band (breach beyond ±`eps_D` penalized at `dur_pen`, so the LP is always feasible), issuer cap,
  lending-facility recursion + PV-shortfall cap (quarterly grid to maturity).
- **Turnover control (`PARAMS`):** `kappa` scales the trading-cost hurdle (LP no-trade band; `>1`
  trades less); `reopt_every` re-optimizes every N days (hold between). `allow_post_fabn=True` lets
  the optimizer buy bonds maturing after the FABN (sold before maturity) — required for early-horizon
  feasibility (see *Previous issues* §3).

**Amortized-cost ledger.** After each solve, `y^bk_i = [(h_prev_i−s_i)y^bk_i + b_i y^mkt_i]/h_i`.
Matured bonds redeem at par (no spread) and their cash is redeployed (dynamic) or held at `r^F`
(static, net-zero spread → a static book *decays into cash* as bonds run off).

**Realized daily P&L** (accrual, separate from the decision objective; `Δ_k` = day length in years;
`e` = alive mask):
$$\text{Net}_k=\Delta_k\sum_i e\,h_{k,i}(y^{bk}_{k,i}-r^F)-\Delta_k\lambda\sum_i e\,\theta_i h_{k,i}-\sum_i\tau_{k,i}(b_{k,i}+s_{k,i})$$
Income accrues at the **locked** in-force yield; **facility interest is decision-shaping only**
(full-horizon), so it is *not* re-accrued daily (would double count). Dynamic vs static =
cumulative `Σ Net_k`; both start from cash on day 0 with the identical day-0 book (entry cost
cancels).

**Honest limitations (in the notebook):** IMR/AVR excluded → sale gains/losses not booked, so this
is a *conservative* test (forward book-yield pickup net of costs + run-off reinvestment, not
trading P&L). Prices treated as clean. The current-quarter facility bucket may include intra-quarter
past coupons (minor ALM approximation). Outcome is data-driven — if costs exceed the pickup, static
can win.

**Outputs:** cumulative net (dynamic vs static), in-force weighted book yield over time, daily
turnover + notional traded, and required capital over time. Plus **Section 5**: a **1A** turnover
diagnostic (yield-pickup distribution on swaps vs the horizon `T`) and a **1B** `kappa × reopt_every`
sweep with a dynamic-vs-static advantage heatmap.

---

## Previous issues — what was wrong, and what we fixed (June 2026)

**Symptom.** The Phase-2 daily backtest concluded **static beats dynamic by ~18%** ($22.7M vs
$27.8M) — the opposite of the capstone thesis. Three distinct problems sat behind that, plus
code-quality debt.

### 1. Over-trading produced a structurally bad result (the main one)
The daily solve values income over the full remaining horizon `T` but charges the bid-ask cost
*once*. With **daily** re-optimization at the **raw** bid-ask (`kappa=1`), marginal swaps with sub-5bp
pickup cleared the hurdle: ~26–37% of trade-days had <5bp pickup, the book churned **$22.8B notional**
and paid **$13.2M** turnover over 2y — swamping the yield pickup. Dynamic *always* lost, not because
re-optimization is bad but because it rebalanced far too often at full cost.
**Fix:** two feasibility-preserving LP levers — `kappa` (trading-cost hurdle) and `reopt_every`
(rebalance every N days) — plus a 1A diagnostic and a 1B sweep. **Result:** with moderate damping
(e.g. `reopt_every≈21`, `kappa≈2–5`) dynamic **beats static by ~+10–13%** with ~5× less turnover; only
daily+raw-cost loses.

### 2. Hold-to-maturity exclusion was inconsistent (silent bug)
The single-period optimizer excluded 175/303 bonds; the backtest excluded **0** — its quarter grid
`ALLQ` ends *at* FABN maturity, so "any bond cashflow in a quarter after the FABN's last quarter" was
always empty and the mask never fired. The two notebooks silently disagreed.
**Fix:** one shared, date-based rule — `maturity > FABN_MATURITY` — in both notebooks (184/303).

### 3. Fixing #2 exposed an early-horizon infeasibility (static then = $0)
Once the exclusion actually applied, only short bonds were buyable, so early in the backtest
(liability ~3.5y) the **hard duration band was unreachable → day-0 infeasible**. `solve_day` silently
returned "hold zeros", so the **static baseline collapsed to $0** and the comparison printed `+inf%`.
**Fix:** (a) **soft duration band** (`dur_pen`) — breach penalized, never infeasible; (b)
**`allow_post_fabn=True`** — buy post-FABN bonds (sold before they mature) so the duration band is
reachable again; (c) **loud feasibility reporting** (counts `STATUS_*_hold` days) + divide-by-zero
guards, so a broken baseline can never masquerade as `+inf%` again.

#### Why allowing bonds that mature after the FABN is prudent, not risky (actuary note)
An actuary's instinct is *"a bond maturing after my liability can't pay it — exclude it."* That strict
cash-flow-matching instinct is what broke the model, and excluding the bonds was actually the
**riskier** choice. Why allowing them is safe:
- **We never fund the liability from its principal.** These are liquid investment-grade corporates;
  before the FABN matures you **sell them in the secondary market**. The model only counts their
  *coupons* inside the horizon — the post-FABN principal is never used to meet a liability payment.
- **The final payment stays protected.** The lending-facility recursion + the **PV-shortfall cap
  (≤ 1% of liability PV)** force the book to hold enough bonds *maturing in time* to cover the ~$508M
  final payment. The optimizer cannot pile into long bonds and leave the liability unfunded.
- **It is *better* ALM, not worse.** The duration band exists so a parallel rate move moves asset and
  liability value together. Excluding every longer bond left only short assets that **could not reach
  the liability's duration** — that *under-hedges* the liability (the genuinely risky position) and is
  precisely why the early solve was infeasible. Adding the longer bonds back lets the portfolio
  actually match duration.
- **The result is stated conservatively.** We do **not yet book the sale gain/loss** on these bonds
  (IMR pending). The reported +10–13% edge counts only coupons earned while held — it does **not**
  rely on selling them at a profit. Proper IMR would, if anything, *improve* the dynamic result.
- **It mirrors real practice.** Insurers routinely hold assets longer than their liabilities and trade
  them; exact hold-to-maturity matching is not required — duration matching, liquidity, issuer
  concentration and capital limits are, and all of those still bind here.

Bottom line: the risk an actuary worries about — using a not-yet-matured bond to *pay* the liability —
is structurally prevented by the shortfall cap; allowing the bonds **improves** the duration hedge,
and the performance claim is deliberately conservative.

### 4. Code-quality / correctness hygiene
- Core math (book-yield IRR, modified duration, C-1, coupon/amort split) was **duplicated** across
  notebooks → extracted to `fabn_finance.py`, covered by **18 pytest tests**.
- C-1 lookup was O(N²) (`fixed.loc[...]` per bond) → vectorized.
- Silent data fills (IRR-failure fallback, tau median-fill) → now logged with counts.
- Dead code (overwritten `pd.date_range`) removed; blanket `warnings.filterwarnings("ignore")`
  narrowed to Deprecation/Future only.

**Net effect / what we've achieved.** The corrected, *valid* comparison is: the naive daily-full-cost
dynamic strategy loses ~18% purely on trading cost, but a **sensibly-paced dynamic strategy beats
static by ~+10–13% with ~5× less turnover** — the capstone thesis now holds, and we can explain
exactly why the naive version failed.

### 5. IMR — realized sale gains now recognized (Phase 2, implemented)
The backtest previously counted only coupon income (conservative — no credit for selling appreciated
bonds). **Section 6** now recognizes realized **rate-driven** gains/losses on sales via an Interest
Maintenance Reserve: `run_daily` carries a per-bond amortized-cost price (`cb_px`), books each sale's
gain to `fabn_finance.IMRLedger`, and amortizes it into `Net_k` over the sold bond's remaining life —
**never at the sale date** (no liquidation-proceeds inflation). It is a deliberate **accounting
consequence**, *not* a term in `solve_day` (putting raw gains in the objective would re-create the
gains-trading distortion IMR prevents). `use_imr=False` recovers the coupons-only run; Section 6 shows
no-IMR / IMR-in-window / IMR-fully-recognized side by side. The single-period optimizer needs no IMR
(one-shot allocation, no sales). **AVR** (credit-default reserve) remains out of scope. See
`METHODOLOGY.md` §5–6.

### Empirical findings (backtest 2024-03 → 2026-02, STEP=1; placeholders, illustrative)
- **Static baseline:** $27.76M cumulative net statutory income.
- **Base dynamic (daily, kappa=1) = worst case:** $22.66M no-IMR (−18.4%), $23.45M IMR-in-window
  (−15.5%), $26.26M IMR-fully-recognized (−5.4%). Daily full-cost rebalancing pays $13.2M turnover.
- **Tuned dynamic (reopt_every≈21, kappa≈2..5) = realistic pacing:** beats static by **~+10 to +15%**
  with **~5× less turnover** (~$1.5–3M). The 1B `kappa × reopt_every` sweep is green across most of the
  grid; only daily+raw-cost loses.
- **IMR adds ~$3.6M of harvested rate-driven gains**, but only ~$0.79M releases *within* the 2-year
  window (the rest amortizes over the sold bonds' remaining lives) — so a short backtest **understates**
  the IMR benefit; the *fully-recognized* line shows the ultimate effect.
- **Bottom line:** the capstone thesis holds — a sensibly-paced, constraint-aware re-optimizer beats
  static; the naive daily version loses purely on trading cost.

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
