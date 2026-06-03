# RBC Capital Cost Reformulation — Session Summary
**Date:** 2026-05-09  
**Files modified:** `FABN_Data_Pipeline.ipynb`, `FABN_Optimizer_Gurobi_Clean_v2_Graphs.ipynb`

---

## Problem: Why Was the RBC Ratio So High?

The original model reported an RBC ratio of ~79x. There were three compounding errors:

### Error 1 — Placeholder `C_min = $1M`
Both `C_curr` ($50M) and `C_min` ($1M) were hardcoded placeholders flagged with
`# CONFIRM WITH ATHENE` but never replaced. The RBC ratio was computed as:

```
RBC_val = (C_curr + Σ spread_i·h_i) / C_min
        = ($50M + ~$29M) / $1M  ≈  79x
```

A $1M denominator for a $500M portfolio is the direct mechanical cause of the inflated ratio.

### Error 2 — Wrong formula (spread income ≠ capital)
The numerator added **spread income** (a flow) to current capital (a stock).
RBC is a point-in-time capital adequacy ratio — it should not include P&L accrual.

### Error 3 — Wrong constraint (spread ≠ solvency)
The solvency constraint forced the optimizer to pick bonds with enough spread income
to satisfy a capital floor. This is not how RBC works. RBC constrains the
**credit risk capital charge** (C1), not earnings.

---

## Correct RBC Framework (NAIC Standard)

The industry-standard RBC ratio for a fixed-income insurance block is:

```
RBC ratio = Total Adjusted Capital (TAC) / Required Capital
          = TAC / (C1 + C3)
```

Where:
- **C1** = credit risk capital = `Σ theta_i · h_i` (NAIC charge factor × dollar allocation)
- **C3** = interest rate risk capital = duration mismatch penalty (currently `alpha_w = 0`)
- **TAC** = regulatory capital the insurer holds against this block

For a FABN optimizer, C1 is **endogenous** — it is determined by which bonds the
optimizer selects. A target RBC ratio `RBC_bar` means the insurer commits to holding
`RBC_bar × C1` in capital against this portfolio.

---

## What Was Changed

### 1. `FABN_Data_Pipeline.ipynb` — Parameters cell

| Parameter | Before | After | Reason |
|-----------|--------|-------|--------|
| `C_curr` | `$50,000,000` | **Removed** | Total company surplus — not meaningful at FABN block level |
| `C_min` | `$1,000,000` | **Removed** | Placeholder; now endogenous (= C1 charge of portfolio) |
| `RBC_bar` | `1.5` | **`2.0`** | Realistic mid-range for an IG fixed-income insurer (range: 1.2–2.5) |

`C_min` is now computed inside the optimizer as `Σ theta_i · h_i` — it moves with
the portfolio allocation. `RBC_bar` controls how much capital the insurer holds
relative to that charge.

---

### 2. `FABN_Optimizer_Gurobi_Clean_v2_Graphs.ipynb`

#### Section 1A — Unpack
Removed `C_curr` and `C_min` from the pipeline unpack (they no longer exist in the pipeline dict).

#### Section 2 — Core Model (most important change)

**Capital cost in the objective:**
```python
# BEFORE
annual_capital_cost = gamma_w * (C1 + C3)
capital_cost        = annual_capital_cost * D_mac

# AFTER
capital_cost = gamma_w * RBC_bar * C1 * D_mac
```

**Economic interpretation:**
```
Required capital      = RBC_bar × C1            (what insurer must hold)
Annual cost           = gamma_w × required capital  (WACC on that capital)
PV cost over FABN life = annual cost × D_mac        (Macaulay duration scaling)
```

**Solvency constraint — removed:**
```python
# BEFORE (wrong)
rbc_rhs = (RBC_bar * C_min - C_curr) / dt
model.addConstr(Σ spread_i·h_i >= rbc_rhs, name="solvency")

# AFTER
# RBC is enforced implicitly by the capital cost term in the objective.
# No separate constraint needed.
```

The constraint was removed because the RBC requirement is now baked into the cost
function. The optimizer already pays `gamma_w × RBC_bar × theta_i × D_mac` per dollar
allocated to bond `i` — equivalent to holding the required capital and paying WACC on it.

#### Section 3 — Results Reporting
```python
required_capital = RBC_bar * (C1_val + C3_val)   # capital insurer must hold ($)
capital_cost_val = gamma_w * required_capital * D_mac
RBC_val          = required_capital / C1_val      # = RBC_bar by construction
```

#### Sensitivity helpers (`_solve_nev`, `_solve_nev_delta`)
Same capital cost fix applied to all parametric sweep functions.
The `>= (RBC_bar·C_min - C_curr)/dt` solvency constraint was removed from all of them.

---

## Economic Effect of the New Formulation

The net contribution of bond `i` to NEV is now:

```
net_i = h_i × (spread_i  −  gamma_w × D_mac × RBC_bar × theta_i)
```

Bond `i` is worth holding only if its spread exceeds its capital breakeven:

```
spread_i  >  gamma_w × D_mac × RBC_bar × theta_i
```

### Breakeven spreads at current parameters
`gamma_w = 0.15`, `D_mac ≈ 2.53 yrs`, `RBC_bar = 2.0`:

| Rating | C1 factor (theta) | Breakeven spread |
|--------|-------------------|-----------------|
| AAA    | 0.00158           | ~12 bps          |
| AA     | 0.00419           | ~32 bps          |
| A      | 0.00816           | ~62 bps          |
| BBB    | 0.01523           | ~116 bps         |
| BBB-   | 0.02168           | ~165 bps         |

The universe spread range is **-1.6 to 153.7 bps, mean 59.4 bps**.  
Result: BBB bonds (mean spread ~50–80 bps) are mostly below their breakeven.
The optimizer will tilt toward AA/A-rated bonds with above-average spreads.

---

## Parameters to Confirm with Athene

| Parameter | Current value | What it represents |
|-----------|--------------|-------------------|
| `RBC_bar` | `2.0` | Target RBC ratio for this FABN block. Adjust per actual regulatory requirement (range 1.2–2.5). |
| `gamma_w` | `0.15` (15%) | WACC on regulatory capital. If capital is funded internally at lower cost, reduce to 0.08–0.10. |
| `alpha_w` | `0.0` | C3 scaling factor. Set to non-zero to activate duration mismatch capital penalty. |

---

## How to Re-run

1. Open `FABN_Data_Pipeline.ipynb` — confirm `RBC_bar` and `gamma_w` then run all cells.
2. Open `FABN_Optimizer_Gurobi_Clean_v2_Graphs.ipynb` — run cells top to bottom:
   `Date Selection → Section 0 → 1A → (1B) → (1C) → 2 → 3 → 4`
3. The RBC ratio in the results output will now report cleanly as `2.0x` (= `RBC_bar`).
4. To sensitivity-test the RBC target, change `RBC_bar` in the pipeline params cell and re-run.
