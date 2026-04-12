# C1 Risk-Based Capital Framework for FABN

This document provides the mathematical framework for calculating the **C1 Risk-Based Capital (RBC)** component applied to the bond portfolio backing **Funding Agreement-Backed Notes (FABN)** liabilities, following the **NAIC Life RBC methodology**.

---

## What is C1?

C1 is the **credit risk capital charge** — the capital buffer a life insurer must hold in case the bonds backing its FABN liabilities fail to pay. It is one of four major risk components in the NAIC Life RBC formula:

| Component | Risk |
|-----------|------|
| **C1** | **Asset / credit risk ← this document** |
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

## Relationship to C3

This document covers the **asset side** of the FABN structure. The companion document `C3_FABN_Mathematical_Framework.md` covers the **liability side.**

Together, C1 and C3 determine the dominant RBC requirements for a FABN optimization problem.
