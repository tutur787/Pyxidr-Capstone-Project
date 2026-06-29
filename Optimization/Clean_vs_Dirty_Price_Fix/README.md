# Clean → Dirty Price Fix (isolated working copy)

This folder is a **self-contained copy** of the FABN optimizer with **one** change applied:
the bond-yield IRR solve now uses the **dirty** price (`clean + accrued interest`) instead of the
**clean** quoted mid price. The original `Optimization/` folder is **untouched** — compare the two.

## Why
Yield-to-maturity is defined by `Σ_t CF_t (1+y)^(-t) = P_dirty = P_clean + accrued`. Quoted mid
prices are **clean**. Solving against the clean price uses a target that is too small by the accrued
interest, so every solved yield was biased **UPWARD (overstated)**. Two consequences:
1. **Reported book yields / NII overstated** (the headline numbers look better than reality).
2. **Backtest sawtooth** — for a fixed bond, the clean-price yield `Y[d,i]` drifts up through each
   coupon period and snaps down at the coupon, an artificial oscillation that can fire **phantom
   swaps** and inflate turnover. The dirty price removes it.

## What changed (vs `../`)
| File | Change |
|---|---|
| `fabn_finance.py` | **New** `accrued_interest(...)` and `previous_coupon_date(...)` (vectorized, unit-tested). |
| `FABN_Data_Pipeline.ipynb` | §9.5 builds `dirty = price + accrued` and solves `ff.book_yields(bond_cf, t_vec, dirty)`. Clean `price` stays the carry value + bid-ask base. Propagates to `FABN_Optimizer_SAP.ipynb` automatically. |
| `FABN_Optimizer_SAP_Backtest.ipynb` | Section 1 adds `CPN_FREQ` to the SQL and accrued interest per `(day, bond)`, so `Y[d,i]` is a true YTM (kills the sawtooth). |
| `FABN_Price_Yield_Validation.ipynb` | Measures the real per-bond bias + dollar NII overstatement, and a **convention check** that confirms the pipeline now matches the dirty-price solve. |
| `tests/test_fabn_finance.py` | +3 tests: accrued actual/actual + bounds, `previous_coupon_date`, and clean-yield > dirty-yield. |

What did **not** change: clean price as carrying/book value, bid-ask `tau`, duration, C-1, the LP
objective/constraints, IMR.

## Run order
1. `pytest tests/ -q`  — pure-math check (no creds needed). *Verified: 25 passed.*
2. `FABN_Price_Yield_Validation.ipynb` — **Measure.** Real bias distribution, $ NII overstatement,
   and the convention check (should print `DIRTY (fix is live)`). Needs BigQuery/GCP ADC.
3. `FABN_Optimizer_SAP_Backtest.ipynb` — **Re-run.** End-to-end; compare cumulative net, weighted
   book yield, and **turnover** against the original folder. Needs BigQuery + Gurobi (WLS).
4. (Optional) `FABN_Optimizer_SAP.ipynb` — single-period; inherits the fix via the pipeline.

## Honesty note
The pure-math (`pytest`) and the accrued-interest logic were verified locally. The BigQuery/Gurobi
notebooks (steps 2–4) could **not** be executed in the assistant's environment (no GCP creds / Gurobi
license) — run them on your machine. Patched cells were compile-checked and the accrued logic was
simulated on synthetic schedules (correct sawtooth in `[0, period-coupon]`, zero after the last
coupon).

## Expectation for the thesis
The +10–13% dynamic-vs-static result is a **difference** of two strategies that share the same level
bias, so it should survive. The level of reported NII drops (overstatement removed — the prudent
direction); watch whether **turnover** falls once the sawtooth is gone. If the thesis holds, it is
now defensible to a fixed-income reviewer; if it shifts materially, you caught a wrong answer before
shipping.
