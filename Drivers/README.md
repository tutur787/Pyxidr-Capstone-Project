# Mean Reversion — CIR Model Analysis

This folder contains the theoretical framework and simulation code for
**mean reversion in interest rates**, using the Cox-Ingersoll-Ross (CIR)
model in the context of **Funding Agreement-Backed Notes (FABN)**
portfolio optimization.

---

## What is Mean Reversion?

Interest rates tend to return to a long-term equilibrium level $\theta$
over time — they cannot rise or fall indefinitely:

- **Very high rates** suppress economic activity → central banks cut rates
- **Very low rates** stimulate borrowing → inflation builds → rates rise

This behavior is captured mathematically by the CIR model:

$$dr_t = \kappa(\theta - r_t)\,dt + \sigma\sqrt{r_t}\,dW_t$$

| Parameter | Symbol | Role |
|-----------|--------|------|
| Speed of reversion | $\kappa$ | How fast rates return to $\theta$ |
| Long-run mean | $\theta$ | Equilibrium level |
| Volatility | $\sigma$ | Magnitude of random shocks |

---

## Why it Matters for FABN

Mean reversion operates on **both sides** of the FABN balance sheet:

<table>
<tr>
<th>Asset side (C1)</th>
<th>Liability side (C3)</th>
</tr>
<tr>
<td>Bond coupons are fixed at issuance and do not revert</td>
<td>FABN crediting rate is fixed and must be paid regardless of market conditions</td>
</tr>
<tr>
<td align="center">↓</td>
<td align="center">↓</td>
</tr>
<tr>
<td>Mean reversion governs reinvestment rates when bonds mature</td>
<td>Mean reversion determines the discount rates used to value funding gaps</td>
</tr>
</table>

> Mean reversion applies to **market-driven variables** (rates, spreads),
> not to **contractual cash flows** (coupons or crediting rates).

---

## Document Summaries

### 1. Mean Reversion.md

Theoretical research document covering:

- Conceptual explanation of mean reversion and why it differs from
  stock price dynamics
- CIR model specification and parameter interpretation
- Half-life formula $t_{1/2} = \ln 2 / \kappa$ and sensitivity table
- Connection to C1, C3, and the optimizer duration constraint

---

### 2. Mean Reversion Simulator.py

Simulation code that runs entirely inline — no external files required.
Produces printed summaries and three plots directly:

| Output | Description |
|--------|-------------|
| Print: Feller condition | Verifies $2\kappa\theta \geq \sigma^2$ |
| Print: Half-life | Theoretical vs empirical comparison |
| Print: κ comparison | Slow / base / fast reversion summary |
| Print: Autocorrelation | 12-month lag analysis |
| Plot 1 | 50 CIR scenarios + mean path + confidence band |
| Plot 2 | Convergence to θ + absolute deviation over time |
| Plot 3 | Impact of κ on mean path and rate dispersion |

**Default parameters:**

| Parameter | Value | Source |
|-----------|-------|--------|
| $\kappa$ | 0.20 | NAIC typical range |
| $\theta$ | 4.5% | Long-run MRP |
| $\sigma$ | 1.5% | Historical calibration |
| $r_0$ | 5.5% | Above θ to show reversion |
| Scenarios | 50 | NAIC C3 convention |
| Horizon | 30 years | FABN typical maturity |
