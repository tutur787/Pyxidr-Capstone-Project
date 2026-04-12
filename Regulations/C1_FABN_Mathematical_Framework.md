# C1 Risk-Based Capital Calculation for FABN

## Mathematical Framework - Credit Risk Methodology (NAIC Life RBC)

---

## 1. C1 Objectives and Risk Factor Method

### 1.1 C1 RBC Purpose

The C1 component of Risk-Based Capital measures the potential loss from credit risk on fixed
income assets. In the FABN context, C1 quantifies the capital required on the bond portfolio
held as backing assets for the funding agreement obligations, absorbing losses arising from:

- Issuer default on principal and/or interest payments
- Deferral risk: suspension of coupons without triggering a formal default
- Subordination risk: lower priority of claims in a liquidation scenario
- Event risk: dramatic and unexpected impacts on the issuer's ability to pay

### 1.2 Why the Factor Method for Bonds

Bonds are **valued at amortized cost** under statutory accounting, which means:

- Market value fluctuations do not directly impact statutory surplus
- The relevant risk is **actual default**, not fair value depreciation
- Factors are derived from historical default rates by rating category
- The framework is **auditable** from publicly available financial statements

**Key principle:** We apply a pre-tax risk factor to the Book/Adjusted Carrying Value (BACV)
of each bond, adjusted by portfolio diversification (PAF).

---

## 2. C1 Capital Requirement Equation

### 2.1 Requirement per Individual Bond

For each bond *b* with rating *r* and carrying value BACV_b:

$$C1_b = \text{BACV}_b \times f_r \times \text{PAF}(n)$$

Where:

- $\text{BACV}_b$ = Book/Adjusted Carrying Value of bond *b* (in $)
- $f_r$ = Pre-tax base factor by rating category (table in section 3)
- $\text{PAF}(n)$ = Portfolio Adjustment Factor by number of issuers *n* (table in section 4)

### 2.2 Total C1o Portfolio Requirement

$$C1o = \sum_{b=1}^{N} C1_b + \text{ConcentrationCharge}$$

Where the concentration charge applies to the 10 largest single-issuer exposures
(section 5).

### 2.3 Pre-Tax to After-Tax Conversion

Applying the statutory tax rate $\tau = 21\%$:

$$C1o_{\text{PostTax}} = C1o_{\text{PreTax}} \times (1 - \tau) = C1o_{\text{PreTax}} \times 0.79$$

---

## 3. C1 Base Factors by Rating (Effective Year-End 2021)

Pre-tax factors adopted by the NAIC in June 2021, applied to BACV regardless of bond
maturity.

| S&P / Fitch Rating | Moody's Rating | NAIC Designation | Base Factor (Pre-Tax) | Grade |
|--------------------|----------------|------------------|-----------------------|-------|
| AAA                | Aaa            | 1.A              | 0.158%                | IG    |
| AA+                | Aa1            | 1.B              | 0.271%                | IG    |
| AA                 | Aa2            | 1.C              | 0.419%                | IG    |
| AA−                | Aa3            | 1.D              | 0.523%                | IG    |
| A+                 | A1             | 1.E              | 0.657%                | IG    |
| A                  | A2             | 1.F              | 0.816%                | IG    |
| A−                 | A3             | 1.G              | 1.016%                | IG    |
| BBB+               | Baa1           | 2.A              | 1.261%                | IG    |
| BBB                | Baa2           | 2.B              | 1.523%                | IG    |
| BBB−               | Baa3           | 2.C              | 2.168%                | IG    |
| BB+                | Ba1            | 3.A              | 3.151%                | HY    |
| BB                 | Ba2            | 3.B              | 4.537%                | HY    |
| BB−                | Ba3            | 3.C              | 6.017%                | HY    |
| B+                 | B1             | 4.A              | 7.386%                | HY    |
| B                  | B2             | 4.B              | 9.535%                | HY    |
| B−                 | B3             | 4.C              | 12.428%               | HY    |
| CCC+               | Caa1           | 5.A              | 16.942%               | D     |
| CCC                | Caa2           | 5.B              | 23.798%               | D     |
| CCC−               | Caa3           | 5.C              | 32.975%               | D     |
| Below CCC−         | Ca / C         | 6                | 30.000%               | D     |

> **Note:** The CCC− factor (32.975%) exceeds the 30% floor applied to Category 6.
> IG = Investment Grade · HY = High Yield · D = Distressed / In or Near Default

---

## 4. Portfolio Adjustment Factor (PAF)

### 4.1 Adjustment Formula

The base factor is multiplied by a PAF that scales with the number of distinct issuers in the
portfolio. More diversified portfolios receive a lower multiplier:

$$f_r^{\text{adjusted}} = f_r \times \text{PAF}(n)$$

Where $n$ = number of distinct issuers in the bond portfolio.

### 4.2 PAF Table (Adopted 2021)

| Number of Issuers (*n*) | PAF (MA / Adopted Formula) | PAF (Prior Formula) |
|-------------------------|---------------------------|---------------------|
| Up to 10                | 5.87×                     | 2.50×               |
| Next 90 (11–100)        | 1.53×                     | 1.83×               |
| Next 100 (101–200)      | 0.85×                     | 1.00×               |
| Next 300 (201–500)      | 0.85×                     | 0.86×               |
| Above 500               | 0.82×                     | 0.90×               |

**Interpretation:** A highly concentrated portfolio (few issuers) carries a much higher
effective factor than a broadly diversified one. The PAF reflects the empirical benefit of
issuer diversification.

---

## 5. Asset Concentration Charge (Top 10 Holdings)

For the 10 largest single-issuer exposures, the C1 factor is doubled:

$$\text{ConcentrationCharge}_b = f_r \times \text{BACV}_b \times 2$$

Capped at a maximum of 45% pre-tax on the exposure's BACV.

**Exclusions:** The doubling does not apply to NAIC 1 bonds, government bonds, or assets
with a factor below 0.8% post-tax.

---

## 6. Total RBC Formula After Covariance

C1o is integrated into the global RBC formula through covariance aggregation:

$$\text{RBC} = C_0 + C_{4a} + \sqrt{(C_{1o} + C_{3a})^2 + (C_{1cs} + C_{3c})^2 + C_2^2 + C_{3b}^2 + C_{4b}^2}$$

Where:

- $C_0$ = asset risk – affiliates
- $C_{1o}$ = credit risk – fixed income (bonds, mortgages) ← **component of this section**
- $C_{1cs}$ = equity risk – common stock
- $C_2$ = insurance / underwriting risk
- $C_{3a}$ = interest rate risk
- $C_{3b}$ = credit risk – health
- $C_{3c}$ = market risk – variable annuities
- $C_{4a}$, $C_{4b}$ = business / operational risk

> **Note on maturities:** C1 does **not** incorporate a maturity adjustment for bonds.
> Duration and interest rate risk are captured entirely in the $C_{3a}$ component.

---

## 7. Key Modelling Assumptions

| Parameter | Value |
|-----------|-------|
| Model time horizon | 10 years |
| Statistical confidence level | ~92nd–95th percentile |
| Assumed tax rate | 21% (updated 2021) |
| Maturity adjustment | None — no maturity dimension |
| Default data source | Moody's historical corporate default rates |
| Correlation model | Empirical default correlations (Moody's Analytics 2021) |

### Risks Captured vs. Excluded

| Risk | In C1? | Note |
|------|--------|------|
| Credit / default risk | Yes | Core of the component |
| Deferral risk | Yes | Implicit via rating |
| Maturity / duration risk | No | Captured in C3a |
| Currency risk | No | Captured in C3 |
| Liquidity risk | No | Not modelable in RBC |
| Fair value depreciation | No | Statutory amortized cost basis |

---

## 8. Summary: C1 Algorithm for FABN (NAIC Methodology)

````
INPUT: Bond portfolio, NRSRO ratings, BACV per issuer

STEP 1: For each bond b:
        Identify rating → assign NAIC Designation (1.A to 6)
        Obtain base factor f_r from the table (section 3)

STEP 2: Calculate number of distinct issuers n in the portfolio
        Obtain PAF(n) from the table (section 4)

STEP 3: For each bond b:
        C1_b = BACV_b × f_r × PAF(n)

STEP 4: Identify the 10 largest single-issuer exposures
        For each: ConcentrationCharge = BACV_b × f_r × 2
        (capped at 45% pre-tax; exclude NAIC 1 and factors < 0.8% post-tax)

STEP 5: C1o_PreTax = Σ C1_b + Σ ConcentrationCharge_b

STEP 6: C1o_PostTax = C1o_PreTax × 0.79

OUTPUT: C1o charge in millions of dollars
````

---

## Key Mathematical References

| Element | Equation | Purpose |
|---------|----------|---------|
| Capital per bond | $C1_b = \text{BACV}_b \times f_r \times \text{PAF}(n)$ | Individual charge |
| Total portfolio capital | $C1o = \sum_b C1_b + \text{ConcentrationCharge}$ | Aggregated charge |
| Top-10 concentration | $\text{CC}_b = \text{BACV}_b \times f_r \times 2$ | Concentration penalty |
| After-tax conversion | $C1o_{\text{PostTax}} = C1o_{\text{PreTax}} \times 0.79$ | Regulatory basis |
| Global RBC integration | $\text{RBC} = C_0 + C_{4a} + \sqrt{(C_{1o}+C_{3a})^2 + \ldots}$ | Covariance formula |

---

## References

1. **Moody's Analytics (2021).** *Revisions to the RBC C1 Bond Factors.* Prepared for ACLI
   and NAIC. April 2021.
   https://content.naic.org/sites/default/files/inline-files/2021%20Revisions%20to%20the%20RBC%20C1%20Bond%20Factors.pdf

2. **American Academy of Actuaries, C1 Work Group (2015).** *Model Construction and
   Development of RBC Factors for Fixed Income Securities for the NAIC's Life Risk-Based
   Capital Formula.* August 3, 2015.
   https://content.naic.org/sites/default/files/inline-files/committees_e_capad_investment_rbc_wg_exposure_academy_bond_factors_report.pdf

3. **NAIC (2025).** *Life and Fraternal Risk-Based Capital Newsletter, Volume 31.*
   September 2025.
   https://content.naic.org/sites/default/files/inline-files/2025_RBC%20Newsletter_Life%20and%20Fraternal.pdf

4. **Indiana Department of Insurance (2024).** *NAIC Life RBC Instructions 2024.*
   Publicly available copy:
   https://www.in.gov/idoi/files/RBCL24-INpdf.pdf

5. **New England Asset Management / NEAM (2021).** *Latest NAIC RBC C1 for Life Insurers:
   Time to Reposition Your Portfolio?* October 2021.
   https://www.neamgroup.com/hubfs/pdfs/2021/quick%20takes%20-%20latest%20naic%20rbc%20c1%20for%20life%20insurers%20-%20oct%2021.pdf

6. **Obersteadt, A. / NAIC Center for Insurance Policy and Research (2017).**
   *Risk-Based Capital Requirements on Fixed Income Assets to Change.*
   CIPR Newsletter, November 2017.
   https://content.naic.org/sites/default/files/inline-files/topic_risk_based_capital_rbc_requirements_on_fixed_income_assets_to_change.pdf
