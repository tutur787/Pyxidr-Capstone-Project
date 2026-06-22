# Size of the Prize — Perfect-Foresight Upper Bound for FABN Trading

## Executive summary

A McKinsey consultant who specializes in insurance-asset trading reviewed the FABN optimizer and
said we are on the right path, but that to make a **business case** we need to know the **size of the
prize**: *if we knew the next two years of prices perfectly, what is the maximum cumulative SAP / NII
we could earn — carry plus realized trading gains, net of trading cost — by trading as much as it is
worth?*

This is a **clairvoyant (perfect-foresight) upper bound**. It is **not a strategy** — perfect
foresight is unattainable. It is a **ceiling**: the most a re-optimizing trader could *possibly* book
over this window if every future price were known. Its business value is the **gap** to the realistic
dynamic backtest:

- **Prize ≈ realistic dynamic** → almost all the value is static carry; smarter trading buys little.
  Don't over-invest in signal/strategy R&D.
- **Prize ≫ realistic dynamic** → there is real tradeable upside being left on the table; the
  engineering effort to close part of that gap is justified.

We frame the prize in the **same units as the backtest** — cumulative net statutory income ($),
directly comparable to the **$27.76M static** baseline and the ~+10–15% tuned-dynamic result.

---

## The intuition: where a prize can and cannot come from

Two sources of edge, only one of which is real under SAP:

1. **Carry timing / rotation (real).** Under SAP you hold at amortized cost and earn the **book yield
   locked at purchase**. When rates rise, the market book yield on new paper rises, but your existing
   holdings stay stuck at their old, lower locked yield. With foresight you can **sell the stale
   low-yield lot and re-buy higher carry at exactly the right moment**, and you can **time initial
   purchases at local book-yield peaks** (price dips) to lock the best available yield. This is a
   genuine, exploitable source of prize.

2. **Gains trading (a mirage — and deliberately so).** You might think: with foresight, buy low / sell
   high and pocket the price gains. But the **Interest Maintenance Reserve (IMR)** *amortizes* a
   realized rate-driven gain straight-line over the **sold bond's remaining life** — it is **never**
   booked in full at the sale date. So pure round-trip gains trading has **no free lunch**: the gain
   you harvest is exactly the future income you give up. This is the whole point of the IMR, and it is
   why the prize is fundamentally a **carry story**, not a price-flipping story.

> This is also the project's standing guardrail: **never** inflate earnings by collapsing a bond's
> future cashflows (or a future sale) into an earlier date as "proceeds." Realized gains flow through
> `fabn_finance.IMRLedger` (amortized, never front-loaded), and post-FABN bonds never fund the
> liability from principal — the PV-shortfall cap forbids it.

---

## The formulation: a time-expanded "trade-arc" LP

The challenge is that SAP **book-yield locking** is path-dependent (income on a holding depends on
*when each lot was bought*), which is normally non-linear. Perfect foresight dissolves this: if the
whole price path is known, each possible trade has a **constant, pre-computable** profit. So we model
the decision as a flow over a time-expanded network.

**Rebalance grid.** Choose `M` rebalance dates `τ_0 < … < τ_M` (a sub-sample of the backtest's daily
dates; default **monthly**). Carry accrues daily *between* grid points; trades happen *at* grid
points. A coarser grid offers **fewer** trade opportunities, so it **under-states** the true ceiling —
a conservative (safe) direction. We report a **grid-sensitivity sweep** to show the prize rising then
plateauing as the grid refines.

**Trade arc.** `a = (bond i, buy node m, close node n)`. Decision variable `x_a ≥ 0` = dollars of
**book value** routed through the arc. With foresight, the per-dollar profit is a constant:

```
coef_a = net_carry_a + imr_window_a − cost_a

net_carry_a = ((Y[m,i] − r_FABN) − λ·θ_i) · (t_n − t_m)     # locked carry, net of capital cost
imr_window_a = g_a · min(1, (window_end − t_n)/(t_mat − t_n))   # IMR release inside the window; 0 if not sold
cost_a       = TAU[m,i] (+ TAU[n,i] if sold before maturity)    # bid-ask/2 on each traded leg
g_a          = realized_gain_on_sale(1, mid[n,i], cb_a)         # cb_a = amortized cost basis at sale
λ            = cost_of_capital · RBC_bar
```

A bond can close three ways: **sold** at a later grid node (pays the sell-leg `TAU`, books the
rate-driven IMR gain/loss), **redeemed at par** at maturity in-window (no sell cost, no gain — the
amortized cost has reached par), or held to the **window cutoff** (no cost, no gain, conservative —
open positions are simply stopped, never liquidated for credit).

**Book-value conservation (the anti-liquidation discipline).** We conserve **book value**, exactly the
backtest's `Σ h_i == H` invariant. A dollar enters an arc at `m` and is freed at `n` to fund new buys;
the rate-driven gain trickles into **income** (IMR), and is **never** added back to redeployable
principal. Selling a bond at a gain does **not** hand you extra cash to reinvest — precisely the
behavior that prevents fictitious coverage.

**Objective and constraints.**

```
max  Σ_a coef_a · x_a
s.t. book-value flow conservation across grid nodes (buys ≤ cash freed so far)
     soft duration band per interval  (breach penalized at dur_pen; always feasible)
     issuer concentration cap per interval (≤ delta_iss · H)
     [facility recursion + PV-shortfall cap on the quarterly grid — funds the final payment]
```

Capital is **priced into the objective** (`λ·θ_i` inside `net_carry`), matching the SAP optimizer's
`λ·RBC` term. With a monthly grid the model is ~50k arcs — a comfortable LP for Gurobi.

---

## Worked intuition (why the gap is informative)

- A **flat** rate path ⇒ foresight-dynamic equals foresight-static: nothing to time, **prize gap ≈ 0**.
  (This is a unit test: `test_flat_path_gives_no_foresight_edge`.)
- A path where some bond's book yield **spikes** (price dips) ⇒ foresight buys it at the trough and
  locks the high carry; static cannot. The gap is the **value of timing**. (Unit test:
  `test_foresight_beats_static_when_a_pickup_exists`.)
- The realistic dynamic strategy captures *some* of this gap without foresight (sensible re-optimization);
  the prize tells you **how much head-room remains**.

The headline read: the prize should sit **above** the $27.76M static and the tuned dynamic (it is an
upper bound), and **below** a constraint-relaxed loose ceiling we also print for context. If it does
not, there is a modeling bug — the notebook **asserts** these orderings (no silent `+inf%`, same
lesson as the backtest's earlier feasibility bug).

---

## How to read the number (business framing)

| Quantity | Meaning |
|---|---|
| **Prize (windowed)** | Max cumulative net statutory income over the 2y window, IMR recognized only as it releases inside the window — the apples-to-apples ceiling vs the backtest's CumNet. |
| **Prize (fully recognized)** | Same solution, crediting the *ultimate* IMR release — the long-run ceiling (a short window under-states IMR). |
| **Prize − tuned dynamic** | **Head-room**: tradeable upside our realistic strategy has not captured. The "size of the prize." |
| **Carry / IMR / cost decomposition** | *Where* the prize comes from — confirms it is carry-timing, not a discounting artifact. |

---

## Limitations (state them plainly)

- **Foresight is unattainable** — this is a ceiling, not a deployable strategy. The *achievable* side
  is the realistic dynamic backtest; the prize only bounds it.
- **No market impact.** "Trade a lot" is modeled as infinitely liquid at bid-ask/2 (`TAU`), with no
  price impact or capacity limit. This **over-states** the ceiling — a real desk moving size pays more.
  (Capacity/impact modeling is the natural next extension.)
- **Coarse rebalance grid under-states** the prize slightly (fewer trade chances) — the safe direction;
  the grid sweep shows where it plateaus.
- **Clean prices; AVR excluded.** Credit-default reserve (AVR) is out of scope, as in the rest of the
  MVP; only rate-driven IMR gains are recognized.
- **Quarterly facility approximation** for liquidity timing, identical to the backtest's.

---

## Relationship to the rest of the folder

- Reuses `fabn_finance.py` for every primitive (`amortize_price_to_par`, `realized_gain_on_sale`,
  `IMRLedger` semantics) and consumes the **same precompute panels** as
  `FABN_Optimizer_SAP_Backtest.ipynb` (exported to `prize_panels.npz`) so the two never silently
  diverge.
- Complements `Shadow & SWAP Analysis/` (which asks *which constraint is most expensive* and *can
  swaps cut turnover*); this folder asks the prior question — *is there enough prize to be worth it?*
