# Duration & Swaps Reference — Interest-Rate Hedging for the FABN Book

> **Audience:** an AI agent (or engineer) that needs deep context on how duration is measured
> and how interest-rate swaps are used to manage it in this system, and *why*.
> Source of truth: `Optimization/fabn_finance.py` (swap + duration math),
> `Optimization/fabn_data_pipeline.py` (`D_FABN`), `backend/services/optimizer_service.py`
> (how swaps enter the LP).
>
> **Two-state document.** **[CURRENT]** = code that runs today (pay-fixed overlay, CVaR-governed
> risk). **[RETIRED]** = mechanics that were live before the Step 1-4 redesign shipped and have
> since been replaced (receive-fixed overlay, the PV-shortfall cap, the held-to-maturity bond
> exclusion) — kept here for context on why the design changed, not as current behavior.
> **[PLANNED]** = further redesign work (hedge-ratio rebalancing, credit budgets) not yet
> implemented. Read alongside `docs/agent-context/optimization-reference.md`.

---

## 0. What "FABN" is, and why its rate risk matters

A **FABN (Funding Agreement-Backed Note)** is how the insurer raises institutional funding: it
issues a note to investors and owes them a **fixed crediting rate** `r_FABN` (the note coupon,
3.205%) plus principal at maturity (issued 2022-09-06, matures 2027-09-06). The **FABN is a
liability** — a fixed stream of dated cash outflows (semi-annual coupons + a principal bullet).
The note proceeds (`H = $500M`) are invested in bonds (the **asset**). Profit = the spread the
assets earn over `r_FABN`.

Because the FABN is a *fixed-rate* liability, it has a **duration** (`D_FABN`): its present value
rises when rates fall and falls when rates rise, just like a bond. The assets also have a
duration. **Interest-rate risk to the insurer is a mismatch between the two.** Duration hedging
exists to keep that mismatch small so that *surplus* (assets − liability) is insulated from rate
moves — leaving the insurer exposed only to the **credit spread** it is actually paid to take.

---

## 1. What "duration" is in this codebase

Duration is computed in `Optimization/fabn_finance.py` from each instrument's **cash flows**,
not from a data feed.

**Macaulay duration** (`macaulay_duration`, `fabn_finance.py:89`):
```
D_mac = Σ_t [ t · CF_t · (1+y)^(-t) ] / Σ_t [ CF_t · (1+y)^(-t) ]
```
The present-value-weighted average time to receive the cash flows, in years. `CF_t` are cash
flows per \$1 face, `t` is time in years, `y` is the discount yield.

**Modified duration** (`modified_duration`, `:103`), which is what the optimizer uses:
```
D_mod = D_mac / (1 + y)
```
**Plain English:** `D_mod` is the % change in price for a 1-unit (100%) change in yield; scaled
down, a **1 bp** rate move changes price by roughly `D_mod · 0.01%`. A 2-year bond has
`D_mod ≈ 1.9`; a 10-year bond `≈ 7.8`. Longer maturity ⇒ larger duration ⇒ more rate
sensitivity.

**Inputs that drive it:**
- **Cash-flow schedule** (coupon rate, frequency, maturity) → `CF_t`, `t`.
- **Discount yield** `y` — per bond, typically `risk-free + spread` (with a Bloomberg fallback,
  `modified_durations` `:111`).
- Pipeline stores the per-bond vector as `durs` and feeds it to the LP.

**The FABN's own duration** (`fabn_data_pipeline.py:323-324`):
```
mac_D_FABN = Σ_t t · CF^FABN_t / Σ_t CF^FABN_t        (PV-weighted, on the FABN's own schedule)
D_FABN     = mac_D_FABN / (1 + r_FABN/2)              # semi-annual convention
```
`D_FABN` is the **rate-duration target** the asset book is matched to.

**Key identity used throughout the design.** A bond's yield is `y = risk-free + spread`, so
```
dP/P ≈ − D_mod · dy = − D_mod · (d·risk-free + d·spread)
```
→ **rate DV01 = spread DV01** for a fixed bond (same `D_mod` multiplies both). This is *why* a
swap can separate the two risks: a swap moves only with the risk-free/SOFR leg, so it cancels
the rate term and leaves the spread term untouched. (Verified numerically in
`swap_intuition_lab` §2.)

---

## 2. How swaps are used mechanically

Swap math lives in `Optimization/fabn_finance.py:309-444`, all **per \$1 notional**.

### 2.1 [RETIRED] Receive-fixed overlay

Before the Step 1-4 redesign, the overlay was **receive-fixed / pay-floating**: the book received
a known fixed coupon and paid SOFR-linked floating. It behaved like *adding a bond* — positive
duration, value rises when rates fall. This was retired in favor of the pay-fixed overlay in
§2.2 once the bond universe opened up to post-FABN-maturity bonds (§1, HtM exclusion removed) —
a book that can now hold longer bonds needs a hedge that *subtracts* duration, not adds it.

| Function | Formula (per \$1) | Returns | Role |
|---|---|---|---|
| `swap_fixed_leg_duration(tenor, fixed_rate, r_disc)` `:319` | `D_mod` of a par bond with the same coupon/tenor | modified duration (years, **positive** as returned; negated by the caller for the pay-fixed overlay, see §2.2) | The swap's duration contribution `swp_dur_k`. |
| `swap_quarterly_cashflows(fixed_rate, r_float, tenor, n_q)` `:354` | `(fixed_rate − r_float)·dt_settle` per settlement, mapped to quarters | net CF per \$1 per quarter | Feeds the facility recursion (`CF^{swap}_q`). |
| `swap_fair_value(fixed_rate, r_market, tenor)` `:406` | `PV(fixed leg at r_market) − 1` | mark-to-market per \$1 | Risk reporting / IMR on unwind (not in the LP objective). |

**[RETIRED] How the old receive-fixed overlay mapped to a duration adjustment:**
```
swp_dur_k = swap_fixed_leg_duration(tenor_k, c_swap_k, r_float)          # positive
net asset dollar-duration = Σ_i durs_i · h_i  +  Σ_k swp_dur_k · v_k     # swap ADDED duration
```
with differentiated fixed rates `c_swap = [4.3, 4.4, 4.5]%` (not at-the-money) — a receive-fixed
swap was used to *top up* duration when the eligible (short, pre-FABN) bonds fell short of
`D_FABN`. Superseded by §2.2.

### 2.2 [CURRENT] Pay-fixed overlay

To hold **long, high-spread** bonds while staying duration-matched, the overlay is
**pay-fixed / receive-floating**: pay a known fixed coupon, receive SOFR. This behaves like
*shorting a bond* — **negative duration**, value rises when rates rise.

- **Value per \$1** (pay-fixed): `V_pay(r) = 1 − P_fixed(r)`, where `P_fixed(r)` is the price of
  the fixed leg valued as a par bond. `V_pay = 0` at inception (fixed = par rate); `V_pay > 0`
  when rates rise (the hedge *gains*, offsetting the bond's loss).
- **Duration contribution:** `dV_pay/dr = +D_sw` (opposite sign to a bond), so in the book it
  contributes duration `−D_sw` per \$1 notional:
```
net asset duration = ( Σ_i durs_i · h_i  −  D_sw · Σ_k v_k ) / H     # swap SUBTRACTS duration
```
- **Spread sensitivity = 0:** the swap references SOFR, not any issuer's credit, so it leaves
  credit-spread exposure fully intact. That is the entire point: shed the rate risk you are not
  paid for, keep the spread risk you are.
- **Carry:** the live swap is priced **at-the-money** (`c_swap = r_float` for every tenor), so
  carry `(c_swap − r_float)·v` is ~zero by construction — the swap does not add or remove income;
  its value is purely the hedge, so the optimizer may hold longer, higher-spread (now including
  post-FABN-maturity) bonds without the sale-price rate risk that used to require excluding them.

**[CURRENT] Live parameters** (`optimizer_service.py:245-253`):
```
K = 3 tenors [1, 2, 3]y, all at-the-money: c_swap_k = r_float = 4.35%
swp_dur_k = -swap_fixed_leg_duration(tenor_k, r_float, r_float)          # negated -> negative
net asset dollar-duration = Σ_i durs_i · h_i  +  Σ_k swp_dur_k · v_k     # swap SUBTRACTS duration
```
capped at `Σ_k v_k ≤ 0.20·H` (`optimizer_service.py:354-358`, unchanged from the retired design).

Full derivations, sign checks, and the `bond DV01 − swap DV01 = target` identity are in
`swap_intuition_lab` §6 (with a verification cell).

---

## 3. Core rationale — why we hedge duration at all

**Goal: reduce the FABN book's exposure to interest-rate risk, so the insurer earns the credit
spread it is paid for without carrying rate risk it is not paid for.**

The causal chain, unhedged:

1. The FABN is a **fixed-rate liability** with duration `D_FABN`. If market rates **fall**, the
   present value of that liability **rises** (you owe a now-above-market coupon); if rates
   **rise**, its PV **falls**.
2. The assets also move with rates, by their own duration `D_A`.
3. **Surplus = assets − liability.** Its sensitivity to a rate move `Δr` is approximately
   `ΔSurplus ≈ − (D_A · MV_A − D_FABN · MV_L) · Δr`. If `D_A ≠ D_FABN`, surplus swings with
   rates — an *uncompensated* P&L that the risk committee and regulators penalize.
4. **Terminal-date danger (the acute case).** At the FABN maturity you must repay face. If you
   hold bonds that outlive the note and rates have **risen**, those bonds' **market value has
   fallen**; selling them to repay the note **crystallizes the loss**. Duration mismatch turns a
   rate move into a realized funding shortfall.

**How the swap overlay offsets it.** A swap moves with rates but not with the issuer's credit.
Sizing the overlay so the **net** asset duration equals `D_FABN` makes `D_A · MV_A` track
`D_FABN · MV_L`, so `ΔSurplus ≈ 0` for a parallel rate move — the rate risk is neutralized while
the bonds' **spread** exposure (the paid-for risk) is untouched. In the [CURRENT] design a
**pay-fixed** swap does this for a *long, open-universe* book (subtracting the excess duration);
the [RETIRED] receive-fixed overlay instead topped up a *short* book to reach the target, back
when post-FABN-maturity bonds were banned outright rather than hedged.

> Subtlety worth stating: matching net asset duration to `D_FABN` immunizes **surplus**, not the
> asset market value alone. The assets still carry `D_FABN` worth of rate duration *by design*;
> it is only *net of the liability* that rate risk vanishes. This is exactly what the
> asset-vs-surplus CVaR comparison shows (`swap_intuition_lab` §11.3).

---

## 4. Constraints, targets & rebalancing triggers

| Item | Formula | Plain English | Rationale | Notes |
|---|---|---|---|---|
| **[RETIRED as hard bound] Duration band** (`optimizer_service.py:311-318`) | `\|Σ_i durs_i h_i ± Σ_k swp_dur_k v_k − D_FABN·H\| ≤ eps_D_eff·H` | Net asset duration within `eps_D_eff` years of `D_FABN`. | Was the primary risk control; now relaxed to an inert `eps_D_eff = 100yr` band whenever CVaR is active (always, currently) — the LP still reports the gap for information, it just never binds. | `eps_D` request param still accepted but has no effect while CVaR governs. |
| **Swap notional cap** (`:354-358`) | `Σ_k v_k ≤ v_max_frac·H` | Total swap notional ≤ 20% of book. | Bounds derivative leverage & counterparty/collateral exposure. | `v_max_frac = 0.20`. In the [CURRENT] pay-fixed design this also bounds how far a long book can be duration-neutralized (see optimization-ref Example B). |
| **[CURRENT] CVaR on MV/BV** (`:360-369`) | `ζ + 1/((1−α)S)·Σ_ω z_ω ≤ φ_cvar·H`, `z_ω ≥ loss_ω − ζ`, `z_ω ≥ 0` | Cap the average forced-sale loss in the worst `(1−α)` tail of rate+spread scenarios. | Directly bounds the forced-sale loss the retired HtM ban used to prevent by exclusion instead; a *coherent* risk measure, LP-representable (Rockafellar–Uryasev). Now the primary risk control, replacing the duration band and the retired PV-shortfall cap. | `α = 0.95` (cvar_alpha), `φ_cvar` request param (default 0.01). Scenarios (`cvar_relloss`, `cvar_d_rate`) come from `fabn_data_pipeline.py`'s historical shock-scenario section. |
| **[PLANNED] Hedge-ratio target** | `v* = (Σ_i D_i(t)·MV_i(t) − D_tgt·MV_assets(t)) / D_sw(t)` | The swap notional that brings net dollar-duration to target *right now*. | The number you rebalance **to** as the book and time evolve. | Recomputed each period; reproduces the optimizer's `v` at t=0 (verified, lab §12). |
| **[PLANNED] Rebalance trigger (no-trade band)** | rebalance when `\|net_dur(t) − D_tgt\| > δ` | Leave the swap alone until net duration drifts outside `D_tgt ± δ`, then reset to `v*`. | Trades off tracking error vs. transaction cost — avoids churning the swap every tick. | Same logic as the duration band, applied to *rebalancing*. Also rebalance on any material trade/maturity. |

### Why the hedge must be rebalanced (three drivers)
1. **Composition** — a bond matures or is traded ⇒ `Σ D_i MV_i` jumps ⇒ required `v` jumps.
   Direction rule: a maturity/duration-sale ⇒ **unwind** pay-fixed; extending/reinvesting long ⇒
   **add** pay-fixed.
2. **Time decay** — bond and swap durations shrink at *different* speeds, so `v*` drifts **even
   with no trades** (a static swap slowly de-hedges).
3. **Convexity** — durations depend on the rate level, so a large rate move nudges the ratio.

### How rebalancing enters the model **[PLANNED]**
Model **net** swap notional as a per-period decision variable and add a transaction-cost penalty
on `|Δv_k|` to the objective (exactly like bond turnover, `optimizer_service.py:289-290, 265`).
This keeps the problem linear and lets the CVaR constraint "see" the resized hedge. Mechanically
the desk chooses among (a) partial unwind at market (realizes the swap's MtM), (b) an offsetting
swap, or (c) partial novation — but the model represents only the *net* notional change.

---

## 5. Worked examples

### Example A — [RETIRED] receive-fixed swap topping up a short book

This example describes the retired design, where post-FABN bonds were banned by a hard HtM
exclusion (also retired — see optimization-reference.md) and the duration band was a hard bound.
Kept for context on the problem the receive-fixed overlay used to solve.

Eligible bonds (post-FABN bonds banned by HtM) average duration `D_A = 2.2`, but
`D_FABN = 2.8` with `eps_D = 0.3` ⇒ band `[2.5, 3.1]`. The pure-bond book at 2.2y is **below**
the band — infeasible on bonds alone.

- Add a **receive-fixed** 3y swap, `swp_dur ≈ +2.7` per \$1. On budget `H`, holding bonds worth
  `H` at 2.2y gives dollar-duration `2.2·H`; the target midpoint is `2.8·H`.
- Needed swap notional: `swp_dur·v = (2.8 − 2.2)·H ⇒ v ≈ 0.6·H / 2.7 ≈ 0.22·H`.
- But `v ≤ 0.20·H` (cap) ⇒ the swap can lift duration to `2.2 + 2.7·0.20 = 2.74`, just inside
  the band. **The receive-fixed swap rescued feasibility** by adding the missing duration.

### Example B — [CURRENT] pay-fixed swap stripping duration off a long book

Hold a 10-year bond book, `D_A = 7.8`, target `D_FABN = 2.8`. Use a 5y **pay-fixed** swap,
`D_sw ≈ 4.5` per \$1 (subtracts duration).

1. **Duration gap to remove:** `(7.8 − 2.8)·H = 5.0·H` of dollar-duration.
2. **Swap notional:** `v = 5.0·H / 4.5 ≈ 1.11·H` — *more than 100% of the book*. The 20% cap
   (`v ≤ 0.20·H`) means a single 5y swap can only remove `4.5·0.20 = 0.9y`, taking net duration
   to `7.8 − 0.9 = 6.9` — still far above target.
3. **Reading:** to run a *fully* duration-neutral 10y book you would need a much larger notional
   budget (raise `v_max_frac`) or a longer-tenor swap (higher `D_sw`). In practice the optimum
   blends some long bonds (partially hedged) with shorter bonds, and the **CVaR constraint** and
   credit budgets — not the duration band — become the binding risk limits.
4. **Rate-move check (why it reduces FABN rate exposure).** Suppose rates rise `+100 bp` on a
   \$100 slice held as the 10y bond hedged down to net `2.8y`:
   - Bond MV change ≈ `−7.8 · 1% · $100 = −$7.80`.
   - Pay-fixed swap MV change ≈ `+ (7.8 − 2.8) · 1% · $100 = +$5.00` (the hedge gains).
   - **Net asset change ≈ −$2.80**, which now matches the liability's `−D_FABN·1%·$100 = −$2.80`
     move ⇒ **surplus ≈ unchanged**. Unhedged, surplus would have dropped ~\$5 for the same
     move. That \$5 is the rate risk the swap removed; the residual is the (intended) spread and
     the `D_FABN` matched component.

Full runnable versions (with the terminal-date dispersion and the reinvestment fork) are in
`swap_intuition_lab` §7–§12.

---

## 6. Frequently needed context (FAQ)

**Q: Is the current overlay pay-fixed or receive-fixed?**
**[CURRENT] pay-fixed** — the code negates `swap_fixed_leg_duration`'s return value, so `swp_dur`
is *negative* and the overlay *subtracts* duration to strip it off a long, open-universe book.
The **[RETIRED]** receive-fixed overlay used a positive `swp_dur` to top up a short book, back
when post-FABN bonds were banned outright. Always check the sign of `swp_dur` in the code you
are reading.

**Q: Does the swap hedge credit-spread risk?**
No. A swap references SOFR/rates, not issuer credit — its spread DV01 is zero. It hedges *rate*
risk only. Spread-widening risk is the compensated exposure the strategy deliberately keeps; it
is controlled by the CVaR constraint (§4), not by the swap.

**Q: How is swap notional `v` sized?**
By the CVaR risk budget inside the LP (`v` is a decision variable, not a fixed ratio) — it's sized
so the worst-tail forced-sale loss stays under `φ_cvar·H`, subject to `Σ v_k ≤ v_max_frac·H`. The
duration band is still computed and reported but no longer binds (§4). The closed-form
"what notional hits a duration target *now*" is the [PLANNED] hedge-ratio `v*` in §4.

**Q: What discount yield goes into duration?**
Per bond, `risk-free + spread` (with a Bloomberg fallback where the analytic solve fails,
`modified_durations` `:111`). The FABN uses its own `r_FABN` with a semi-annual convention
(`D_FABN`, pipeline `:324`).

**Q: Why match to `D_FABN` and not to zero?**
Because the objective is to immunize **surplus** (assets − liability), not asset value. Matching
asset duration to the liability's duration makes their rate moves cancel. Hedging assets to zero
duration would *re-introduce* a mismatch against the fixed-rate liability.

**Q: A bond matured / we traded — what happens to the swap?**
Rebalance to the new `v*` (§4). A maturity lowers bond duration ⇒ unwind some pay-fixed; a
long reinvestment raises it ⇒ add. Use the no-trade band (`|net_dur − D_tgt| > δ`) to avoid
churning, and represent it in the model as a `|Δv|` turnover cost.

**Q: What is the secondary cash-flow risk the swap introduces?**
Net settlements (`swap_quarterly_cashflows`) flow through the facility, and — for a
collateralized pay-fixed swap — **variation margin** must be posted when the swap loses value
(rates fall). That is a real liquidity draw; the planned design sizes a buffer for it (flagged in
`swap_intuition_lab` next-steps).

**Q: Where does the swap's mark-to-market go?**
`swap_fair_value` (`:406`) computes MtM for risk reporting and IMR treatment on unwind; it is
**not** in the LP objective (which is book/SAP-based). Realized rate gains on unwind amortize via
the `IMRLedger` (`fabn_finance.py:232`), consistent with statutory accounting.

---

## 7. See also (ground truth)

- `Optimization/fabn_finance.py` — duration: `macaulay_duration` `:89`, `modified_duration`
  `:103`; swaps: `swap_fixed_leg_duration` `:319`, `swap_quarterly_cashflows` `:354`,
  `swap_fair_value` `:406`; IMR: `IMRLedger` `:232`.
- `Optimization/fabn_data_pipeline.py` — `D_FABN` `:323-324`, `r_FABN` `:58`, `qtr_fabn_cf`
  `:332-333`.
- `backend/services/optimizer_service.py` — swap params `:245-253`, duration band `:311-318`
  (relaxed to inert while CVaR is active), swap in facility recursion `:325-335`, swap notional
  cap `:354-358`, CVaR tail-loss block `:360-369`.
- `Optimization/fabn_optimizer_sap.py` — the literal notebook-mirror version of the same LP, kept
  in sync section-by-section with `FABN_Optimizer_SAP_Shadow_SWAP.ipynb`.
- `docs/agent-context/optimization-reference.md` — the full objective/constraint set and how the
  swap terms sit inside the LP.
- `swap_intuition_lab/swap_intuition_lab.ipynb` — runnable, verified derivations: the
  rate-vs-spread duration identity (§2), pay-fixed swap value & sign (§6), BV/MV over scenarios
  (§7), lifecycle & terminal date (§8), CVaR on MV/BV incl. Rockafellar–Uryasev (§11), and swap
  rebalancing (§12).
