# FABN Optimizer — Financial Methodology & Assumptions

Single reference for the financial math behind the FABN bond-portfolio optimizer, the
assumptions baked in, and the conservative/MVP simplifications (so reviewers see them as
deliberate choices, not oversights). Code lives in `fabn_finance.py` (pure, unit-tested in
`tests/`) and the three notebooks. See `CLAUDE.md` for the engineering map.

---

## 1. What we are optimizing

A bond portfolio backs a **Funding Agreement-Backed Note (FABN)**: the insurer owes a fixed
**3.205% semi-annual coupon** on $500M, issued 2022-09-06, maturing **2027-09-06**. We invest the
$500M in bonds that earn more than 3.205%, match the liability's interest-rate sensitivity, respect
regulatory capital (NAIC RBC), and produce cash when liability payments fall due.

Accounting basis is **SAP (Statutory Accounting Principles)**: bonds are held at **amortized cost**,
so earnings are accrual **book yield**, not mark-to-market.

---

## 2. Core formulas (each with its code home)

| Quantity | Formula | Code |
|---|---|---|
| **Book yield** `y_i` | effective-interest IRR: solve `Σ_t CF_t (1+y)^(-t) = P/100` | `fabn_finance.book_yield` |
| **Coupon yield** `coupon_inc` | `annual_coupon / (price/100)` (current yield) | `fabn_finance.coupon_amort_split` |
| **Amortization** `amort_inc` | `book_yield − coupon_inc` (residual) | `fabn_finance.coupon_amort_split` |
| **Macaulay duration** | `Σ_t t·PV(CF_t) / Σ_t PV(CF_t)` | `fabn_finance.macaulay_duration` |
| **Modified duration** | `Macaulay / (1+y)` | `fabn_finance.modified_duration` |
| **C-1 capital charge** `θ_i` | NAIC rating → factor (S&P → Moody's → BBB default) | `fabn_finance.lookup_c1` |
| **Transaction cost** `τ_i` | `(ask − bid) / (2·mid)` (relative half-spread) | pipeline §9.5 / backtest §1 |
| **Capital cost rate** `λ` | `cost_of_capital × RBC_bar` (= 0.08 × 1.5 = 0.12) | both optimizers |

### Amortization / accretion — rationale
Under SAP a bond is carried at amortized cost and glided to **par** by maturity. A **premium** bond
(price > 100) returns part of each coupon as your own capital → `amort_inc < 0`; a **discount** bond
accretes toward par → `amort_inc > 0`. The identity `book_yield = coupon_inc + amort_inc` holds by
construction. The code uses a **constant-yield approximation**: one rate for the bond's life (exact at
purchase). The textbook effective-interest method recomputes `B_{t-1}·y − coupon` each period; the
difference is second-order over the MVP horizon. (Unit-tested: par→amort≈0, premium→<0, discount→>0.)

---

## 3. The SAP objective (single-period, `FABN_Optimizer_SAP.ipynb`)

Maximize, over allocations `h_i ≥ 0` (dollars, long-only):

```
Σ_i (y_i − r_FABN)·h_i        statutory NII (net of funding)
  − λ · Σ_i θ_i·h_i           cost of required capital
  − Σ_i τ_i·(tc⁺_i + tc⁻_i)   turnover (real bid-ask, both sides)
  − η · Σ_q DF_q·s_net_q      PV of lending-facility shortfall
  + r_save·δ · Σ_q B_q        surplus reinvestment income
```

**Headline metric:** statutory NII ÷ required capital (`RBC_bar · Σ θ_i h_i`).

Constraints (all linear): budget `Σh = H`; duration band `|Σ D_i h_i − D_FABN·H| ≤ eps_D·H`; turnover
decomposition; lending-facility recursion; PV-shortfall hard cap (`≤ phi_sf·PV(L)`); issuer cap
(`≤ delta·H`); hold-to-maturity exclusion (§5).

**Linearizations:** `|x| = d⁺ + d⁻` with `x = d⁺ − d⁻`, both `≥ 0`; `max(0,x)` via a non-negative slack.

---

## 4. The dynamic backtest (`FABN_Optimizer_SAP_Backtest.ipynb`)

Re-optimizes each trading day via a **buy/sell decomposition** `h_i = h_prev_i + b_i − s_i`
(`b_i ≥ 0`, `0 ≤ s_i ≤ h_prev_i`). Retained lots keep their **locked** book yield `y_book`; new buys
enter at the day's **market** yield `Y[d]`. Income/capital are valued over horizon `T` (years to FABN
maturity), so a one-time trade cost is weighed against the income a holding would actually earn —
this is the swap trigger (true pickup minus the yield given up), and it is what prevents both churning
and freezing.

**Realized daily P&L** (separate from the decision objective; accrued at the locked yield):
```
Net_k = Δ_k·Σ_i h_{k,i}(y_book_{k,i} − r_FABN) − Δ_k·λ·Σ_i θ_i h_{k,i} − Σ_i τ_i(b+s)
```
Facility interest is **decision-shaping only** (valued full-horizon in the objective), so it is **not**
re-accrued daily (that would double-count). Matured bonds redeem at par and their cash is redeployed
(dynamic) or held at `r_FABN` (static).

### Turnover control (Section 5 of the notebook)
- **`kappa`** scales the trading-cost hurdle inside the LP (no-trade band; `kappa>1` ⇒ fewer trades).
- **`reopt_every`** re-optimizes every N days instead of daily.
Both stay inside the LP — post-hoc zeroing of small trades is *avoided* because it breaks the budget
and duration constraints. The 1A diagnostics quantify whether trades chase real pickup or tiny wiggles.

---

## 5. Hold-to-maturity exclusion (unified rule)

A bond is **post-FABN** if its **maturity > FABN_MATURITY**. Both notebooks share this single
date-based definition. *Previously inconsistent:* the single-period notebook excluded 175/303 via a
cashflow-grid test, while the backtest excluded **0** because its quarter grid was truncated at FABN
maturity (the grid-based test could never fire). The date rule fixes that and makes the two agree
(184/303 post-FABN at the 2024-03 universe).

**Backtest relaxation (first half of Phase 2, implemented).** Excluding post-FABN bonds left only short
bonds, so early in the backtest (liability ~3.5y) the duration band was **unreachable → day-0
infeasible → static baseline collapsed to $0**, invalidating the dynamic-vs-static comparison. Two
feasibility-preserving changes in `solve_day`:
- **`allow_post_fabn`** (default **True**) lets the optimizer buy post-FABN bonds (sold before they
  mature). Their principal lands after the grid, so the facility + PV-shortfall cap still force enough
  in-horizon maturities to fund the final liability. Booking the eventual sale gain (IMR) is the
  *second* half of Phase 2.
- **Soft duration band** (`dur_pen`): breach beyond ±`eps_D` is allowed but penalized, so the LP is
  always feasible and only bends the band when genuinely forced (breach vars are 0 when the hard band
  is reachable → identical to before).

The single-period `FABN_Optimizer_SAP.ipynb` stays **strict** (hard band, post-FABN excluded): at its
2025-01-15 date the liability is short enough that the hard band is feasible, so no relaxation is
needed there.

### Why allowing bonds that mature after the FABN is prudent, not risky (actuary note)

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
  (IMR pending, §6). The reported +10–13% edge counts only coupons earned while held — it does **not**
  rely on selling them at a profit; proper IMR would, if anything, *improve* the dynamic result.
- **It mirrors real practice.** Insurers routinely hold assets longer than their liabilities and trade
  them; exact hold-to-maturity matching is not required — duration matching, liquidity, issuer
  concentration and capital limits are, and all of those still bind here.

Bottom line: the risk an actuary worries about — using a not-yet-matured bond to *pay* the liability —
is structurally prevented by the shortfall cap; allowing the bonds **improves** the duration hedge,
and the performance claim is deliberately conservative.

---

## 6. IMR / AVR (Phase 2)

Realized gains/losses on sales are currently **excluded** (conservative test — dynamic pays trading
costs but is not credited for selling at a gain). Phase 2 adds proper **IMR**: a realized rate-driven
gain goes into an IMR balance and is **amortized into income over the sold bond's remaining life** —
**never booked in full at sale** (doing so would overstate earnings, the same anti-pattern as crediting
discounted future cashflows as sale proceeds). **AVR** (credit/default-driven reserve) is out of scope
for the MVP.

**Implemented (backtest Section 6).** The recognition is now wired into `run_daily`:
- `fabn_finance.IMRLedger` holds realized gains and releases them straight-line over each lot's
  remaining life; `realized_gain_on_sale`, `amortize_price_to_par`, and `blend_cost_basis` compute the
  cost basis. All unit-tested, incl. the conservation identity `Σ released = Σ gains`.
- `run_daily` carries a per-bond amortized-cost price `cb_px` (pulled to par over life, blended on
  buys); on each sale it books `sold$ × (mid − cb_px)/cb_px` to the IMR and adds the **daily release**
  to `Net_k`. `use_imr=False` recovers the conservative coupons-only run for comparison.
- **Design choice (consequence, not driver):** IMR is *not* a term in the `solve_day` objective. The
  decision stays on economic book-yield pickup; IMR only re-times recognition in the reported P&L.
  Putting raw gains in the objective would re-introduce the gains-trading distortion IMR exists to
  prevent (see *§Why IMR shouldn't drive the decision* in the design notes / CLAUDE.md).
- **Single-period optimizer:** IMR is **not** added there — it is a one-shot allocation from cash with
  no sales over time, so there are no realized gains to recognize.
- Section 6 reports three lines — dynamic *no-IMR*, *IMR released in-window*, and *IMR fully
  recognized* — plus graphs of the IMR balance and realized-vs-recognized gains.

---

## 7. Assumptions & placeholders (CONFIRM WITH ATHENE)

| Parameter | Value | Status |
|---|---|---|
| `H` (budget) | $500M | placeholder |
| `C_curr`, `C_min` | $5M, $1M | placeholder |
| `RBC_bar` | 1.5 | placeholder |
| `h_curr` (current book) | equal-weight `H/N` | **placeholder** — real starting book needed; turnover in the single-period optimizer is measured against this |
| `cost_of_capital` | 8% | assumption (WACC) |
| `r_borrow` | 5% | assumption |
| `eps_D`, `delta`, `phi_sf` | 0.3 yr, 5%, 1% | tunable policy |

Other conventions: cashflows are per-100 face in BigQuery (pipeline divides by 100 → per $1 face);
mid price is the book/purchase value; FRED Treasury curve has a static fallback if the network fails;
issuer = first 6 CUSIP chars; prices treated as clean (no accrued-interest separation).

---

## 8. How the math is verified

`pytest tests/` covers: par/premium/discount book yield and the IRR round-trip; zero-coupon modified
duration `= T/(1+y)`; the `book_yield = coupon_inc + amort_inc` identity and amort signs; C-1 lookup
incl. Moody's fallback and BBB default; (Phase 2) the IMR amortization identity `Σ released = Σ gains`.
`pytest "Size of the Prize/tests/"` adds the Phase-3 arc-economics checks (single-arc identity vs the
backtest accrual, IMR-window conservation, upper-bound sanity, cash-conservation feasibility).
See the plan's Test Plan for the in-notebook invariant/accounting/behavioral checks (budget, duration
band, cash-conservation reconciliation, and the `τ→0 ⇒ dynamic≥static`, `τ→∞ ⇒ dynamic→static`
monotonicity tests).

## 9. Size of the Prize — perfect-foresight upper bound (Phase 3, `Size of the Prize/`)

**Question.** With the full 2-year price path known in advance, what is the maximum cumulative SAP NII
— carry **plus** IMR-recognized trading gains, net of bid-ask/2 — achievable under the same
constraints? This is a **ceiling**, not a strategy; the gap to the realistic dynamic backtest is the
"size of the prize" (does the problem have tradeable upside worth pursuing?).

**Formulation (time-expanded trade-arc LP).** Perfect foresight makes each trade
`a = (bond i, buy node m, close node n)` carry a *constant* per-dollar profit, which keeps SAP
book-yield **locking** linear:

- `net_carry_a = ((Y[m,i] − r_FABN) − λ·θ_i)·(t_n − t_m)` — income at the **locked** purchase yield,
  net of the capital charge (λ = `cost_of_capital·RBC_bar`), over the holding span.
- `imr_window_a` — the realized rate-driven gain at the sale (`amortize_price_to_par` basis →
  `realized_gain_on_sale`), recognized straight-line over the sold bond's remaining life, counting
  only the portion released **inside the window** (`imr_full_a` = the ultimate gain). Held-to-maturity
  arcs redeem at par: no sell cost, no gain.
- `cost_a = τ[m,i] (+ τ[n,i] if sold)` — bid-ask/2 on each traded leg.

Decision `x_a ≥ 0` = dollars of **book value**, **conserved** across grid nodes (a dollar freed when an
arc closes can only then fund a new buy). This is the SAP `Σh = H` invariant and the key discipline:
realized gains flow into income via the IMR and are **never** added back to redeployable principal — no
liquidation-proceeds inflation. Objective `max Σ coef_a·x_a` (`coef_a = net_carry + imr_window − cost`)
s.t. soft duration band, issuer cap, capital-in-objective, and (optional) the quarterly facility +
PV-shortfall cap. Code: `prize_foresight.py` (`build_arcs`, `solve_prize`), reusing `fabn_finance`.

**Why the answer is mostly trading gains, not carry.** IMR amortizes a gain over the sold bond's
remaining life, so naive *symmetric* gains-trading is a wash. But the 2024–26 path had large
**directional** rate moves: with foresight you systematically buy before prices rise / sell at the top,
and a large slice is recognized in-window. Empirically carry is ~identical static vs dynamic; the prize
is rotation-timing IMR. A dollar of NII and a dollar of (windowed) IMR are weighted **1:1** in the
objective; to prefer recurring NII, weight the IMR term by `α<1` (`coef = net_carry + α·imr_window −
cost`), which also damps over-trading.

**Tractability & honesty.** Arcs grow `O(N·P²)` in grid nodes `P`; full-universe daily (`P≈498`,
~37M arcs) is intractable, so `build_arcs(max_hold_nodes=L)` caps the sell horizon → `O(N·P·L)`. The
prize **does not plateau** with grid refinement, and the model charges **only bid-ask/2 with no market
impact** — so fine grids (esp. daily) are upper-bound **artifacts** (daily L=10 churns ~100× book).
The defensible figures are monthly/weekly; **market-impact / capacity cost** is the natural next
extension. See `Size of the Prize/RESULTS.md` for the numbers and `prize_theory.md` for the rationale.
