# C3 Risk-Based Capital Calculation for FABN Optimization
## Mathematical Framework - Cash Flow Testing Methodology

---

## 0.0 Potential Shortcut if you don't want to read or we do not want to optimize this -->which could be the case for a first pass

*C3 can also be calculated as 0.75%.*


## 1. C3 Objectives and Cash Flow Testing Method

### 1.1 C3 RBC Purpose

The C3 component of Risk-Based Capital measures the potential loss from adverse interest rate movements and market risk. For FABNs, C3 quantifies the capital required to absorb losses from interest rate scenarios where:

- Asset coupons cannot service FABN crediting obligations
- Accumulated cash deficits emerge from duration mismatches
- Refinancing risk occurs at liability maturity

### 1.2 Why Cash Flow Testing for FABNs

FABNs are **interest-sensitive liabilities** with:
- Fixed crediting rate (e.g., 3.5%) regardless of market rates
- Deterministic annual cash outflows
- Known maturity date

The cash flow method directly measures **annual liquidity sufficiency** rather than balance sheet markings. This avoids false negatives from unrealized losses on held-to-maturity bonds.

**Key principle:** We test whether annual coupon receipts cover annual crediting payments across 50 stochastic interest rate scenarios.

---

## 2. Cash Flow Matching Equation

### 2.1 Annual Net Cash Flow

For each scenario $s$ and year $t$:

$$\text{NetCash}_t^s = \text{CashIn}_t^s - \text{CashOut}_t^s$$

Where:

$$\text{CashIn}_t^s = C_t + P_t^{maturity} + I_t^{reinvest}$$

$$\text{CashOut}_t^s = R_t^{FABN} + M_t^{FABN} + E_t$$

**Components:**
- $C_t$ = Bond coupon payments (deterministic, in $)
- $P_t^{maturity}$ = Principal from maturing bonds at year $t$ (deterministic, in $)
- $I_t^{reinvest}$ = Interest earned on accumulated cash: $\text{AccumCash}_{t-1}^s \times r_t^s$ (scenario-dependent)
- $R_t^{FABN}$ = FABN crediting obligation: $B_0 \times c_{FABN}$ for years $1 \leq t \leq T_{FABN}$ (deterministic)
- $M_t^{FABN}$ = FABN principal maturity (year $T_{FABN}$ only): $B_0$
- $E_t$ = Operating expenses (deterministic, in $)

### 2.2 Accumulated Cash Position

The cumulative cash position in scenario $s$ at year $t$:

$$\text{AccumCash}_t^s = \text{AccumCash}_{t-1}^s + \text{NetCash}_t^s$$

With initial condition: $\text{AccumCash}_0^s = 0$

### 2.3 Present Value of Accumulated Deficiencies (PVAD)

For each year $t$ in scenario $s$, calculate the present value of any accumulated cash shortfall using path-dependent discount factors:

$$\text{PVAD}_{s,t} = \frac{\max(0, -\text{AccumCash}_t^s)}{\prod_{j=1}^{12t} (1 + r_j^s)}$$

Where:
- The numerator is the deficiency (if accumulated cash is negative)
- The denominator is the cumulative discount factor from month 1 to month $12t$, using scenario $s$'s monthly rates
- All cash flows are assumed to occur at year-end

**Interpretation:** Each year's potential shortfall is discounted back to present value using the scenario's own interest rate path, reflecting timing of the cash need.

---

## 3. Scenario Greatest Present Value (SGPV) and CTE Weighting

### 3.1 Scenario Greatest Present Value

For each scenario $s$, identify the year with the **greatest discounted deficiency**:

$$\text{SGPV}_s = \max_{1 \leq t \leq T} \left(\text{PVAD}_{s,t}\right) = \max_{1 \leq t \leq T} \left(\frac{\max(0, -\text{AccumCash}_t^s)}{\prod_{j=1}^{12t} (1 + r_j^s)}\right)$$

**Interpretation:** $\text{SGPV}_s$ is the worst present-valued cash shortfall in scenario $s$. It tells you: "If this scenario occurs, what is the PV amount of capital I need at time zero to ensure I never run out of cash?"

### 3.2 CTE (92-98) Percentile Weighting

Rank all 50 scenarios by $\text{SGPV}_s$ from **largest to smallest** (worst to best). Apply tail-risk weights emphasizing the worst scenarios:

$$\text{SGPV}^{(1)} \geq \text{SGPV}^{(2)} \geq \cdots \geq \text{SGPV}^{(50)}$$

Where $\text{SGPV}^{(i)}$ denotes the $i$-th largest SGPV value.

The **C3 Pre-Tax** is the weighted average of the tail scenarios:

$$C3_{\text{PreTax}} = 0.10 \cdot \text{SGPV}^{(1)} + 0.10 \cdot \text{SGPV}^{(2)} + 0.10 \cdot \text{SGPV}^{(3)} + 0.40 \cdot \text{SGPV}^{(4)} + 0.10 \cdot \text{SGPV}^{(5)} + 0.10 \cdot \text{SGPV}^{(6)} + 0.10 \cdot \text{SGPV}^{(7)}$$

**Weight allocation:**
- $\text{SGPV}^{(1)}$ = worst outcome (92nd percentile): 10% weight
- $\text{SGPV}^{(4)}$ = median of tail (95th percentile): 40% weight (highest emphasis)
- $\text{SGPV}^{(7)}$ = edge of tail (98th percentile): 10% weight
- All other scenarios: zero weight

**Interpretation:** We focus capital requirements on the worst plausible outcomes, not median scenarios. The 40% weight on the 95th percentile reflects regulatory emphasis on "bad but not catastrophic" outcomes.

### 3.3 After-Tax Conversion

Apply statutory tax rate $\tau = 21\%$:

$$C3_{\text{PostTax}} = C3_{\text{PreTax}} \times (1 - \tau) = C3_{\text{PreTax}} \times 0.79$$

This converts the pre-tax capital requirement to an after-tax equivalent.

---

## 4. Discount Rate Determination for FABNs

### 4.1 Scenario-Specific Monthly Rates

The discount factor $r_t^s$ comes from the CIR scenario generator (see Section 5). For cash flow projection in year $t$, use the **monthly rate from that scenario** in continuous form or discretized annual form.

---

## 5. Setting Scenario Interest Rates

### 5.1 CIR Model Specification

Generate 50 interest rate scenarios using the **Cox-Ingersoll-Ross** short-rate model:

$$dr_t = \kappa(\theta - r_t)dt + \sigma\sqrt{r_t} \, dW_t$$

**Parameters** (calibrated to historical data, updated annually):
- $\kappa$ = speed of mean reversion (typical: 0.15–0.25 per year)
- $\theta$ = long-run mean reversion point or MRP (updated annually by NAIC)
- $\sigma$ = interest rate volatility (typical: 1–3% per year)

### 5.2 Monthly Discretization for Simulation

For practical simulation, discretize with monthly time step $\Delta t = \frac{1}{12}$:

$$r_{t+\Delta t}^s = r_t^s + \kappa(\theta - r_t^s) \Delta t + \sigma\sqrt{r_t^s} \sqrt{\Delta t} \, Z_t^s$$

**Explicit form:**

$$r_{t+\frac{1}{12}}^s = r_t^s + \kappa(\theta - r_t^s) \cdot \frac{1}{12} + \sigma\sqrt{r_t^s} \cdot \sqrt{\frac{1}{12}} \cdot Z_t^s$$

Where:
- $r_t^s$ = 3-month or 1-year Treasury rate in scenario $s$ at month $t$
- $Z_t^s \sim N(0,1)$ = independent standard normal random variable, fresh draw each month and scenario
- $\sqrt{\frac{1}{12}} \approx 0.2887$

**Floor:** If $r_{t+\frac{1}{12}}^s < 0.0001$, set $r_{t+\frac{1}{12}}^s = 0.0001$ to prevent negative rates.

### 5.3 Scenario Generation Procedure

1. **Calibration (annual):** Fit $\kappa$, $\theta$, $\sigma$ to 50 years of historical Treasury rates via OLS regression
2. **Initialization:** Set $r_0^s = $ current 3-month Treasury (same for all 50 scenarios)
3. **Simulation:** For $s = 1$ to $10,000$ scenarios:
   - For $t = 1$ to $360$ months:
     - Draw $Z_t^s \sim N(0,1)$
     - Update: $r_t^s = r_{t-1}^s + \kappa(\theta - r_{t-1}^s)/12 + \sigma\sqrt{r_{t-1}^s} \cdot 0.2887 \cdot Z_t^s$
     - Enforce floor: $r_t^s = \max(r_t^s, 0.0001)$
4. **Stratification:** Rank 10,000 scenarios by final rate; select 50 via percentile stratification (scenarios at 2nd, 4th, 6th, ..., 100th percentile)


---

## Summary: C3 Algorithm for FABN (NAIC Methodology)

```
INPUT: FABN portfolio, current yield curve, historical rate data

STEP 1: Calibrate CIR parameters (κ, θ, σ) from 50 years of history

STEP 2: Generate 10,000 scenarios via monthly CIR discretization
        Select 50 representative scenarios via stratification

STEP 3: FOR each of 50 scenarios s:
          Initialize cumulative discount factor: DF_0 = 1.0
          
          FOR each month m = 1 to 360:
            Get monthly rate: r_m^s from CIR scenario
            Update discount factor: DF_m = DF_{m-1} / (1 + r_m^s)
            
            If m is year-end (m = 12t):
              Calculate year-end accumulated cash: AccumCash_t^s
              Calculate deficiency: PVAD_{s,t} = max(0, -AccumCash_t^s) × DF_m
          END FOR
          
          Find worst year: SGPV_s = max_t(PVAD_{s,t})
        END FOR

STEP 4: Rank all 50 scenarios by SGPV_s from largest to smallest
        Extract top 7 values: SGPV^(1), SGPV^(2), ..., SGPV^(7)

STEP 5: Apply CTE weighting:
        C3_PreTax = 0.10×SGPV^(1) + 0.10×SGPV^(2) + 0.10×SGPV^(3) 
                  + 0.40×SGPV^(4) + 0.10×SGPV^(5) + 0.10×SGPV^(6) + 0.10×SGPV^(7)

STEP 6: C3_PostTax = C3_PreTax × 0.79

OUTPUT: C3 RBC charge in millions
```

---

