# Shadow Prices in the FABN SAP Optimizer
### Theoretical Framework and Integration Roadmap

---

## Executive Summary

Every constrained optimization problem carries hidden information: for each rule the optimizer must
obey, there is a precise dollar value attached to how much that rule is costing us. These values are
called **shadow prices** (or dual values). They answer the question *"how much more income could we
earn if this constraint were slightly relaxed?"* — and, equally, they reveal which bonds in our
universe are excluded only because they narrowly fail to clear a cost hurdle, not because they are
genuinely unattractive.

In the FABN SAP Optimizer, shadow prices let us:
1. Quantify the exact cost of each regulatory and operational constraint on statutory NII.
2. Identify bonds whose value to the portfolio exceeds their raw book yield once their structural
   fit — cash-flow timing, duration contribution, capital efficiency — is accounted for.
3. Provide the investment team with actionable intelligence: *"relaxing the issuer cap by 1% would
   add $X to annual NII"* is a concrete, auditable statement the CEO can take to the board.

Shadow prices require **no changes to the core optimization model**. They are a natural byproduct of
solving any linear program and are computed automatically by Gurobi.

---

## 1. What Is a Shadow Price?

### 1.1 The intuition

Imagine you are allocating a fixed budget across bonds, but you are required to keep the average
portfolio duration within 0.3 years of the FABN's duration. That constraint forces you to hold some
shorter bonds even when longer bonds yield more. If you could widen the band from 0.3 to 0.4 years,
the optimizer could reach slightly better bonds — and your annual NII would increase by some
amount. That amount, measured **per unit of relaxation**, is the shadow price of the duration
constraint.

More concisely: a shadow price is the **rate at which the optimal objective value improves when a
constraint is eased by one unit**, evaluated at the current solution.

Three properties worth keeping in mind:

- Shadow prices are **local**: they describe the marginal benefit of a small relaxation, not a large
  one. Doubling the budget does not necessarily double NII.
- A shadow price of **zero** means the constraint is not currently binding — the optimizer is already
  operating comfortably within that limit, so relaxing it would not help.
- A **large** shadow price signals a highly binding constraint: one that is actively preventing the
  portfolio from reaching a better outcome.

### 1.2 A simple analogy

Think of a manufacturing plant with five production lines, each subject to a capacity limit. The
shadow price of each line's capacity constraint tells management: *"if we install one more unit of
capacity on line 3, our profit increases by $Y per period."* That information directly prioritizes
capital investment. Shadow prices in portfolio optimization serve the same role — they tell us where
the constraints are expensive and where relaxing them would pay off.

---

## 2. Shadow Prices in the FABN SAP Optimizer

The current optimizer enforces six families of constraints. We describe each, what its shadow price
measures, and what a high or zero value implies for investment strategy.

### 2.1 Budget constraint — `Σᵢ hᵢ = H`

**Shadow price interpretation:** the marginal value of $1 of additional capital deployed in the
FABN portfolio, net of all costs (capital charge, transaction costs, liquidity penalties).

| Shadow price | Implication |
|---|---|
| High and positive | The portfolio is capital-constrained; every additional dollar earns significant NII net of charges. Present a case for increasing H. |
| Near zero | The budget is effectively non-binding at the current yield environment; additional capital would not be meaningfully deployed. |

Because this is an equality constraint, its shadow price can be positive or negative, though in
practice it will be positive as long as there exist bonds that earn above the FABN funding rate net
of capital charges.

### 2.2 Duration alignment band — `|D_avg − D_FABN| ≤ ε_D`

The ALM constraint forces the portfolio's weighted-average modified duration to stay within
`eps_D = 0.30` years of the FABN's duration. It is implemented as two one-sided inequalities
(upper and lower), each with its own shadow price.

**Shadow price interpretation:** the increase in annual NII achievable if the duration band were
widened by 0.01 years (one basis point of duration).

| Shadow price | Implication |
|---|---|
| High | The optimizer is pressing against the duration ceiling or floor; loosening the ALM constraint materially improves NII. Consider whether the liability hedging rationale justifies a tighter band than `±0.30`. |
| Zero | The portfolio's natural duration already lands within the band; the constraint is not costing anything. |

This is one of the most strategically important shadow prices: it directly quantifies the **cost of
the ALM mandate** in income terms.

### 2.3 Issuer concentration cap — `Σᵢ∈g hᵢ ≤ δ · H`

Each issuer (identified by the first six CUSIP characters) is capped at 5% of the portfolio budget.

**Shadow price interpretation:** the increase in NII if the cap for issuer $g$ were raised by $1
(equivalently, by 1/H percentage points of concentration).

| Shadow price | Implication |
|---|---|
| High for issuer $g$ | Issuer $g$ has bonds the optimizer wants to overweight — likely high book yield relative to their capital charge and duration. Investigate whether the concentration limit is credit-driven policy or a modelling default. |
| Zero | The optimizer is not pressing against this issuer's cap; it would not add more even if allowed. |

In practical terms, this tells the credit committee which issuers the yield optimizer most wants to
concentrate in — useful context for credit review decisions.

### 2.4 PV shortfall cap — `Σq DFq · sⁿᵉᵗq ≤ φ · PV(L)`

The lending-facility hard cap limits the present value of cash shortfalls (quarters where asset
cash flows fall short of FABN liability payments) to 1% of the PV of the FABN liability.

**Shadow price interpretation:** the increase in NII per dollar of additional PV shortfall tolerance.

| Shadow price | Implication |
|---|---|
| High | The liquidity constraint is binding; the optimizer would prefer a less cash-flow-matched portfolio but cannot because of the shortfall cap. High-yield bonds with back-loaded cash flows are being blocked. |
| Zero | Asset cash flows comfortably cover liability cash flows in all periods; liquidity is not a binding constraint. |

### 2.5 Lending-facility balance constraints — quarterly dynamics

For each of the 33 quarters from the optimization date to FABN maturity:

$$
B_q - s^{net}_q = (1 + r_{save} \cdot \Delta t) \cdot B_{q-1} + CF^{asset}_q - CF^{FABN}_q
$$

Each quarterly balance equation has a shadow price that measures the value of having $1 more in
the facility at the beginning of that quarter.

**Shadow price interpretation:** liquidity value over time. Quarters where the FABN makes large
payments (especially the final quarter, which includes the $500M principal) will have the highest
shadow prices, revealing which periods are the tightest funding points.

### 2.6 Turnover decomposition constraints — `hᵢ − hᶜᵘʳʳᵢ = tc⁺ᵢ − tc⁻ᵢ`

These linearization constraints separate buys and sells for transaction cost accounting. Their
shadow prices represent the **marginal value of the current holding position** in each bond —
essentially, how much it costs to move away from the current portfolio.

---

## 3. Reduced Costs: The Hidden Value of Excluded Bonds

### 3.1 Why raw yield is not the whole story

The optimizer's objective for bond $i$ looks like this in the simplified view:

$$
\text{NII contribution}_i = (y_i^{book} - r^{FABN}) \cdot h_i
$$

But a bond's true marginal value to the portfolio also depends on:

- How much its duration pushes the portfolio toward or away from `D_FABN` (duration constraint
  interaction)
- Whether its quarterly cash flows align with FABN liability payments (facility constraint
  interaction)
- How much required capital it consumes relative to its yield premium (capital charge)
- Which issuer group it belongs to (concentration constraint interaction)

The **reduced cost** of bond $i$ captures all of these interactions simultaneously. For a bond
excluded from the optimal portfolio:

$$
\bar{c}_i = \underbrace{(y_i^{book} - r^{FABN})}_{\text{raw yield premium}} 
           - \underbrace{\lambda \cdot \theta_i}_{\text{capital charge}}
           - \underbrace{\pi_{budget}}_{\text{budget opportunity cost}}
           - \underbrace{\sum_q \pi_{fac,q} \cdot CF^{bond}_{q,i}}_{\text{liquidity fit value}}
           - \underbrace{\pi_{dur} \cdot D_i}_{\text{duration contribution value}}
           - \cdots
$$

### 3.2 The reservation-price interpretation

The reduced cost formula above is stated in **yield space** — annual income per dollar invested. But it has an equally exact and more intuitive **price-space** interpretation that connects directly to how traders think about bond value.

Define the **internal hurdle yield** for bond $i$ as the yield that exactly covers all portfolio costs associated with holding it:

$$r^*_i = r^{FABN} + \lambda \cdot \theta_i + \pi_{budget} + \pi_{dur} \cdot D_i + \sum_q \pi_{fac,q} \cdot CF^{bond}_{q,i}$$

This is our portfolio-specific required return: the minimum yield the bond must offer to justify its capital charge, its impact on the duration band, its cash-flow timing, and the opportunity cost of the budget dollar it consumes.

Now define the **reservation price**:

$$P^*_i = \text{PV}\bigl(\text{bond cash flows discounted at } r^*_i\bigr)$$

This is the **maximum price we would pay** for the bond. The connection to the reduced cost is exact:

$$\bar{c}_i > 0 \iff P^*_i > P^{mkt}_i$$

When the reservation price exceeds the market price, the bond's structural fit — its duration contribution, cash-flow alignment, capital efficiency — relaxes enough binding constraints to justify what the market charges. The **dollar price gap** is approximately:

$$\Delta P_i \approx \bar{c}_i \times MD_i \times P^{mkt}_i$$

For example: if the reduced cost is +5 bps and the bond has a duration of 2 years and a market price of $100, the reservation price is approximately $100.10. We would pay up to $100.10 for a bond the market offers at $100, because its structural fit is worth that premium to us.

> **CEO-level summary:** The shadow prices of the constraints collectively define a hurdle yield for each bond. Bonds whose cash flows, discounted at that hurdle yield, produce a price above the market price are worth buying. The "price gap" is exactly this excess value — how much more the bond is worth to us than to the market, because its fit relaxes the constraints that bind our portfolio.

### 3.3 The cash-flow-matching example

Consider two bonds with identical book yields, ratings, and durations. Bond A has its cash flows
concentrated in years 3–5 (after the FABN matures); Bond B has cash flows falling in the same
quarters as the FABN's semi-annual coupon payments.

In raw-yield terms, the optimizer is indifferent. But Bond B relaxes the quarterly facility
constraints — it directly funds FABN coupon payments without requiring the lending facility — so its
interaction with the `π_{fac,q}` shadow prices is favorable. Its reduced cost will be **less
negative** than Bond A's, and in some cases may push it into the optimal portfolio even if its
advertised yield is slightly lower.

This is the formalization of the intuition that *"a bond that pays like the FABN is worth more to
us than its yield suggests."* Shadow prices make that value explicit and quantifiable.

### 3.4 Ranking the excluded universe

After solving, we can compute each excluded bond's reduced cost and decompose it into its
components. This produces a ranked list of "near-miss" bonds — those that came closest to entering
the portfolio — along with a breakdown of **why** each was excluded:

| Bond | Raw yield premium | Capital charge | Duration fit | Liquidity fit | **Reduced cost** |
|---|---|---|---|---|---|
| Bond X | +180 bps | −15 bps | −5 bps | +12 bps | **−8 bps** ← near miss |
| Bond Y | +200 bps | −80 bps | +3 bps | +2 bps | **−75 bps** ← excluded by capital |
| Bond Z | +90 bps | −10 bps | −2 bps | +45 bps | **+23 bps** ← should be in portfolio |

A positive reduced cost on an excluded bond indicates a model anomaly or degeneracy (the bond
should have been selected); near-zero negatives are the most actionable cases for qualitative
review.

---

## 4. Proposed Integration into the FABN Optimizer

### 4.1 What changes (and what does not)

Shadow prices and reduced costs are available immediately after `model.optimize()` with no
modifications to the model structure. The integration is **purely additive**: we extract and
report information the solver already computes.

```
[Existing model: Section 0 → 1A → 1B → 2 → 3]
         ↓
[New Section 3B: Shadow Price Extraction & Interpretation]
         ↓
[Existing Section 4: Analytics]
```

### 4.2 What to extract from Gurobi

After `model.optimize()` and confirming `model.Status == GRB.OPTIMAL`, the following attributes
are available:

| Gurobi attribute | What it gives us |
|---|---|
| `constr.Pi` | Shadow price (dual value) of each named constraint |
| `constr.RHS` | Right-hand side of the constraint (for context) |
| `constr.SARHSLow / .SARHSUp` | Range over which the shadow price is valid (sensitivity interval) |
| `var.RC` | Reduced cost of each decision variable |
| `var.SAObjLow / .SAObjUp` | Range of objective coefficient over which the current basis is stable |

For the budget constraint (equality), we access `h_budget_constr.Pi`. For the duration gap
constraints, `dur_upper_constr.Pi` and `dur_lower_constr.Pi`. For each issuer's concentration
cap, `conc_{issuer}_constr.Pi`. For the PV shortfall cap, `pv_shortfall_limit.Pi`.

### 4.3 New outputs to produce

**Table 1 — Constraint Shadow Price Report**

| Constraint | Shadow price ($/unit) | Current RHS | Binding? | Stable range |
|---|---|---|---|---|
| Budget ($) | `π_budget` | $500M | Yes (equality) | [lower, upper] |
| Duration upper | `π_dur_up` | 0.30 yr | Yes/No | [lower, upper] |
| Duration lower | `π_dur_lo` | 0.30 yr | Yes/No | [lower, upper] |
| Issuer ABC | `π_issuer_ABC` | $25M | Yes/No | [lower, upper] |
| PV shortfall | `π_shortfall` | $5.04M | Yes/No | [lower, upper] |

**Table 2 — Bond Reduced Cost Ranking (excluded bonds)**

Sorted by reduced cost descending (least negative first = closest to entering the portfolio).
Includes decomposition into yield premium, capital charge, and constraint interactions.

**Chart — Shadow Price Heatmap over the facility quarters**

A bar chart of `π_{fac,q}` across the 33 quarters, revealing which quarters are the tightest
funding bottlenecks. Quarters with large FABN payments (especially the final principal payment)
should show elevated shadow prices.

### 4.4 Interpretation guidelines for the investment team

- **If `π_budget` is high:** the portfolio is yield-hungry; additional capital deployed in this
  environment would be highly productive. Consider whether H = $500M is the right ceiling.
- **If `π_dur_up` or `π_dur_lo` is high:** the duration band is the binding constraint on NII.
  This is the ALM team's call: is ±0.30 years the right tolerance, or is it a conservative
  default that can be revisited?
- **If an issuer's `π_issuer` is high:** the credit committee should be aware that the 5%
  concentration cap on this issuer has a measurable income cost. It may be worth a credit review
  to assess whether that cap can be raised.
- **If `π_shortfall` is high:** we are being forced to hold more liquid, cash-flow-matched assets
  than is strictly necessary for the coupon schedule, at the cost of NII. Consider whether `φ_sf`
  (currently 1%) can be widened.
- **Near-miss bonds (small negative RC):** these deserve manual review. A bond one rating upgrade
  away, or maturing two weeks earlier, might flip it into the optimal portfolio.

---

## 5. Extension: Shadow-Augmented Bond Scoring

Beyond post-hoc reporting, shadow prices can be used to construct a **shadow-augmented score**
for each bond in the universe — a single number that captures its total value to the portfolio,
not just its raw yield premium:

$$
\text{Score}_i = (y_i^{book} - r^{FABN}) 
               - \lambda \cdot \theta_i 
               + \underbrace{\sum_q \pi_{fac,q} \cdot CF^{bond}_{q,i}}_{\text{liquidity fit bonus}}
               + \underbrace{\pi_{dur} \cdot (D_{FABN} - |D_i - D_{FABN}|)}_{\text{duration fit bonus}}
$$

This score explicitly rewards bonds for:
- Paying cash flows in quarters where the FABN needs liquidity (high `π_{fac,q}`)
- Having duration close to `D_FABN` when the duration band is binding (high `π_{dur}`)

In principle, this score can be used as a **screening tool** before running the full optimizer — or
fed back into the objective as an additional term, making the optimizer explicitly aware of
structural fit beyond yield and capital charge.

> **Caution:** shadow prices are computed from one solved instance and change as market conditions
> evolve. Using them as fixed inputs to a subsequent optimization (a technique called *Benders
> decomposition* in the operations research literature) is valid but requires care to avoid circular
> reasoning. For now, the simpler post-hoc reporting is the recommended starting point.

---

## 6. Limitations

| Limitation | Detail |
|---|---|
| **Linearity assumption** | Shadow prices are exact only within the LP's current basis. Large constraint changes (e.g., doubling H) require re-solving. |
| **Degeneracy** | When multiple optimal bases exist (degenerate LP), some shadow prices may be zero even for binding constraints. Gurobi handles this gracefully but the analyst should check whether a constraint is binding regardless of its `Pi` value. |
| **Market regime dependence** | Shadow prices reflect the yield environment on the optimization date. They should be recalculated each time the optimizer is re-run; using stale shadow prices for bond screening is misleading. |
| **Integer variables** | If the model is extended to include binary variables (e.g., minimum lot sizes), the LP relaxation shadow prices are still informative but not exact for the mixed-integer problem. The current model is a pure LP, so this is not a concern today. |
| **SAP treatment** | Shadow prices are derived from the *statutory* (book-yield) objective. A bond's shadow value in a market-value (NEV) framework would be different. The two should not be mixed. |

---

## 7. Summary

Shadow prices are not an add-on or a complexity: they are the natural language in which a solved
linear program describes its own constraints. In the FABN SAP Optimizer, they translate directly
into actionable statements about the cost of the ALM mandate, the value of concentration limits,
the tightness of the liquidity constraint, and the hidden value of bonds excluded on raw yield
alone.

The practical integration requires no model changes — only additional code to extract, decompose,
and present the information Gurobi already computes. The proposed roadmap is:

1. Add a **Section 3B** to `FABN_Optimizer_SAP.ipynb` that extracts all dual values and reduced
   costs and presents Tables 1 and 2 above.
2. Add the same extraction to `FABN_Optimizer_SAP_Backtest.ipynb` inside `solve_day()`, recording
   per-day shadow prices to track how constraint costs evolve across the backtest horizon.
3. Produce the facility shadow price heatmap as a standing chart in the analytics section.

These three steps transform the optimizer from a black box that outputs allocations into a
transparent decision-support tool that explains *why* each allocation was made and *what it would
take* to do better.

