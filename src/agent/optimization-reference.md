# Optimization Reference — FABN SAP Optimizer

> **Audience:** an AI agent (or engineer) that needs deep, exact context on how the
> portfolio optimization is formulated, why each piece exists, and what breaks if you
> change it. Everything below is grounded in the actual implementation. Source of truth:
> `backend/services/optimizer_service.py` and `Optimization/fabn_data_pipeline.py`.
>
> **Two-state document.** The optimizer is mid-evolution. Sections tagged
> **[CURRENT]** describe code that runs today. Sections tagged **[PLANNED]** describe the
> swap-overlay / CVaR redesign discussed with the sponsor (see
> `swap_intuition_lab/` and `docs/agent-context/duration-swaps-reference.md`). When the two
> disagree, the code is authoritative for *what runs*; the PLANNED notes tell you *where it
> is going and why*.

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
bond (and, in the planned design, a swap overlay) to **maximize risk-adjusted statutory
profit** subject to those constraints.

The model is a **Linear Program (LP)** solved with **Gurobi** (`_solve`,
`optimizer_service.py:149`).

---

## 1. Objective function

**[CURRENT]** The objective is the **SAP** (Statutory Accounting Profit) expression built at
`optimizer_service.py:261-272`:

```
maximize  SAP = NII − capital_cost − turnover_cost − liq_penalty
                + savings_income + swap_NII − swap_RBC
```

Every term is **linear in the decision variables** (dollars). Definitions:

| Term | Formula (as coded) | Units | Economic meaning |
|---|---|---|---|
| `NII` | `Σ_i (book_yield_i − r_FABN) · h_i` | $/yr | Net investment income: the annual book-yield spread of each bond over the FABN crediting rate, times dollars held. This is the core profit engine. |
| `capital_cost` | `lambda_cap · Σ_i theta_i · h_i` | $/yr | Cost of the regulatory capital the assets consume. `theta_i` = NAIC C-1 factor (credit charge). `lambda_cap = cost_of_capital · RBC_bar` (`:195`). |
| `turnover_cost` | `Σ_i tau_i · (tc⁺_i + tc⁻_i)` | $ | Transaction cost of trading away from the current book. `tau_i = tau_raw_i · 10` (bid-ask half-spread, scaled). `tc⁺/tc⁻` = dollars bought / sold. |
| `liq_penalty` | `eta · Σ_q df_q · s_net_q` | $ | Penalty for any quarter where asset cash inflow falls short of the FABN outflow (`eta = 1.0`). `df_q` discounts at `r_FABN`. |
| `savings_income` | `r_save · dt_q · Σ_{q<Q-1} B_q` | $ | Income earned on surplus cash parked in the lending facility. `r_save = r_FABN · lambda_w`, `dt_q = 0.25`. |
| `swap_NII` | `Σ_k (c_swap_k − r_float) · v_k` | $/yr | Net carry of the interest-rate swap overlay (`:269`). **[CURRENT]** receive-fixed, so positive when fixed > floating. |
| `swap_RBC` | `lambda_cap · mu_swap · Σ_k v_k` | $/yr | Capital charge on swap notional (`mu_swap = 0.002`, a small C-3 proxy). |

Where `book_yield_i` is the effective-interest IRR of bond *i* (`fabn_finance.book_yield`,
solving `Σ_t CF_t (1+y)^(-t) = price/100`), `r_FABN` = FABN coupon, and
`nii_rate_i = book_yield_i − r_FABN` (`:211`).

**Economic reading:** maximize spread income, *minus* the cost of the capital that income ties
up, *minus* trading friction, *minus* a penalty for under-funding the liability, *plus*
reinvestment income, *plus* the swap's net carry and capital.

**[PLANNED]** Two objective changes accompany the swap redesign:
- **Mean–CVaR form.** Add a risk penalty `− λ · CVaR_α(L)` where `L` is the relative
  market-value-vs-book loss (Rockafellar–Uryasev; see §2 constraint "CVaR" and the
  duration-swaps reference). Equivalently keep the objective and add CVaR as a *hard
  constraint*. Both are LP-preserving.
- **Signed swap carry.** When swaps flip to **pay-fixed** (to *reduce* duration rather than
  add it), the carry term becomes `(r_float − c_swap_k) · v_k` and is typically slightly
  negative (an upward-sloping curve → the hedge has negative carry). The swap then earns ~0;
  its value is *relaxing the duration constraint so longer, higher-spread bonds can be held*.

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
| C1 | **Budget** (`:276`) | `Σ_i h_i = H` | Invest exactly the full \$500M of proceeds, no more, no less. | The FABN proceeds are a fixed pot; you must deploy all of it (idle cash earns nothing and still owes `r_FABN`), and you cannot invest money you do not have. | Removing `=` for `≤` lets the model under-invest, dodging risk while still owing the liability — spurious "profit". Over-investing implies phantom leverage. |
| C2 | **Duration band** (`:279-286`) | `Σ_i durs_i·h_i + Σ_k swp_dur_k·v_k − D_FABN·H = d⁺ − d⁻`, with `d⁺ ≤ eps_D·H`, `d⁻ ≤ eps_D·H` | Keep the *dollar-weighted asset duration* within `eps_D` years of the FABN's duration `D_FABN`. | Immunizes **surplus** (assets − liability) against parallel rate moves: if asset and liability durations match, their values move together, protecting the balance sheet from rate risk. See duration-swaps reference. | Widen `eps_D` → more rate risk in surplus; a rate move now changes net economic value. Remove it → the optimizer chases the highest-yield (usually longest) bonds and the book becomes badly rate-mismatched to the liability. |
| C3 | **HtM exclusion** (`:252-259`) | For each *i* with `maturity_i > FABN_maturity`: `h_i.ub = 0` | Forbid holding any bond that matures *after* the FABN. | A bond maturing after the note cannot return principal in time to repay the note; it would have to be **sold** at maturity at an unknown price. Banning them guarantees self-liquidation. | This is the constraint most directly **[PLANNED for removal]** — see §2.2. Removing it *without* a replacement exposes forced-sale price risk at the terminal date. |
| C4 | **Turnover decomposition** (`:289-290`) | `h_i − h_curr_i = tc⁺_i − tc⁻_i` | Split each position change into a buy leg and a sell leg (both ≥ 0). | Makes the traded amount `|h_i − h_curr_i|` linear so the `turnover_cost` term can price it. Purely structural (enables C-cost, not a limit). | Not a risk limit; if dropped the objective can't see trading cost and will churn the book. |
| C5 | **Facility dynamics** (`:293-303`) | `B_q − s_net_q = (1+r_save·dt_q)·B_{q−1} + CF^A_q + CF^{swap}_q − CF^L_q` (with `B_{-1}=0`) | Roll a cash account quarter by quarter: prior balance grown at `r_save`, plus asset & swap cash in, minus FABN cash out. Surplus → `B_q`; shortfall → `s_net_q`. | Ties the *timing* of cash to the model. Surplus earns `savings_income`; shortfalls are penalized and capped (C6). This is the cash-flow-matching mechanism. | If the facility recursion is dropped there is no representation of *when* cash arrives — the model could "fund" a Q1 outflow with a Q8 coupon. |
| C6 | **PV shortfall cap** (`:305-310`) | `Σ_q df_q · s_net_q ≤ phi_sf · PV_liability`, `phi_sf = 0.01` | The present value of all cumulative funding shortfalls must stay under 1% of the liability's PV. | A hard solvency guardrail: allows *tiny* timing mismatches (bridged by the facility) but forbids a materially under-funded schedule. | Raise `phi_sf` → tolerate larger unfunded gaps (liquidity/solvency risk). Remove → the liability need not be funded at all; "profit" becomes illusory. |
| C7 | **Issuer concentration** (`:312-320`) | For each issuer *g*: `Σ_{i∈g} h_i ≤ effective_delta · H`, `effective_delta = min(w_max, 1/n_min)` | No single issuer (CUSIP prefix) exceeds a small fraction of the book; forces ≥ `n_min` names. | Diversifies idiosyncratic default/credit risk; a mandate/prudence rule. `n_min = 20` ⇒ at least ~20 distinct issuers. | Loosen → concentration risk (one default hurts more). Remove → the LP piles into the single highest-SAP issuer. |
| C8 | **Swap notional cap** (`:322-326`) | `Σ_k v_k ≤ v_max_frac · H`, `v_max_frac = 0.20` | Total swap notional ≤ 20% of the book. | Bounds derivative leverage, counterparty exposure, and (in the planned design) variation-margin liquidity draw. | Loosen → larger hedge / larger collateral swings; remove → unbounded notional, model can over-hedge or (planned pay-fixed) take large rate positions. |

**Non-negativity** (`lb=0`) on `h, v, B, s_net, tc±` are bounds, not rows: no short bonds, no
negative swap notional, no negative cash balance, no negative shortfall.

### 2.2 Constraint evolution **[PLANNED]** — what is deleted and what is added

The swap-overlay redesign (see `duration-swaps-reference.md` and `swap_intuition_lab/`)
changes the constraint set deliberately:

| Change | Constraint | What & why |
|---|---|---|
| **DELETE** | **C3 HtM exclusion** | Remove the blanket ban on post-FABN bonds so the book can hold longer, higher-spread credit. The forced-sale risk this ban prevented is instead controlled by the CVaR constraint (below) and, where needed, by put options / repo bridging the terminal principal. |
| **FLIP** | **Swap direction in C2 & objective** | Swaps change from **receive-fixed** (`swp_dur > 0`, *adds* duration) to **pay-fixed** (`swp_dur < 0`, *subtracts* duration). This lets a long-duration bond book be pulled back to `D_FABN`: net duration `= Σ durs_i h_i − |swp_dur_k| v_k`. |
| **ADD** | **CVaR on MV/BV** | A Rockafellar–Uryasev tail-loss limit on the relative market-value-vs-book loss `L = 1 − MV/BV`: `ζ + 1/((1−α)S)·Σ_ω z_ω ≤ β`, with `z_ω ≥ L_ω − ζ`, `z_ω ≥ 0`. Bounds the mark-to-market loss we'd crystallize at a forced sale — the risk C3 used to prevent by fiat. Can *replace* C2 (it already penalizes rate moves) or run alongside it. LP-preserving. |
| **ADD** | **Credit-risk budgets** | Once C2 no longer implicitly caps how long/risky bonds can be (because swaps absorb duration), add explicit linear budgets: spread-duration `Σ durs_i h_i ≤ D̄_s·H`, rating floor `Σ g_i h_i ≤ ḡ·H`, WAL cap `Σ T_i h_i ≤ WAL̄·H`, liquidity `Σ_{maturity>FABN} h_i ≤ ℓ̄·H`. These replace duration's former role as a credit brake. |
| **ADD** | **Swap turnover** | On rebalance, penalize `|Δv_k|` (change in swap notional) in the objective, exactly like bond turnover (C4), so the hedge is not churned each period. See duration-swaps reference §4. |
| **CHANGE** | **Reinvestment policy** | Make the reinvestment rule for returned principal explicit rather than silently parking it at `r_save`; this is a modeling assumption that materially drives shadow prices. |

---

## 3. Why this formulation (design rationale)

- **Why an LP (linear, not quadratic/MILP).** Every term above is linear in `(h, v, aux)`.
  A linear program is globally optimal, fast, and returns **dual values / reduced costs**
  (`h[i].RC` at `:415`) — the marginal SAP of relaxing each constraint. That interpretability
  is the point: the model can tell you the *price* of each limit (e.g., "the last 0.1y of the
  duration band costs X bps of spread"). A quadratic (mean-variance) objective would lose the
  clean shadow prices; the planned **CVaR** risk measure is specifically chosen because it is
  *coherent* **and** stays linear (Rockafellar–Uryasev), unlike variance (QP) or VaR
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

### Example A — a 3-bond toy solve (objective + constraints by hand)

Scale everything down: budget `H = $300`, target duration `D_FABN = 3.0`, `eps_D = 0.4`,
`r_FABN = 3.2%`, `w_max` large enough to ignore, one issuer each. Three bonds:

| Bond | book_yield | duration | theta (C-1) | matures after FABN? |
|---|---|---|---|---|
| A (2y) | 4.0% | 1.9 | 0.008 | no |
| B (5y) | 4.8% | 4.4 | 0.010 | no |
| C (10y) | 5.8% | 7.8 | 0.015 | **yes** |

Take `lambda_cap = 0.15 · 1.5 = 0.225`. Ignore turnover/facility for intuition.

1. **C3 (HtM)** immediately sets `h_C ≤ 0` — bond C is *banned* because it matures after the
   FABN. So under **[CURRENT]** rules we can only use A and B.
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

### Example B — the same solve **[PLANNED]** with pay-fixed swap + no HtM ban

Now delete C3 and allow a **pay-fixed** swap with `swp_dur = −4.5` per \$1 notional (a ~5y
swap), capped at `v ≤ 0.20·H = 60`.

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
`_solve` returns `{"status":"infeasible"}` (`:331-334`). It means no `h,v` can satisfy *all*
constraints at once. Usual causes, in order of likelihood: (a) **duration band too tight**
(`eps_D` small) given the available bonds and the HtM ban — the eligible short bonds cannot
reach `D_FABN`; (b) the **PV-shortfall cap** cannot be met because eligible cash flows do not
line up with the FABN schedule; (c) concentration (`n_min`) too high for the eligible universe.
Debug by loosening one constraint at a time (widen `eps_D`, raise `phi_sf`, lower `n_min`).

**Q: How does changing `eps_D` ripple through?**
`eps_D` is the half-width of the duration band (C2). Larger → the model can hold longer
(higher-yield) bonds → higher SAP but more surplus rate risk. Smaller → forces shorter bonds →
lower SAP, tighter immunization; too small → **infeasible**. Its shadow price = marginal SAP per
year of band.

**Q: How does `gamma_w` (cost of capital) change the answer?**
`gamma_w` scales `lambda_cap = gamma_w · RBC_bar` (`:195`), which multiplies every bond's C-1
charge in the objective. Higher `gamma_w` → capital-heavy (low-rated / high-`theta`) bonds get
penalized more → the book tilts toward higher-quality names even at lower yield.

**Q: What is `r_save` / `lambda_w`?**
`r_save = r_FABN · lambda_w` (`:198`) is the rate earned on surplus cash in the lending
facility (C5). `lambda_w = 1.0` means surplus cash earns exactly the funding rate (break-even
reinvestment). Lower it to model a reinvestment drag; this is the assumption flagged for
explicit treatment in the planned redesign.

**Q: Where do `book_yield`, `durs`, `theta` come from?**
The pipeline (`fabn_data_pipeline.py`) computes them via `fabn_finance`: `book_yield` = IRR
solve, `durs` = modified duration, `theta` = NAIC C-1 factor by rating. They are *inputs* to the
LP, fixed per date.

**Q: Why can SAP be dominated by so few bonds?**
Because it is linear, the LP pushes to the vertices — it buys the highest per-dollar-SAP bonds
until a constraint (duration band, concentration, budget) binds. The binding constraints, not
the objective, determine the shape of the book. Reduced costs (`h[i].RC`) rank the rest.

**Q: Where does the swap enter today vs. tomorrow?**
**[CURRENT]** swaps are receive-fixed, add duration (used to top *up* duration when the eligible
short bonds are too short), capped at 20%. **[PLANNED]** they flip to pay-fixed to strip
duration off long bonds, with CVaR + credit budgets replacing the HtM ban. See
`duration-swaps-reference.md`.

---

## 6. See also (ground truth)

- `backend/services/optimizer_service.py` — the LP: objective `:261-272`, constraints
  `:274-326`, swap params `:213-227`, result/constraint extraction `:340-453`.
- `Optimization/fabn_data_pipeline.py` — inputs: `H` `:57`, `r_FABN` `:58`, `RBC_bar` `:61`,
  `D_FABN` `:323-324`, `qtr_fabn_cf` `:332-333`, `h_curr` `:287`, pipeline dict `:486+`.
- `Optimization/fabn_finance.py` — `book_yield` `:38`, `modified_duration` `:103`,
  `coupon_amort_split` `:132`, C-1 tables `:151-199`, `IMRLedger` `:232`.
- `docs/agent-context/duration-swaps-reference.md` — duration measurement, swap mechanics,
  and the hedging rationale.
- `swap_intuition_lab/swap_intuition_lab.ipynb` — runnable derivations of the swap overlay,
  CVaR (Rockafellar–Uryasev), and rebalancing math referenced in the [PLANNED] sections.
