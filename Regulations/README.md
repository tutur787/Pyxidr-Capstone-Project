# C1 Risk-Based Capital Framework for FABN

This document provides the mathematical framework for calculating the **C1 Risk-Based Capital (RBC)** component applied to the bond portfolio backing **Fixed Annuities with Book Value (FABN)** liabilities, following the **NAIC Life RBC methodology**.

---

## What is C1?

C1 is the **credit risk capital charge** — the capital buffer a life insurer must hold in case the bonds backing its FABN liabilities fail to pay. It is one of four major risk components in the NAIC Life RBC formula:

| Component | Risk |
|-----------|------|
| **C1** | Asset / credit risk ← this document |
| C2 | Insurance / underwriting risk |
| C3 | Interest rate / ALM risk |
| C4 | Business / operational risk |

---

## Contents of This Framework

| Section | Description |
|---------|-------------|
| 1. Objectives | Purpose of C1 and why the factor method is used |
| 2. Capital Equation | Bond-level and portfolio-level formulas |
| 3. Factor Table | 20 NAIC rating categories with pre-tax factors |
| 4. PAF | Portfolio Adjustment Factor by number of issuers |
| 5. Concentration Charge | Top-10 holding penalty and cap rules |
| 6. RBC Covariance Formula | How C1 integrates into total RBC |
| 7. Modelling Assumptions | Time horizon, confidence level, data sources |
| 8. Algorithm | Step-by-step calculation procedure |

---

## Core Formula

$$C1_b = \text{BACV}_b \times f_r \times \text{PAF}(n)$$

$$C1o_{\text{PostTax}} = \left( \sum_b C1_b + \text{ConcentrationCharge} \right) \times 0.79$$

Where:
- **BACV** = Book/Adjusted Carrying Value of the bond
- **f_r** = Pre-tax risk factor based on NAIC rating designation
- **PAF(n)** = Portfolio diversification adjustment by number of issuers

---

## Key Design Decisions

**No maturity adjustment** — unlike Canada's LICAT, the NAIC C1 factor does not vary by bond maturity. Duration and interest rate risk are captured separately in the C3 component.

**20 rating categories** — expanded from 6 to 20 in 2021 to better differentiate credit risk across the rating spectrum.

**Portfolio Adjustment Factor** — penalizes concentrated portfolios (few issuers) and rewards diversified ones. A portfolio with 5 issuers gets a 5.87× multiplier vs. 0.82× for 500+ issuers.

**Concentration charge** — the top-10 largest non-NAIC-1 exposures have their factor doubled, capped at 45% pre-tax.

---

## Relationship to C3

This document covers the **asset side** of the FABN structure. The companion document `C3_FABN_Mathematical_Framework.md` covers the **liability side.**

Together, C1 and C3 determine the dominant RBC requirements for a FABN optimization problem.

## File Location

---

## Primary Sources

- Moody's Analytics (2021) — *Revisions to the RBC C1 Bond Factors*
- American Academy of Actuaries, C1 Work Group (2015) — *Model Construction and Development of RBC Factors for Fixed Income Securities*
- NAIC CIPR / Obersteadt (2017) — *RBC Requirements on Fixed Income Assets to Change*
- NAIC (2025) — *Life and Fraternal RBC Newsletter, Volume 31*
