# RBC-Constrained Portfolio Optimization for FABN

This folder contains the regulatory and optimization framework documents
supporting the **Funding Agreement-Backed Notes (FABN) portfolio optimization
project**, following the **NAIC Life Risk-Based Capital (RBC)** methodology.

---

## Document Summaries

### 1. RBC Equations.md

Overview of the four NAIC Life RBC risk components with both theoretical
(VaR-based) and practical representations:

| Component | Risk | Theoretical | Practical |
|-----------|------|-------------|-----------|
| **C1** | Asset / credit | $VaR_q(\text{credit losses}) - \text{risk premium}$ | $\sum_i Exposure_i \cdot f_i^{(C1)}$ |
| **C2** | Insurance | $VaR_q(\text{insurance losses})$ | $\sum_k Exposure_k \cdot f_k^{(C2)}$ |
| **C3** | Interest rate / ALM | $VaR_q(\Delta A - \Delta L)$ | $\lambda \|D_A - D_L\|$ |
| **C4** | Business / operational | $VaR_q(\text{business losses})$ | $\alpha \cdot \text{Premiums} + \beta \cdot \text{Reserves}$ |

> **Note:** The VaR-style equations are conceptual representations supported
> by broader solvency literature, not the literal NAIC implementation formulas.

In the FABN optimization context, **C1 and C3 are modeled explicitly**
as endogenous constraints. C2 and C4 are treated as exogenous, since they
are driven by liability-side assumptions rather than asset allocation decisions.

---

### 2. Proposed Equation.md

Mathematical formulation of the bond portfolio optimization problem under
RBC constraints for FABN backing assets.

**Objective — maximize risk-adjusted spread:**

$$\max_{w} \sum_i w_i \left( GSpread_i - \beta \cdot Vol_i - \gamma \cdot BA_i \right)$$

**Constraints:**

| Constraint | Formula | Purpose |
|------------|---------|---------|
| Budget | $\sum_i w_i = 1$ | Fully invested |
| Long-only | $w_i \geq 0 \; \forall i$ | No short positions |
| RBC / C1 | $\sum_i w_i \cdot f_i^{(C1)} \leq B$ | Capital budget |
| ALM / C3 | $\|D_A(w) - D_L\| \leq \epsilon$ | Duration match |
| Rating | $\sum_{i \in BBB} w_i \leq q$ | Credit quality floor |
| Sector | $\sum_{i \in s} w_i \leq u_s$ | Diversification |

Also includes an optional **alpha decomposition extension** for future
development, replacing raw spreads with idiosyncratic return components:

$$GSpread_i = \beta^{mkt}_i M_t + \beta^{sec}_i S_t + \beta^{dur}_i D_t + \beta^{qual}_i Q_t + \alpha_i$$

---

### 3. Optimization Simulator.xlsm

Interactive implementation of the optimization problem. Fill in your
portfolio parameters to compute optimal bond weights and verify
constraint compliance.

**Workbook Structure**

| Sheet | Purpose |
|-------|---------|
| **Instructions** | Step-by-step guide for setting up and running Solver |
| **Parameters** | Edit tuning parameters (β, γ, B, D_L, ε, sector caps) |
| **Bonds** | Bond universe — add, remove, or edit bonds here |
| **Optimizer** | Solver target sheet — weights, objective, constraints, dashboard |
