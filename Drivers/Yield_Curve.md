# The Yield Curve in Fixed Income

---

## What is the Yield Curve?

The yield curve is a snapshot of the relationship between yield (the return an
investor earns) and time to maturity across bonds of the same credit quality —
typically US Treasuries. At any given moment, it answers the question:
*what does the market demand to lend money for 1 month vs. 2 years vs. 30 years?*

A healthy economy typically shows an **upward-sloping** (normal) curve:
investors demand a premium for locking up capital longer, compensating for
inflation uncertainty and liquidity risk. But the curve changes shape
constantly in response to monetary policy, growth expectations, and
risk appetite.

> **Key insight:** The yield curve is not a static object. It shifts, tilts,
> and twists every day — and nearly all of that movement can be decomposed
> into just three independent factors: level, slope, and curvature.

---

## 1. Why the Yield Curve Matters for FABN

FABN (Funding Agreement-Backed Notes) portfolios are exposed to the yield
curve on **both sides** of the balance sheet.

### Asset Side

- The bond portfolio generates cash flows (coupons + principal) at fixed
  contractual rates. Those cash flows do not change when rates move.
- **What does change** is the mark-to-market price of each bond and the
  rate at which maturing proceeds can be reinvested.
- A parallel rise in yields reduces the price of every bond in the portfolio
  in proportion to its duration. A steepening of the curve affects
  long-duration positions more than short ones.
- G-spreads — the primary credit signal in this project — are defined as the
  bond's YTM minus the interpolated Treasury yield at the same maturity.
  Changes in the Treasury curve therefore mechanically affect how we measure,
  compare, and trade credit.

### Liability Side

- FABN liabilities carry a fixed crediting rate, so the liability cash flows
  themselves are not rate-sensitive.
- However, the **discount rate** used to value those liabilities is driven by
  market rates. A falling yield curve increases the present value of future
  liability payments, widening the asset-liability gap.
- This gap is the core of the **C3 interest rate risk charge**: if asset
  duration and liability duration diverge, a rate move creates a surplus or
  deficit. The curve determines the size of that move.

> **Key insight:** The yield curve affects the asset side through
> **price returns and reinvestment rates**, and the liability side through
> **discount rates and liability valuation**. Duration mismatch is the
> C3 risk, and the curve is what converts that mismatch into dollars of
> capital at risk.

---

## 2. Shape of the Curve: Three Summary Metrics

In practice, the entire curve can be summarized with three numbers calculated
daily from the raw tenor data.

| Metric | Formula | Economic Interpretation |
|--------|---------|------------------------|
| **Level** | 10Y yield | Overall rate environment; proxy for the long-run "price of money" |
| **Slope** | 10Y − 2Y | Steepness of the curve; negative = inverted = recession signal |
| **Curvature** | 2 × 5Y − (2Y + 10Y) | Richness of the belly vs. the wings; linked to convexity demand |

### Common curve regimes

| Slope (10Y − 2Y) | Regime | Typical Context |
|------------------|--------|----------------|
| < −25 bps | Deeply inverted | Peak monetary tightening; recession concerns |
| −25 to 0 bps | Mildly inverted | Late hiking cycle; growth slowdown |
| 0 to +50 bps | Flat / normalizing | Rate-cut cycle beginning; uncertainty |
| > +50 bps | Normal / steep | Expansion; market expects rising long-run rates |

The Batch 1 data window (March 2024 – February 2026) spans the transition
from deep inversion (post-2022 hiking cycle) through progressive
normalization — a particularly rich period for regime analysis.

---

## 3. Mathematical Decomposition: PCA

### Why PCA?

Eleven tenor points move together in structured ways. Rather than modeling
each tenor independently, PCA on daily yield *changes* reveals the
**orthogonal shocks** that actually drive rate risk:

$$\Delta y_t = F_t \Lambda^\top + \varepsilon_t$$

Where:
- $\Delta y_t$ = vector of daily yield changes across all tenors
- $F_t$ = row vector of **factor scores** on date $t$ (the "how much" of each shock)
- $\Lambda$ = matrix of **factor loadings** (the "shape" of each shock across tenors)
- $\varepsilon_t$ = residual noise

**Empirically, three factors explain ~99% of all yield curve variance:**

| Factor | Loading Shape | Interpretation |
|--------|--------------|---------------|
| **PC1 (Level)** | Roughly uniform across tenors | All rates move together — parallel shift |
| **PC2 (Slope)** | Negative at short end, positive at long end | Twist — curve steepens or flattens |
| **PC3 (Curvature)** | Positive at ends, negative in belly | Butterfly — belly moves vs. wings |

This decomposition was first documented empirically by Litterman & Scheinkman
(1991) and has remained stable across decades and rate environments.

### Practical use in this project

Each bond's G-spread can be regressed on the three PC scores:

$$\Delta s_{i,t} = \alpha_i + \beta^{(1)}_i \cdot F^{(1)}_t + \beta^{(2)}_i \cdot F^{(2)}_t + \beta^{(3)}_i \cdot F^{(3)}_t + \varepsilon_{i,t}$$

The coefficient $\beta^{(1)}_i$ captures how much bond $i$'s G-spread
reacts to a level shift — a proxy for its rate sensitivity beyond what
duration alone captures. Bonds with near-zero betas are "pure credit plays";
bonds with large betas are more rate-driven.

---

## 4. The Nelson-Siegel Model

An alternative to PCA is the **Nelson-Siegel** parametric curve, which fits
a smooth yield curve at each point in time using four parameters:

$$y(\tau) = \beta_0 + \beta_1 \cdot \frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} + \beta_2 \cdot \left(\frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} - e^{-\tau/\lambda}\right)$$

Where:
- $\tau$ = time to maturity (in years)
- $\beta_0$ = long-run level (the yield as $\tau \to \infty$)
- $\beta_1$ = slope loading (decays to zero as $\tau$ grows)
- $\beta_2$ = curvature / hump loading (peaks at intermediate maturities)
- $\lambda$ = decay rate (controls where the hump appears)

Nelson-Siegel is particularly useful for **G-spread interpolation**: rather
than linearly interpolating between two treasury tenors to find the rate at
a bond's exact maturity, a smooth parametric curve avoids distortions at
off-the-run maturities. The Diebold-Li (2006) extension also treats
$\beta_0$, $\beta_1$, $\beta_2$ as latent factors with their own dynamics,
enabling term structure forecasting.

---

## 5. Connection to FABN and the Optimizer

### C3 interest rate risk

The NAIC C3 framework stress-tests the portfolio under a range of interest
rate scenarios. Each scenario shifts the yield curve (typically in level and
slope), reprices the bond portfolio, and measures the resulting surplus
change. The PCA factors define the natural scenario axes:

- A large PC1 shock → parallel shift scenarios (the dominant C3 driver)
- A PC2 shock → twist scenarios (affect short-duration vs. long-duration bonds differently)
- Combined PC1 + PC2 → reproduce the NAIC's prescribed rising / falling rate paths

### Duration matching constraint

The optimizer enforces $|D_A(w) - D_L| \leq \epsilon$, where $D_A$ is the
weighted average duration of the bond portfolio and $D_L$ is the liability
duration. This constraint is the single-factor (level-only) approximation to
yield curve risk. An extension using **key rate durations** (KRDs) at the 2Y,
5Y, and 10Y tenors would constrain mismatch separately at each curve point —
capturing slope and curvature risk that a single duration number cannot.

### G-spread signal quality

The momentum signal is built on G-spreads. If G-spreads are heavily
contaminated by yield curve moves (high $\beta^{(1)}_i$), the signal
is mixing rate risk with credit signals. Residualizing spreads against the
PCA factors — using only $\varepsilon_{i,t}$ as the signal input — would
produce a purer credit momentum factor.

---

## References

1. **Litterman, R. & Scheinkman, J. (1991).** *Common Factors Affecting Bond
   Returns.* Journal of Fixed Income, 1(1), 54–61.
   The foundational paper establishing that three factors (level, slope,
   curvature) explain ~99% of Treasury yield curve variation.
   https://doi.org/10.3905/jfi.1991.692347

2. **Nelson, C. R. & Siegel, A. F. (1987).** *Parsimonious Modeling of Yield
   Curves.* Journal of Business, 60(4), 473–489.
   Introduces the parametric three-factor yield curve model used in central
   banks worldwide for curve fitting and interpolation.
   https://doi.org/10.1086/296409

3. **Diebold, F. X. & Li, C. (2006).** *Forecasting the Term Structure of
   Government Bond Yields.* Journal of Econometrics, 130(2), 337–364.
   Reinterprets Nelson-Siegel as a dynamic factor model; widely used for
   yield curve forecasting and scenario generation.
   https://doi.org/10.1016/j.jeconom.2005.03.005

4. **Fabozzi, F. J. (2012).** *Fixed Income Mathematics, 4th ed.* McGraw-Hill.
   Comprehensive reference for duration, convexity, key rate durations,
   and G-spread mechanics in the context of portfolio management.

5. **Federal Reserve Board (2024).** *H.15 Selected Interest Rates.*
   Daily Treasury yields used as the risk-free benchmark in this project.
   https://www.federalreserve.gov/releases/h15/

6. **NAIC (2023).** *Life Risk-Based Capital Report Including Overview and
   Instructions for Companies.* National Association of Insurance Commissioners.
   Defines C3 interest rate risk scenarios and capital requirements that
   constrain the FABN portfolio optimizer.
   https://content.naic.org/sites/default/files/inline-files/2023-lrbc-report.pdf
