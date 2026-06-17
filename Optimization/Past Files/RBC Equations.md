# RBC Components (C1–C4)

The life insurance company RBC formula provides four categories of risk:

- **Asset risk (C-1)** — Risk of default of the company's investments or other
  non-performance of the assets.
- **Insurance risk (C-2)** — Risk that the company's mortality/morbidity/lapse
  assumptions prove incorrect.
- **Interest rate and market risk (C-3)** — Risk that asset values and policy cash flows
  change due to market movements.
- **Business risk (C-4)** — Risk of operational loss.

In addition, the RBC formula includes a provision for default of an affiliated company and
off-balance sheet items such as derivative instruments (C-0). The interest rate and market
risk (C-3) category calls for a model-based approach for products with long-dated interest
rate guarantees such as variable annuities, certain fixed annuities, and single premium life
insurance policies. The calculation includes correlation adjustments (covariance) and
adjustments for federal taxes.

> **Important Note:** The theoretical VaR-style equations below are conceptual
> representations, not the literal NAIC implementation formulas. NAIC explicitly defines
> the risk categories and the practical RBC formula, while the VaR framing is supported
> by broader solvency/risk-management literature.

## C1 — Asset Risk

### Theoretical Representation

$$C1 \approx VaR_q(\text{credit / asset losses}) - \text{risk premium}$$

This equation captures the idea that asset risk reflects severe losses from invested assets,
especially credit/default losses, net of compensation already earned through spread. NAIC's
bond factor work shows that C1 capital charges are derived from a simulation model for
representative bond portfolios, with losses projected over a ten-year horizon, which supports
this theoretical interpretation.

### Practical Representation

$$C1 \approx \sum_i Exposure_i \cdot f_i^{(C1)}$$

In practice, RBC is implemented through factor-based capital charges. NAIC materials state
that RBC required capital is calculated by multiplying the book/adjusted carrying value
(BACV) by an RBC risk factor.

## C2 — Insurance Risk

### Theoretical Representation

$$C2 \approx VaR_q(\text{insurance losses})$$

Conceptually, C2 reflects severe adverse deviations in mortality, morbidity, lapse, or other
insurance assumptions. NAIC identifies insurance risk as one of the four major categories in
the life RBC formula, while the VaR framing is consistent with insurance capital literature
that treats solvency capital as a tail-loss measure.

### Practical Representation

$$C2 \approx \sum_k Exposure_k \cdot f_k^{(C2)}$$

In practice, C2 is implemented through prescribed formulas/factors applied to liability-side
exposures by product category, rather than by running a fresh VaR simulation each time.
This is consistent with the general RBC architecture, where required capital is generated
through exposure-based factors.

## C3 — Interest Rate / Market / ALM Risk

### Theoretical Representation

$$C3 \approx VaR_q(\Delta A - \Delta L)$$

This expresses C3 as a tail-risk measure on changes in net asset value, driven by market
movements and asset-liability mismatch. NAIC identifies interest rate risk as one of the major
life RBC categories, and VaR-based solvency frameworks support this interpretation.

### Practical Representation

$$C3 \approx \lambda \left| D_A - D_L \right|$$

This is not the literal NAIC C3 formula, but it is a reasonable implementation proxy for an
optimization problem involving bonds and ALM. It captures the core economic idea that
greater duration mismatch implies greater interest-rate / ALM risk. The NAIC life RBC
framework explicitly includes C3 subcomponents in the total RBC aggregation.

## C4 — Business Risk

### Theoretical Representation

$$C4 \approx VaR_q(\text{business / operational losses})$$

Conceptually, C4 represents tail losses arising from operational, strategic, and other
business-related risks not captured in C1–C3. NAIC defines the fourth life RBC category as
all other business risk, while the VaR interpretation comes from broader
solvency/risk-management practice.

### Practical Representation

$$C4 \approx \alpha \cdot \text{Premiums} + \beta \cdot \text{Reserves}$$

This is often the most practical treatment in an asset-allocation project, since C4 is
generally not naturally modeled bond-by-bond. NAIC's life RBC aggregation explicitly
includes C4a and C4b as business-risk components.

---

## References

1. **Bender, J. / Society of Actuaries, Financial Reporting Section (2024).**
   *Regulatory Capital Adequacy for Life Insurance Companies.*
   Financial Reporting Newsletter, May 2024.
   https://www.soa.org/sections/financial-reporting/financial-reporting-newsletter/2024/may/fr-2024-05-bender/

2. **American Academy of Actuaries, C1 Work Group (2015).**
   *Model Construction and Development of RBC Factors for Fixed Income Securities
   for the NAIC's Life Risk-Based Capital Formula.*
   August 3, 2015.
   https://content.naic.org/sites/default/files/inline-files/committees_e_capad_investment_rbc_wg_exposure_academy_bond_factors_report.pdf

3. **Obersteadt, A. / NAIC Center for Insurance Policy and Research (2017).**
   *Risk-Based Capital Requirements on Fixed Income Assets to Change.*
   CIPR Newsletter, November 2017.
   https://content.naic.org/sites/default/files/inline-files/topic_risk_based_capital_rbc_requirements_on_fixed_income_assets_to_change.pdf

4. **CAS RBC Dependencies and Calibration Working Party (2012).**
   *Solvency II Standard Formula and NAIC Risk-Based Capital (RBC).*
   Report 3 of the CAS Risk-Based Capital Research Working Parties.
   Casualty Actuarial Society E-Forum, Fall 2012, Volume 2.
   https://www.casact.org/sites/default/files/database/forum_12fforumpt2_rbc-dcwprpt3.pdf

5. **Johnson, J.L. / American Academy of Actuaries, Life Capital Adequacy Committee (2015).**
   *99.5 Percent Value at Risk Measure over a One-Year Time Horizon.*
   Presentation to the NAIC ComFrame Development and Analysis (G) Working Group,
   August 15, 2015.
   https://www.actuary.org/wp-content/uploads/2017/11/Solvency_NAIC_CDAWG_Presentation_99.5_VaR_081515.pdf

6. **Navratil, P. / American Academy of Actuaries,
   Life Investment and Capital Adequacy Committee (2024).**
   *Correlation in Capital Frameworks: Comparison of Correlation in Other
   Regulatory Capital Frameworks.*
   Presentation to the NAIC Life Risk-Based Capital (E) Working Group, 2024.
   https://content.naic.org/sites/default/files/call_materials/Life-Presentation-CorrelationLRBC.pdf
