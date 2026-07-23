# Optimization Reference — FABN SAP Optimizer

> **Audience:** an AI agent (or engineer) that needs deep, exact context on how the
> portfolio optimization is formulated, why each piece exists, and what breaks if you
> change it. Everything below is grounded in the actual implementation. Source of truth:
> `backend/services/optimizer_service.py` and `Optimization/fabn_data_pipeline.py`.
>
> **Two-state document.** **[CURRENT]** describes code that runs today (pay-fixed swap overlay,
> CVaR-governed risk, open bond universe). **[RETIRED]** describes mechanics that were live
> before the Step 1-4 redesign shipped and have since been replaced (the held-to-maturity
> exclusion, the PV-shortfall cap, the receive-fixed swap, the hard duration band) — kept for
> context on why the design changed, not as current behavior. **[PLANNED]** describes further
> redesign work (credit-risk budgets, swap turnover cost, explicit reinvestment policy) not yet
> implemented (see `swap_intuition_lab/` and `docs/agent-context/duration-swaps-reference.md`).
> When sections disagree, the code is authoritative for *what runs*.

---

## 0. What is being optimized, in one paragraph

A **FABN (Funding Agreement-Backed Note)** is an institutional funding instrument: the
insurer issues a note to investors and, in exchange, owes them a fixed **crediting rate**
(`r_FABN`, the note coupon = 3.205%) plus principal at maturity (issued 2022-09-06, matures
2027-09-06). The proceeds — the budget `H = $500,000,000` — are invested in a portfolio of
corporate bonds. **The FABN is the liability; the bond portfolio is the asset.** The insurer
profits from the *net spread* between what the assets earn and `r_FABN`, subject to statutory
(SAP) accounting, regulatory capital (NAIC C-1 / RBC), and the requirement that asset cash
flows fund the FABN's cash flows on time. The optimizer chooses the dollar allocation to each
bond and a pay-fixed interest-rate swap overlay to **maximize risk-adjusted statutory
profit** subject to those constraints, with a CVaR tail-loss budget as the primary risk control.

The model is a **Linear Program (LP)** solved with **Gurobi** (`_solve`,
`optimizer_service.py:167`).

---

## 1. Objective function

**[CURRENT]** The objective is the **SAP** (Statutory Accounting Profit) expression built at
`optimizer_service.py:294-301`:

```
maximize  SAP = NII − capital_cost − turnover_cost
                + savings_income + swap_NII − swap_RBC
```

`liq_penalty` is **[RETIRED]** as an objective term — it is still computed as a diagnostic
(reported, e.g. for the honest PV-shortfall figure) but no longer subtracted; risk is governed
by the CVaR constraint in §2 instead. Every remaining term is **linear in the decision
variables** (dollars). Definitions:

| Term | Formula (as coded) | Units | Economic meaning |
|---|---|---|---|
| `NII` | `Σ_i (book_yield_i − r_FABN) · h_i` | $/yr | Net investment income: the annual book-yield spread of each bond over the FABN crediting rate, times dollars held. This is the core profit engine. |
| `capital_cost` | `lambda_cap · Σ_i theta_i · h_i` | $/yr | Cost of the regulatory capital the assets consume. `theta_i` = NAIC C-1 factor (credit charge). `lambda_cap = cost_of_capital · RBC_bar` (`:219`). |
| `turnover_cost` | `Σ_i tau_i · (tc⁺_i + tc⁻_i)` | $ | Transaction cost of trading away from the current book. `tau_i = tau_raw_i · 10` (bid-ask half-spread, scaled). `tc⁺/tc⁻` = dollars bought / sold. |
| `[RETIRED] liq_penalty` (diagnostic only) | `eta · Σ_q df_q · s_net_q` | $ | Used to be a penalty for any quarter where asset cash inflow falls short of the FABN outflow. Still computed and reported, no longer in the objective. |
| `savings_income` | `r_save · dt_q · Σ_{q<Q-1} B_q` | $ | Income earned on surplus cash parked in the lending facility. `r_save = 0.0 · lambda_w = 0.0` always — the facility base rate was zeroed (Step 3, "no free parking"), so this term is currently always 0 and `lambda_w` is a no-op. |
| `swap_NII` | `Σ_k (c_swap_k − r_float) · v_k` | $/yr | Net carry of the interest-rate swap overlay (`:301`). **[CURRENT]** pay-fixed, priced at-the-money (`c_swap_k = r_float`), so this term is ~0 by construction — the swap's value is the hedge, not carry. |
| `swap_RBC` | `lambda_cap · mu_swap · Σ_k v_k` | $/yr | Capital charge on swap notional (`mu_swap = 0.002`, a small C-3 proxy). |

Where `book_yield_i` is the effective-interest IRR of bond *i* (`fabn_finance.book_yield`,
solving `Σ_t CF_t (1+y)^(-t) = price/100`), `r_FABN` = FABN coupon, and
`nii_rate_i = book_yield_i − r_FABN` (`:243`).

**Economic reading:** maximize spread income, *minus* the cost of the capital that income ties
up, *minus* trading friction, *plus* reinvestment income (currently always 0), *plus* the
swap's net carry (currently ~0, at-the-money) and capital. Risk is governed separately by the
CVaR constraint (§2), not by a term in this objective.

---

## 2. Constraints

Decision variables (`:234-246`):

| Symbol | Code | Meaning |
|---|---|---|
| `h_i` | `h[i]`, `lb=0` | Dollars allocated to bond *i* (i = 1..N). |
| `v_k` | `v[k]`, `lb=0` | Notional of swap *k* (k = 1..K, K=3 tenors). |
| `d⁺, d⁻` | `d_pos, d_neg` | Duration-gap slack above/below target. |
| `tc⁺_i, tc⁻_i` | `tc_plus[i], tc_minus[i]` | Dollars bought / sold vs `h_curr`. |
| `B_q` | `B[q]`, `lb=0` | Lending-facility (surplus cash) balance at quarter *q*. |
| `s_net_q` | `s_net[q]`, `lb=0` | Funding shortfall in quarter *q*. |

### 2.1 Constraint table **[CURRENT]**

| # | Name (code) | Formula | Plain English | Rationale — why it exists | If loosened / removed |
|---|---|---|---|---|---|
| C1 | **Budget** (`:308`) | `Σ_i h_i = H` | Invest exactly the full \$500M of proceeds, no more, no less. | The FABN proceeds are a fixed pot; you must deploy all of it (idle cash earns nothing and still owes `r_FABN`), and you cannot invest money you do not have. | Removing `=` for `≤` lets the model under-invest, dodging risk while still owing the liability — spurious "profit". Over-investing implies phantom leverage. |
| C2 | **[RETIRED as hard bound] Duration band** (`:311-318`) | `Σ_i durs_i·h_i + Σ_k swp_dur_k·v_k − D_FABN·H = d⁺ − d⁻`, with `d⁺ ≤ eps_D_eff·H`, `d⁻ ≤ eps_D_eff·H` | Keep the *dollar-weighted asset duration* within `eps_D_eff` years of the FABN's duration `D_FABN`. | Used to immunize **surplus** against parallel rate moves. Now relaxed to an inert `eps_D_eff = 100yr` band whenever CVaR is active (always, currently) — the gap is still reported for information, it just never binds. CVaR (C9 below) governs risk instead. | The `eps_D` request param is still accepted but has no effect while CVaR is active. |
| C3 | **[RETIRED] HtM exclusion** | Formerly, for each *i* with `maturity_i > FABN_maturity`: `h_i.ub = 0` | Used to forbid holding any bond that matures *after* the FABN. | A bond maturing after the note cannot return principal in time to repay the note; it would have to be **sold** at maturity at an unknown price. Banning them guaranteed self-liquidation. | **Removed.** The forced-sale price risk this used to prevent by fiat is now controlled by the CVaR constraint (C9) and the pay-fixed swap overlay instead. `post_fabn_mask` is still computed for diagnostics/reporting but no longer bounds `h_i`. |
| C4 | **Turnover decomposition** (`:320-322`) | `h_i − h_curr_i = tc⁺_i − tc⁻_i` | Split each position change into a buy leg and a sell leg (both ≥ 0). | Makes the traded amount `|h_i − h_curr_i|` linear so the `turnover_cost` term can price it. Purely structural (enables C-cost, not a limit). | Not a risk limit; if dropped the objective can't see trading cost and will churn the book. |
| C5 | **Facility dynamics** (`:324-335`) | `B_q − s_net_q = (1+r_save·dt_q)·B_{q−1} + CF^A_q + CF^{swap}_q − CF^L_q` (with `B_{-1}=0`) | Roll a cash account quarter by quarter: prior balance grown at `r_save` (currently always 0), plus asset & swap cash in, minus FABN cash out. Surplus → `B_q`; shortfall → `s_net_q`. | Ties the *timing* of cash to the model. This is the cash-flow-matching mechanism; the facility is retained as a buffer even though its surplus no longer earns anything and its shortfall is no longer hard-capped (C6). | If the facility recursion is dropped there is no representation of *when* cash arrives — the model could "fund" a Q1 outflow with a Q8 coupon. |
| C6 | **[RETIRED] PV shortfall cap** | Formerly `Σ_q df_q · s_net_q ≤ phi_sf · PV_liability`, `phi_sf = 0.01` | Used to require the present value of all cumulative funding shortfalls to stay under 1% of the liability's PV. | Was a hard solvency guardrail bridging small timing mismatches. | **Removed** (Step 4) — CVaR (C9) governs risk instead. `PV_liability` and the shortfall PV are still computed and reported as diagnostics; `phi_sf` is kept in code only as a deprecated marker, no longer used in any constraint. |
| C7 | **Issuer concentration** (`:344-352`) | For each issuer *g*: `Σ_{i∈g} h_i ≤ effective_delta · H`, `effective_delta = min(w_max, 1/n_min)` | No single issuer (CUSIP prefix) exceeds a small fraction of the book; forces ≥ `n_min` names. | Diversifies idiosyncratic default/credit risk; a mandate/prudence rule. `n_min = 20` ⇒ at least ~20 distinct issuers. | Loosen → concentration risk (one default hurts more). Remove → the LP piles into the single highest-SAP issuer. |
| C8 | **Swap notional cap** (`:354-358`) | `Σ_k v_k ≤ v_max_frac · H`, `v_max_frac = 0.20` | Total swap notional ≤ 20% of the book. | Bounds derivative leverage, counterparty exposure, and variation-margin liquidity draw. | Loosen → larger hedge / larger collateral swings; remove → unbounded notional, model can take large pay-fixed rate positions. |
| C9 | **[CURRENT] CVaR tail-loss limit** (`:360-369`) | `ζ + 1/((1−α)S)·Σ_ω z_ω ≤ φ_cvar·H`, with `z_ω ≥ loss_ω − ζ`, `z_ω ≥ 0`, `loss_ω = Σ_i cvar_relloss[ω,i]·h_i + Σ_k swp_dur_k·cvar_d_rate[ω]·v_k` | Cap the average forced-sale loss (book-vs-market, from historical rate/spread shock scenarios) in the worst `(1−α)` tail of scenarios, to at most `φ_cvar·H`. | The **primary risk control**, replacing C2 (duration band) and C6 (PV-shortfall cap). A Rockafellar–Uryasev linearization of a coherent risk measure — directly bounds the forced-sale loss that C3 (HtM ban) used to prevent by fiat, and stays LP-representable. | `α = 0.95` (`cvar_alpha`), `φ_cvar` request param (default 0.01, tighter = stricter risk budget, fewer/shorter-duration eligible bonds). Scenarios come from `fabn_data_pipeline.py`'s historical shock-scenario section. |

**Non-negativity** (`lb=0`) on `h, v, B, s_net, tc±` are bounds, not rows: no short bonds, no
negative swap notional, no negative cash balance, no negative shortfall.

### 2.2 What changed in the Step 1-4 redesign, and what's still [PLANNED]

The swap-overlay redesign (see `duration-swaps-reference.md` and `swap_intuition_lab/`) is
**live** as of the changes described above. Summary of what happened, and what's still ahead:

| Change | Constraint | What & why | Status |
|---|---|---|---|
| **DELETE** | **C3 HtM exclusion** | Removed the blanket ban on post-FABN bonds so the book can hold longer, higher-spread credit. The forced-sale risk this ban prevented is instead controlled by the CVaR constraint (C9). | **[CURRENT]** — done. |
| **FLIP** | **Swap direction in C2 & objective** | Swaps changed from **receive-fixed** (`swp_dur > 0`, *added* duration) to **pay-fixed** (`swp_dur < 0`, *subtracts* duration), priced at-the-money. This lets a long-duration bond book be pulled back toward `D_FABN`: net duration `= Σ durs_i h_i − |swp_dur_k| v_k`. | **[CURRENT]** — done. |
| **ADD** | **CVaR on MV/BV** | A Rockafellar–Uryasev tail-loss limit on the relative market-value-vs-book loss. See C9 above. | **[CURRENT]** — done, replaces C2 as the binding risk control. |
| **ADD** | **Credit-risk budgets** | Explicit linear budgets beyond CVaR: spread-duration `Σ durs_i h_i ≤ D̄_s·H`, rating floor `Σ g_i h_i ≤ ḡ·H`, WAL cap `Σ T_i h_i ≤ WAL̄·H`, liquidity `Σ_{maturity>FABN} h_i ≤ ℓ̄·H`. | **[PLANNED]** — not yet implemented; CVaR alone currently governs how far the model can extend into long/risky bonds. |
| **ADD** | **Swap turnover** | On rebalance, penalize `|Δv_k|` (change in swap notional) in the objective, exactly like bond turnover (C4), so the hedge is not churned each period. See duration-swaps reference §4. | **[PLANNED]** — not yet implemented; this is a single-period (not rebalancing) optimizer today. |
| **CHANGE** | **Reinvestment policy** | Make the reinvestment rule for returned principal explicit, rather than the current `r_save = 0.0` (no reinvestment income at all). | **[PLANNED]** — `r_save`'s base rate is currently hardcoded to 0.0; `lambda_w` is wired but has no effect until this changes. |

---

## 3. Why this formulation (design rationale)

- **Why an LP (linear, not quadratic/MILP).** Every term above is linear in `(h, v, aux)`.
  A linear program is globally optimal, fast, and returns **dual values / reduced costs**
  (`h[i].RC`) — the marginal SAP of relaxing each constraint. That interpretability
  is the point: the model can tell you the *price* of each limit (e.g., "the last \$1M of the
  CVaR budget costs X bps of spread"). A quadratic (mean-variance) objective would lose the
  clean shadow prices; the **CVaR** risk measure (C9, live) was specifically chosen because it
  is *coherent* **and** stays linear (Rockafellar–Uryasev), unlike variance (QP) or VaR
  (non-convex). See duration-swaps reference and `swap_intuition_lab` §11.
- **Why dollars as decision variables** (not weights). The budget is a fixed dollar pot and
  the liability, capital charges, and cash flows are all dollar quantities; working in dollars
  keeps every constraint in natural units and avoids a nonlinear renormalization.
- **Why Gurobi.** Industrial LP/MILP solver; handles the ~N+K+aux variables and the per-quarter
  facility recursion instantly, and exposes duals. Called off the FastAPI event loop via
  `asyncio.to_thread` (`optimizer_service.py:14`).
- **Why book yield (not market yield) in NII.** The insurer reports on **statutory /
  amortized-cost** accounting; income is the *book* yield, not mark-to-market. This is also why
  realized rate gains flow through the **IMR** (`fabn_finance.IMRLedger`) rather than hitting
  income at once.

---

## 4. Worked examples

### Example A — [RETIRED] a 3-bond toy solve under the old hard-constraint rules

This example uses the **retired** rule set (hard duration band, hard HtM ban) to illustrate the
problem the redesign solves. It does not reflect current behavior — see Example B for the live
mechanics.

Scale everything down: budget `H = $300`, target duration `D_FABN = 3.0`, `eps_D = 0.4`,
`r_FABN = 3.2%`, `w_max` large enough to ignore, one issuer each. Three bonds:

| Bond | book_yield | duration | theta (C-1) | matures after FABN? |
|---|---|---|---|---|
| A (2y) | 4.0% | 1.9 | 0.008 | no |
| B (5y) | 4.8% | 4.4 | 0.010 | no |
| C (10y) | 5.8% | 7.8 | 0.015 | **yes** |

Take `lambda_cap = 0.15 · 1.5 = 0.225`. Ignore turnover/facility for intuition.

1. **C3 (HtM)** immediately sets `h_C ≤ 0` — bond C is *banned* because it matures after the
   FABN. So under these **[RETIRED]** rules we could only use A and B.
2. **C1 (budget):** `h_A + h_B = 300`.
3. **C2 (duration):** `1.9·h_A + 4.4·h_B` must land in `[300·(3.0−0.4), 300·(3.0+0.4)] =
   [780, 1020]`.
4. **Objective per dollar** (NII − capital): `A: (0.040−0.032) − 0.225·0.008 = 0.0080 −
   0.0018 = 0.0062`; `B: (0.048−0.032) − 0.225·0.010 = 0.0160 − 0.00225 = 0.01375`. B is far
   more profitable, so the LP wants as much B as possible.
5. **Binding constraint:** pure profit wants all B (`h_B=300`), giving duration
   `4.4·300 = 1320 > 1020` — violates C2's upper band. So C2 binds: solve
   `1.9·h_A + 4.4·h_B = 1020` with `h_A+h_B=300` → `h_A ≈ 96`, `h_B ≈ 204`. Portfolio duration
   sits at the **top of the band (3.4y)** because more duration = more of the high-yield bond
   = more SAP.
6. **Output:** `h ≈ (96, 204, 0)`; SAP `≈ 96·0.0062 + 204·0.01375 ≈ $3.40/yr`. The duration
   band is the *active* constraint and its shadow price tells you how many dollars of SAP the
   last year of duration tightness costs.

**What this teaches:** the duration band, not the budget, is what caps profit here — and it does
so by *excluding the long, high-yield bond twice* (once via C3's ban, once via C2's cap).

### Example B — [CURRENT] the same solve with pay-fixed swap + no HtM ban

This reflects the live rules: C3 is gone and a **pay-fixed** swap is available, `swp_dur = −4.5`
per \$1 notional (a ~5y swap), capped at `v ≤ 0.20·H = 60`. (In place of the hard duration band
this example still uses for illustration, the live system's actual governing constraint is CVaR
— see C9 in §2.1.)

1. C3 gone → **bond C is now allowed**. Its per-dollar SAP `(0.058−0.032) − 0.225·0.015 =
   0.0260 − 0.0034 = 0.0226` beats A and B.
2. The LP wants to load C, but `4.4`/`7.8` durations blow C2. **The swap absorbs duration:** net
   duration `= (1.9 h_A + 4.4 h_B + 7.8 h_C)/H − 4.5·v/H`. Buying `v` pay-fixed *subtracts*
   duration, so the book can hold long bonds and still land in `[2.6, 3.4]`.
3. Solve (schematically): put most of `H` into C, size `v` so net duration = 3.4 (band top).
   With `h_C ≈ 300`, gross duration `7.8`; to reach 3.4 net you need
   `v ≈ (7.8 − 3.4)/4.5 · 300 ≈ 293` — but `v ≤ 60`, so the **swap cap C8 now binds** and you
   can only knock duration down to `7.8 − 4.5·60/300 = 6.9`. That still violates C2.
4. **Consequence:** with a 20% swap cap you cannot fully hold the 10y bond duration-neutral;
   the optimum is a mix (some C, some shorter bonds, swap at the cap). And *because* C2 no
   longer restrains how risky the bonds get, the **CVaR constraint** and the credit budgets
   (§2.2) become the binding risk limits — they stop the model from farming spread into the
   longest, lowest-rated names. This is exactly the intended redesign.

**What this teaches:** removing C3 and adding a pay-fixed swap *unlocks* long-bond spread, but
transfers the governing role from "duration band + HtM ban" to "swap cap + CVaR + credit
budgets." Loosen the swap cap and CVaR takes over as the true leash.

---

## 5. Frequently needed context (FAQ)

**Q: Why is `h_i` bounded at `w_max·H` (and issuers at `effective_delta·H`)?**
Diversification (C7). `effective_delta = min(w_max, 1/n_min)` (`:201`) makes the per-issuer cap
tight enough to *force* at least `n_min` (=20) distinct issuers. Raising `w_max`/lowering
`n_min` concentrates the book.

**Q: What does it mean if the solver returns `infeasible`?**
`_solve` returns `{"status":"infeasible"}`. It means no `h,v` can satisfy *all* constraints at
once. Usual causes, in order of likelihood: (a) **CVaR budget too tight** (`phi_cvar` small)
given the available bonds' loss profile under the historical shock scenarios; (b) concentration
(`n_min`) too high for the eligible universe; (c) the swap notional cap (`v_max_frac`) too small
to bring the CVaR loss under budget. The retired PV-shortfall cap and hard duration band are no
longer possible infeasibility causes, since neither is enforced anymore. Debug by loosening one
constraint at a time (widen `phi_cvar`, lower `n_min`, raise `v_max_frac`).

**Q: How does changing `eps_D` ripple through?**
`eps_D` is the half-width of the duration band (C2), but C2 is currently **[RETIRED as a hard
bound]** — relaxed to an inert 100yr band while CVaR governs. Changing `eps_D` today has **no
effect** on the solve; the duration gap is still computed and reported for information, but
CVaR (`phi_cvar`, C9) is the parameter that actually shapes risk.

**Q: How does `gamma_w` (cost of capital) change the answer?**
`gamma_w` scales `lambda_cap = gamma_w · RBC_bar` (`:219`), which multiplies every bond's C-1
charge in the objective. Higher `gamma_w` → capital-heavy (low-rated / high-`theta`) bonds get
penalized more → the book tilts toward higher-quality names even at lower yield.

**Q: What is `r_save` / `lambda_w`?**
`r_save = 0.0 · lambda_w = 0.0` always — the facility's base reinvestment rate was zeroed (Step
3, "no free parking"), so surplus cash currently earns nothing regardless of `lambda_w`.
`lambda_w` is kept as a wired-but-inert request parameter, pending the **[PLANNED]** explicit
reinvestment-policy redesign that would give it a non-zero base rate to scale again.

**Q: How does `phi_cvar` change the answer?**
`phi_cvar` (default 0.01) is the CVaR risk budget (C9): the worst-5% average forced-sale loss
must stay under `phi_cvar · H`. Lower `phi_cvar` → tighter risk budget → the optimizer favors
shorter-duration, less rate-sensitive bonds and/or more swap hedging; too low → infeasible.
Higher `phi_cvar` → more room to hold long, high-spread (including post-FABN-maturity) bonds.
This is now the primary risk-facing hyperparameter, replacing `eps_D`'s old role.

**Q: Where do `book_yield`, `durs`, `theta` come from?**
The pipeline (`fabn_data_pipeline.py`) computes them via `fabn_finance`: `book_yield` = IRR
solve, `durs` = modified duration, `theta` = NAIC C-1 factor by rating. They are *inputs* to the
LP, fixed per date.

**Q: Why can SAP be dominated by so few bonds?**
Because it is linear, the LP pushes to the vertices — it buys the highest per-dollar-SAP bonds
until a constraint (duration band, concentration, budget) binds. The binding constraints, not
the objective, determine the shape of the book. Reduced costs (`h[i].RC`) rank the rest.

**Q: Where does the swap enter today vs. what's still planned?**
**[CURRENT]** swaps are pay-fixed, subtract duration (used to strip duration off long,
post-FABN-eligible bonds), priced at-the-money, capped at 20% of the book. CVaR (C9) plus the
swap cap (C8) are the governing risk controls today; explicit **[PLANNED]** credit-risk budgets
and swap-turnover costs would add further structure once single-period rebalancing extends to a
multi-period design. See `duration-swaps-reference.md`.

---

## 6. See also (ground truth)

- `backend/services/optimizer_service.py` — the LP: objective `:294-301`, constraints
  `:306-369`, swap params `:245-253`, CVaR block `:360-369`, result/constraint extraction
  `:372+`.
- `Optimization/fabn_optimizer_sap.py` — the literal notebook-mirror version of the same LP,
  kept in sync section-by-section with `FABN_Optimizer_SAP_Shadow_SWAP.ipynb`.
- `Optimization/fabn_data_pipeline.py` — inputs: `H` `:57`, `r_FABN` `:58`, `RBC_bar` `:61`,
  `D_FABN` `:323-328`, `qtr_fabn_cf` `:332-336`, `h_curr` `:288`, CVaR scenario section (new,
  before "10 — Pipeline Output"), pipeline dict (Section 10).
- `Optimization/fabn_finance.py` — `book_yield` `:38`, `modified_duration` `:103`,
  `coupon_amort_split` `:132`, C-1 tables `:151-199`, `IMRLedger` `:232`,
  `historical_shock_scenarios` `:456`, `market_values_under_shocks` `:492` (the two functions
  behind the CVaR scenario generation).
- `docs/agent-context/duration-swaps-reference.md` — duration measurement, swap mechanics,
  and the hedging rationale.
- `swap_intuition_lab/swap_intuition_lab.ipynb` — runnable derivations of the swap overlay,
  CVaR (Rockafellar–Uryasev), and rebalancing math referenced in the [PLANNED] sections.
