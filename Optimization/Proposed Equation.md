# Application of RBC to Portfolio Optimization

The Risk-Based Capital (RBC) framework provides a natural way to incorporate regulatory
capital considerations into portfolio optimization. While RBC is implemented through complex
formulas involving multiple risk components, we construct a tractable approximation tailored
to a bond portfolio setting.

In particular, we focus on two key components:

- **C1 (Asset Risk):** modeled using bond-level capital factors
- **C3 (Interest Rate / ALM Risk):** approximated through duration mismatch

Other components, such as insurance risk (C2) and business risk (C4), are treated as
exogenous, as they are primarily driven by liability-side assumptions and firm-level
characteristics rather than asset allocation decisions.

---

## Optimization Problem

### Objective Function

$$\max_{w} \sum_i w_i \left( GSpread_i - \beta \cdot Vol_i - \gamma \cdot BA_i \right)$$

Where:

- $GSpread_i$: credit spread of bond $i$, representing excess return over Treasuries
- $Vol_i$: volatility of bond $i$, penalizing risk
- $BA_i$: bid-ask spread, capturing liquidity costs
- $\beta, \gamma$: tuning parameters controlling the trade-off between return, risk,
  and liquidity

## Subject to

### Budget Constraint

$$\sum_i w_i = 1$$

Ensures that the full capital is allocated across all bonds. The portfolio weights sum to one.

### Long-Only Constraint

$$w_i \geq 0 \quad \forall i$$

Prevents short positions. This is consistent with typical insurance portfolio constraints.

### RBC Capital Constraint (C1)

$$\sum_i w_i \cdot f_i^{(C1)} \leq B$$

This constraint captures regulatory capital requirements associated with asset risk:

- $f_i^{(C1)}$: RBC capital factor for bond $i$, typically based on credit quality
  (rating or NAIC designation)
- $B$: maximum allowable capital budget

This reflects the fact that riskier bonds consume more regulatory capital. The optimizer
must balance higher spreads against higher capital requirements.

### Interest Rate Risk Constraint (C3)

$$\left| D_A(w) - D_L \right| \leq \epsilon$$

Where:

$$D_A(w) = \sum_i w_i D_i$$

This constraint approximates interest rate and asset-liability management (ALM) risk:

- $D_A(w)$: duration of the asset portfolio
- $D_L$: duration of liabilities
- $\epsilon$: acceptable mismatch tolerance

It ensures that the portfolio is not overly exposed to interest rate movements by limiting
duration mismatch.

### Rating Constraint

$$\sum_{i \in BBB} w_i \leq q$$

Limits exposure to lower credit quality bonds. This reflects both regulatory and internal
risk management guidelines.

### Sector Concentration Constraint

$$\sum_{i \in s} w_i \leq u_s$$

Prevents excessive concentration in a single sector. This improves diversification and
reduces idiosyncratic risk.

---

## Interpretation

This framework captures the trade-off between:

- **Return:** driven by credit spreads  
- **Risk:** captured via volatility  
- **Liquidity:** via bid-ask spreads  
- **Regulatory capital:** via RBC constraints  

The optimization balances higher spreads against higher capital consumption and risk exposure.

---

# Impact

This approach enables insurance companies to:

- Identify risk exposures through dynamic allocation  
- Improve capital efficiency under RBC constraints  
- Enhance return attribution and decision-making  

---

# Note on Potential Extension (Return Decomposition)

An alternative extension of this framework would involve explicitly decomposing bond returns into systematic and idiosyncratic components:

$$
GSpread_i = \beta^{mkt}_i M_t + \beta^{sec}_i S_t + \beta^{dur}_i D_t + \beta^{qual}_i Q_t + \alpha_i
$$

Where:

- $M_t$: market-wide credit factor  
- $S_t$: sector factor  
- $D_t$: duration / interest rate factor  
- $Q_t$: credit quality (rating) factor  
- $\alpha_i$: issuer-specific return (idiosyncratic alpha)  

Under this formulation, the portfolio optimization problem would be reformulated by replacing raw credit spreads with their idiosyncratic component.

## Modified Objective Function

$$
\max_{w} \sum_i w_i \left( \alpha_i - \beta \cdot Vol_i - \gamma \cdot BA_i \right)
$$

This modification ensures that portfolio allocation is driven by true security selection (alpha) rather than unintended exposures to systematic risk factors.

All constraints (e.g., RBC capital, duration matching, rating, and sector limits) would remain unchanged, as they continue to reflect regulatory and portfolio construction requirements.

This extension would allow for:

- Improved identification and control of unintended systematic exposures  
- More accurate performance attribution  
- Portfolio construction driven by true alpha rather than broad factor movements  

However, implementing this approach requires additional modeling assumptions, including the specification and estimation of factor sensitivities ($\beta$) 
and the extraction of $\alpha_i$. Therefore, this extension is left for future development depending on project scope and data availability.
