# Interest Rate Swaps in the FABN SAP Optimizer
### Theoretical Framework and Integration Roadmap

---

## Executive Summary

The FABN SAP Optimizer currently manages portfolio duration by buying and selling bonds — a
mechanism that works but carries a direct cost: every trade consumes the bid-ask spread
(`τᵢ`), which the backtest shows can reach $13M in cumulative turnover costs under daily
rebalancing. **Interest rate swaps** offer a structurally cheaper way to achieve the same duration
alignment. A swap adjusts how sensitive the portfolio is to interest rate movements without
requiring the purchase or sale of a single bond, and at a fraction of the transaction cost.

In the FABN SAP Optimizer, swaps would:
1. Allow the portfolio to meet its duration mandate (`|D_avg − D_FABN| ≤ ε_D`) with fewer
   bond trades, reducing the turnover cost that currently erodes NII.
2. Potentially generate additional statutory income if swap fixed rates available in the market
   exceed the FABN funding rate (3.205%).
3. Provide a cleaner separation between the **income decision** (which bonds to hold for yield)
   and the **duration decision** (how to match the liability's interest rate sensitivity).

Adding swaps modifies the optimization model in three places: the objective function, the duration
constraint, and the quarterly facility cash-flow balance. The necessary mathematical functions
belong in `fabn_finance.py`; the model variables and constraints go in `FABN_Optimizer_SAP.ipynb`
and `FABN_Optimizer_SAP_Backtest.ipynb`.

---

## 1. What Is an Interest Rate Swap?

### 1.1 The intuition

An interest rate swap is a contract between two parties who agree to exchange streams of interest
payments on an agreed **notional principal** for a set period. Crucially, the notional itself is
never exchanged — only the difference in interest payments changes hands at each settlement date.

The most common form is the **plain vanilla fixed-for-floating swap**:

- **Party A (fixed payer):** pays a fixed rate agreed at inception (e.g., 4.50% per year on $100M).
- **Party B (floating payer):** pays a floating rate that resets periodically (e.g., the overnight
  SOFR rate, which moves with the Federal Reserve's policy decisions).

If SOFR is currently 5.30%, Party B pays 5.30% and Party A pays 4.50%, so Party A receives a net
payment of 0.80% × $100M = $800,000 for that period. If rates fall and SOFR drops to 3.80%, the
net payment reverses: Party A pays 0.70% net.

The swap has **no upfront cost** (beyond a small dealer spread), which is what makes it
fundamentally different from buying or selling a bond. You are not purchasing an asset; you are
simply exchanging one type of interest rate exposure for another.

### 1.2 A simple analogy

Think of a homeowner with a fixed-rate mortgage and a landlord who receives fixed rent from tenants.
If the homeowner expects rates to rise, they might prefer a floating-rate mortgage (cheaper now,
but risky later). Rather than refinancing — which is expensive — they can enter a swap: they agree
to pay floating to a bank and receive fixed in return. Their mortgage payments stay fixed, but
economically they now have floating exposure. They achieved a rate transformation cheaply, without
touching the original contract.

In our context, the FABN portfolio holds fixed-rate bonds. A swap lets the portfolio manager
adjust how those fixed cash flows behave relative to changing interest rates — without selling
any bonds and incurring bid-ask costs.

---

## 2. Types of Swaps and Their Role in the FABN Context

Not every swap structure is relevant here. Below are the three most applicable types, ordered from
simplest to most complex.

### 2.1 Plain Vanilla Interest Rate Swap (IRS)

**Structure:** exchange a fixed rate for SOFR (or another floating benchmark) on a notional amount
for a stated term.

**Role in FABN:** purely for **duration management**. The portfolio's bond holdings have a
weighted-average duration approximately matching the FABN's 2.49 years. When bonds mature or are
sold, the portfolio's duration shifts. Instead of buying or selling bonds to restore alignment, a
swap can be used to add or subtract duration instantaneously.

- A **receive-fixed swap** (we receive fixed, pay floating) has **positive duration** — it behaves
  like holding an additional bond. Use it when the portfolio's duration is too short relative to
  the FABN.
- A **pay-fixed swap** (we pay fixed, receive floating) has **negative duration** — it acts like
  shorting a bond. Use it when the portfolio's duration is too long.

This is the primary candidate for integration into the optimizer.

### 2.2 Asset Swap

**Structure:** a combination of a bond purchase and an IRS that converts the bond's fixed coupon
into a floating rate (or vice versa).

**Role in FABN:** if a particular bond has an attractive credit spread but its fixed coupon
creates an unwanted duration contribution, an asset swap can strip out the rate risk and leave
only the credit spread exposure. In statutory (SAP) terms, however, the bond is still carried at
amortized cost, so the asset swap's fair-value changes create accounting complexity. This structure
is **secondary priority** for integration.

### 2.3 Total Return Swap (TRS)

**Structure:** one party pays the total return (price appreciation + coupon) of a reference asset;
the other pays a fixed or floating rate.

**Role in FABN:** a TRS would allow synthetic exposure to bonds the portfolio cannot hold directly
(e.g., post-FABN-maturity bonds excluded by the hold-to-maturity rule). However, TRS introduces
counterparty risk and complex SAP accounting treatment. This structure is **out of scope** for the
current integration and is noted only for completeness.

**Recommended starting point:** the plain vanilla IRS (Section 2.1), applied to duration
management within the existing SAP LP framework.

---

## 3. How Swaps Enter the SAP Optimization Model

Introducing swaps into the optimizer requires adding decision variables for swap notionals and
modifying three structural components of the model: the objective function, the duration
constraint, and the facility balance constraints.

We define a **universe of $K$ candidate swaps**, indexed by $k$, each characterized by:

| Parameter | Symbol | Description |
|---|---|---|
| Swap notional | $v_k$ | Decision variable (dollars, $v_k \geq 0$) |
| Fixed rate | $c_k$ | Agreed at inception; known before optimization |
| Floating rate | $r^{float}$ | SOFR or risk-free rate on the optimization date |
| Modified duration | $D^{swap}_k$ | Duration of the fixed leg (positive for receive-fixed) |
| Quarterly cash flow | $CF^{swap}_{q,k}$ | Net settlement per dollar of notional in quarter $q$ |
| Capital charge | $\mu_k$ | RBC charge on swap notional (interest-rate risk) |

In practice, the swap universe would cover two to four standard maturities spanning the FABN
horizon: 1-year, 2-year, 3-year, and 5-year receive-fixed swaps.

### 3.1 The objective function

The current SAP objective is:

$$
\max \; \underbrace{\sum_i (y_i - r^{FABN}) h_i}_{\text{Statutory NII}}
- \underbrace{\lambda \sum_i \theta_i h_i}_{\text{Capital cost}}
- \underbrace{\sum_i \tau_i (tc^+_i + tc^-_i)}_{\text{Turnover cost}}
- \underbrace{\eta \sum_q DF_q \, s^{net}_q}_{\text{Liquidity penalty}}
+ \underbrace{r_{save} \cdot \Delta t \sum_q B_q}_{\text{Facility income}}
$$

Adding swaps introduces two new terms:

$$
+ \underbrace{\sum_k (c_k - r^{float}) \cdot v_k}_{\text{Swap net income}}
- \underbrace{\lambda \sum_k \mu_k \cdot v_k}_{\text{Swap capital cost}}
$$

**Swap net income:** the fixed rate received minus the floating rate paid, multiplied by the notional.
If $c_k > r^{float}$, the swap generates positive statutory income; if $c_k < r^{float}$, it is a
net cost. In the current environment (SOFR ≈ 4.3%, FABN coupon = 3.205%), a receive-fixed swap
at a market rate of approximately 4.0–4.5% would generate meaningful positive NII.

**Swap capital cost:** under NAIC RBC guidelines, swaps carry an interest-rate risk charge.
$\mu_k$ represents the C-3 capital factor applied to the swap notional, analogous to the C-1
factor $\theta_i$ applied to bond holdings. The exact factor depends on the swap's duration and
the insurer's RBC classification; for this model, a conservative estimate would be used pending
actuarial guidance.

### 3.2 The duration constraint

The duration alignment band currently reads:

$$
\left| \frac{\sum_i D_i h_i}{H} - D^{FABN} \right| \leq \varepsilon_D
$$

With swaps, the portfolio's effective duration includes the duration contribution of each swap:

$$
\left| \frac{\sum_i D_i h_i + \sum_k D^{swap}_k v_k}{H} - D^{FABN} \right| \leq \varepsilon_D
$$

The modified duration of the fixed leg of a receive-fixed swap is **positive** (it behaves like a
bond with that maturity). For a 2-year receive-fixed swap, $D^{swap}_k \approx 1.90$ years — close
to the FABN's target duration. This means the optimizer can add duration synthetically through
swaps rather than by shifting the bond portfolio toward longer maturities.

This is the central mechanism: **the optimizer now has a cheaper instrument (the swap) to satisfy
the duration constraint, and will prefer it over expensive bond trades whenever the economics
allow**.

### 3.3 The facility / liquidity constraints

The quarterly cash-flow balance currently tracks asset bond cash flows against FABN liability
payments. Swaps generate net settlement cash flows at each period that must enter this balance:

$$
B_q - s^{net}_q = (1 + r_{save} \cdot \Delta t) \cdot B_{q-1}
                 + \underbrace{\sum_i CF^{bond}_{q,i} \cdot h_i}_{\text{Bond CFs}}
                 + \underbrace{\sum_k CF^{swap}_{q,k} \cdot v_k}_{\text{Swap CFs (new)}}
                 - CF^{FABN}_q
$$

Where $CF^{swap}_{q,k} = (c_k - r^{float}_q) \cdot \Delta t$ is the net swap settlement per
dollar of notional in quarter $q$ (positive if the fixed rate exceeds the floating rate, i.e.,
we receive more than we pay).

This matters for two reasons:
- A receive-fixed swap that nets positive generates cash every quarter, improving facility
  balances and reducing the PV shortfall penalty.
- A receive-fixed swap in a low-rate environment (where $r^{float} < c_k$) requires net
  cash outflows that tighten facility balances. The optimizer must weigh this against the
  duration benefit.

### 3.4 Capital treatment

Under NAIC RBC for life insurers, interest rate derivatives are captured in the C-3 (interest rate
risk) component. The exact charge depends on the insurer's asset/liability model, but a practical
approximation for the LP model is to treat swap capital analogously to bonds:

$$
RBC^{swap} = \sum_k \mu_k \cdot v_k
$$

where $\mu_k$ is the duration-proportional rate-risk charge for swap $k$. This keeps the model
structure consistent (capital cost enters linearly) and avoids requiring a full C-3 scenario
analysis within the LP.

---

## 4. The Core Strategic Case: Swaps as a Low-Cost Duration Tool

The backtest revealed that the optimizer's biggest friction is **turnover cost**. With `kappa = 1`
and daily rebalancing, cumulative turnover paid reaches $13.2M — wiping out the dynamic
strategy's advantage over static buy-and-hold. The introduction of `kappa` and `reopt_every`
are workarounds that suppress trading but also suppress beneficial rebalancing.

Swaps address the root cause rather than the symptom. Consider the following comparison:

| Action | Duration effect | Cost |
|---|---|---|
| Buy $10M of a 3-year bond | +~2.8 yr × $10M = +$28M yr | Bid-ask: ~5–30 bps × $10M = $5,000–$30,000 |
| Enter $10M receive-fixed 3yr swap | +~2.7 yr × $10M = +$27M yr | Dealer spread: ~1–3 bps × $10M = $1,000–$3,000 |

The swap achieves approximately the same duration adjustment at **one-tenth the transaction cost**.
This means the optimizer can rebalance duration daily — or even intraday — without the turnover
penalty that makes daily rebalancing costly in the bond-only model.

The practical implication for the backtest: in a world with swaps available, the optimal value of
`kappa` and `reopt_every` may shift significantly, because the duration constraint can be managed
cheaply through the swap overlay while bond positions are traded at a slower, more deliberate pace.

---

## 5. Mathematical Functions Required (`fabn_finance.py`)

Three new pure functions should be added to `fabn_finance.py` to keep the math in a single,
testable location:

### 5.1 `swap_fixed_leg_duration(maturity_years, fixed_rate, settlement_freq)`

Computes the modified duration of the fixed leg of a receive-fixed swap. Conceptually identical
to the bond duration calculation already in the library:

$$
D^{swap}_{mod} = \frac{\sum_t t \cdot \frac{c \cdot \Delta t}{(1+r)^t}}{\sum_t \frac{c \cdot \Delta t}{(1+r)^t}} \cdot \frac{1}{1+r}
$$

where $c$ is the fixed coupon rate, $r$ is the current discount rate (SOFR or risk-free), and
the sum runs over settlement dates. For a receive-fixed swap, this is positive; the function
returns a negative value if called for a pay-fixed swap.

### 5.2 `swap_quarterly_cashflows(fixed_rate, r_float_schedule, notional, settlement_dates, quarter_grid)`

Maps swap net settlements to the quarterly facility grid used by the optimizer. Returns a
`(Q,)` array of net cash flows per dollar of notional, aligned to the same quarter index as
`qtr_bond_cf` and `qtr_fabn_cf`. Positive values are cash receipts (floating > fixed); negative
values are cash payments (fixed > floating).

### 5.3 `swap_fair_value(fixed_rate, r_float_curve, maturity_years, settlement_freq)`

Computes the mark-to-market fair value of the swap for reporting purposes (not used in the LP
objective, which is SAP book-based). Useful for risk monitoring and for quantifying the IMR
treatment of any realized gains/losses if a swap is unwound before maturity.

---

## 6. Proposed Integration into the FABN Optimizer

### 6.1 Files to modify

| File | Change |
|---|---|
| `fabn_finance.py` | Add the three functions described in Section 5 |
| `FABN_Optimizer_SAP.ipynb` | Add swap variables to Section 2, modify objective and duration constraint, add swap analytics to Section 4 |
| `FABN_Optimizer_SAP_Backtest.ipynb` | Modify `solve_day()` to include swap variables; add swap cash flows to quarterly facility block; track swap NII separately in daily P&L |
| `FABN_Data_Pipeline_SAP.ipynb` | Optionally: pull current swap rates from FRED (SOFR, swap curve) for live market inputs |

### 6.2 Structure of changes in `FABN_Optimizer_SAP.ipynb`

```
[Existing Section 1B — Parameters]
  Add: swap universe definition (K swaps, fixed rates c[k], durations D_swap[k])
  Add: r_float (current SOFR or risk-free rate for the optimization date)
  Add: mu_swap (capital charge per dollar of swap notional)

[Existing Section 2 — Gurobi Model]
  Add: v = model.addVars(K, lb=0.0, name="v")       ← swap notionals
  Modify: objective → add swap_nii and swap_capital_cost terms
  Modify: duration constraint → add Σ D_swap[k]*v[k]
  Modify: facility constraints → add Σ CF_swap[q,k]*v[k] per quarter
  Add: swap notional cap constraint (e.g., Σ v[k] ≤ 0.20 * H)

[Existing Section 3 — Results]
  Add: swap decomposition in objective table
  Add: report optimal v[k] for each swap maturity

[Existing Section 4 — Analytics]
  Add: chart of swap notional vs bond duration contribution
  Add: total portfolio duration = bond duration + swap duration
```

### 6.3 Structure of changes in `solve_day()` (backtest)

```python
# --- new parameters in PARAMS ---
PARAMS["use_swaps"]    = True
PARAMS["swap_rates"]   = [c_1y, c_2y, c_3y]     # fixed rates for each swap
PARAMS["swap_durs"]    = [D_1y, D_2y, D_3y]      # modified durations
PARAMS["swap_cap"]     = 0.20 * H                # max total swap notional
PARAMS["mu_swap"]      = 0.002                   # capital charge rate on swap notional

# --- inside solve_day() ---
if P.get("use_swaps", False):
    v = m.addVars(K, lb=0.0)
    # Objective: add swap net income and capital cost
    swap_nii    = gp.quicksum((P["swap_rates"][k] - r_float) * v[k] for k in range(K))
    swap_cap    = gp.quicksum(P["mu_swap"] * v[k] for k in range(K))
    # Duration: modify existing constraint to include swap contribution
    # Facility: add CF_swap[q,k] * v[k] to each quarterly balance
    # Cap total swap notional
    m.addConstr(gp.quicksum(v[k] for k in range(K)) <= P["swap_cap"])
```

### 6.4 New outputs to produce

**Table — Swap Overlay Report**

| Swap | Maturity | Fixed rate | Notional | Duration contribution | Net NII | Capital charge |
|---|---|---|---|---|---|---|
| Swap 1 | 1yr | 4.25% | $X | +Y yr·$ | +$Z | $W |
| Swap 2 | 2yr | 4.40% | $X | +Y yr·$ | +$Z | $W |
| Swap 3 | 3yr | 4.55% | $X | +Y yr·$ | +$Z | $W |
| **Total** | | | **$X** | **+Y yr·$** | **+$Z** | **$W** |

**Chart — Duration Attribution: Bonds vs Swaps**

A stacked bar showing, for each backtest date, how much of the portfolio's total duration is
contributed by bond holdings versus the swap overlay. This directly visualizes the substitution
effect — on days when the swap overlay is large, fewer bond trades were needed to meet the
duration mandate.

---

## 7. SAP Accounting Treatment

How swap income and expenses are recognized in statutory financial statements affects how they
should enter the optimizer's objective. Three possible treatments under SAP:

### 7.1 Not designated as a hedge (speculative)

The swap's **fair value change** flows through the income statement each period. This creates
volatility in statutory income — undesirable for an insurer managing stable NII. Under this
treatment, the optimizer's income term should include both the periodic net settlement AND an
estimate of fair value change, making the objective more complex.

**Not recommended** for this use case.

### 7.2 Fair value hedge

The swap is designated to hedge the fair value of a specific bond. Changes in the bond's fair
value attributable to interest rate movements are recognized in income, offset by the swap's fair
value change. Net effect: the hedged bond's income approximates a floating-rate asset.

Under SAP, fair value hedge accounting for bonds is restrictive and requires documentation at
inception. Applicable when the goal is to synthetically convert a specific fixed bond to floating.

**Applicable to asset swaps (Section 2.2); not directly relevant to the plain vanilla IRS.**

### 7.3 Cash flow hedge

Swap settlements are recognized as income or expense when received or paid. Fair value changes
go to a separate equity reserve (similar to OCI under GAAP). Periodic net settlements flow through
the income statement straightforwardly.

**This is the recommended treatment for the plain vanilla IRS.** Under this accounting:
- Each quarter's net swap settlement (floating received minus fixed paid) enters the income
  statement — exactly as modeled in Section 3.1.
- The optimizer's `swap_nii` term maps directly to statutory income recognized each period.
- No fair value volatility enters the objective.

This simplification is consistent with the model's existing approach to the IMR: it focuses on
accrual income (book yields, coupon, amortization, swap settlements) rather than mark-to-market
changes.

---

## 8. Limitations

| Limitation | Detail |
|---|---|
| **Floating rate uncertainty** | In the single-period optimizer, `r_float` is the current SOFR rate. In the backtest, it must be updated daily from the rate history (already available in `rf_hist`). Future floating rates are unknown at optimization time — the optimizer uses the current rate as its best estimate. |
| **Basis risk** | SOFR and the FABN's cost of funds (3.205% fixed) are both fixed or proxied; there is no natural floating-rate liability to hedge. Swaps here are tools for duration management, not liability replication. If the FABN were floating-rate, the analysis would differ significantly. |
| **Counterparty risk** | Swaps expose the portfolio to default risk of the swap dealer. Under a Credit Support Annex (CSA), daily collateral posting mitigates this, but the collateral cash flow must be modeled if the notional is large. For the LP model, this is treated as negligible at current notional levels. |
| **SAP capital charge uncertainty** | The C-3 capital charge for interest rate derivatives varies by insurer and requires actuarial input. The `mu_swap` parameter is a placeholder; the true charge may differ materially. Sensitivity analysis over `mu_swap` is recommended before relying on the optimizer's swap allocation. |
| **Swap market liquidity** | Swap rates and bid-offer spreads are not currently in the BigQuery data pipeline. A FRED or Bloomberg feed for the SOFR swap curve must be added to `FABN_Data_Pipeline_SAP.ipynb` before the model can use live market rates. |
| **Linear approximation of duration** | The duration constraint uses a first-order (linear) approximation of interest rate sensitivity. Convexity — the second-order effect — is ignored both for bonds and swaps. For portfolios with large rate movements, this approximation degrades. For the FABN's 2.5-year horizon with moderate rate changes, it is acceptable. |

---

## 9. Summary

Interest rate swaps, specifically plain vanilla receive-fixed swaps, address the FABN optimizer's
most persistent friction: the cost of managing portfolio duration through bond trading. By
introducing swap notionals as additional decision variables, the optimizer gains a low-cost
instrument that can satisfy the duration mandate without triggering bid-ask transaction costs on
the bond portfolio.

The integration touches four files, is fully linear (no new complexity class), and preserves all
existing constraints and objective terms. The three new mathematical functions belong in
`fabn_finance.py`, keeping the codebase's single-source-of-truth principle intact.

The recommended implementation path is:

1. Add the three mathematical functions to `fabn_finance.py` (pure functions, unit-testable).
2. Add swap variables and modify the duration and facility constraints in
   `FABN_Optimizer_SAP.ipynb`, keeping swaps as an optional overlay (`use_swaps` flag).
3. Extend `solve_day()` in `FABN_Optimizer_SAP_Backtest.ipynb` with the same swap block, and
   run the backtest sweep (`kappa × reopt_every`) again to quantify how much the swap overlay
   reduces the optimal `kappa` and improves the dynamic-vs-static NII advantage.
4. Add the Swap Overlay Report and Duration Attribution chart to the analytics sections.

The key question the implementation will answer is: **how much of the $13M in cumulative
turnover cost can be replaced by a swap overlay, and at what swap notional level does the
capital charge outweigh the duration management benefit?**
