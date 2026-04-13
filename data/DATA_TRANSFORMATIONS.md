# Bond Data Transformations — Pipeline Reference

Covers `bloomberg_first_batch_cleaning.ipynb` (**Batch 1**, ~237 bonds) and `bond_analysis.ipynb` (**Batch 2**, ~173 bonds).  
Both pipelines produce `Mid_Clean`, `Bid_Clean`, `Ask_Clean`, `Credit_Spread_bps`, `Credit_Spread_Dirty`, and `Treasury_Curve` sheets.

---

## 1. Input Structure

| | Batch 1 | Batch 2 |
|---|---|---|
| Source file | `Bloomberg_first_batch.xlsx` | `Bloomberg_second_batch.xlsx` |
| Price sheet name | `PRICE` | `Mid_official` |
| Bid sheet name | `BID` | `Bid_official` |
| Ask sheet name | `ASK` | `Ask_official` |
| Metadata sheet | `Bonds_V2` (2,701 CUSIPs, superset) | `Reduced_List` (batch-specific) |
| Date column | DatetimeIndex (row labels) | Explicit `Date` column |
| Raw bond count | 237 | 173 |

---

## 2. Step-by-Step Transformations

### Step 1 — Duplicate column deduplication
**Batch 1 only.**  
When Excel has two columns with the same header, pandas auto-renames the second to `NAME.1`. The pipeline detects these suffix pairs, verifies the values are identical, and drops the duplicate. Non-identical pairs are kept and flagged.

> **Batch 2:** No duplicate columns in the raw file — this step is skipped.

---

### Step 2 — Phantom row removal & tail trim
**Both batches.**  
Bloomberg exports include trailing empty rows beyond the last trading day.

- `dropna(how='all')` removes rows where every bond is NaN (catches weekends and empty rows at the tail).
- **Batch 1 additional trim:** A second pass drops any date where fewer than 10% of bonds have prices. This handles partial delivery days (e.g., Bloomberg delivered 2026-02-27 with only 5 of 237 bonds quoted — an artefact of the data pull, not a real trading day).

> **Batch 2:** The raw file's date range is clean — only the `dropna` pass is needed.

**Result:** Batch 1 index trimmed from 503 → 499 rows (ends 2026-02-26). Batch 2 ends 2026-03-05.

---

### Step 3 — Duplicate bond pairs (same underlying security)
**Both batches, different detection methods.**

Bloomberg sometimes assigns two CUSIPs to the same bond: one real 9-character numeric CUSIP and one internal Bloomberg ID (prefixed `Z` or `B`).

**Batch 1:** Detected programmatically — group bonds by `(Issuer, Ticker, Coupon, Maturity)`. Any group with 2+ CUSIPs keeps the real numeric CUSIP and drops the Bloomberg-internal one.

**Batch 2:** A hardcoded list of 26 known duplicate pairs (`CUSIPS_TO_DROP`) is dropped directly.

> **⚠ Exception — Batch 1:** If a duplicate pair has genuinely different price series (max diff > 0.01), both are kept and flagged rather than dropped silently.

---

### Step 4 — Zero → NaN conversion
**Both batches.**  
Bloomberg uses `0` as a placeholder for missing prices (not a real price). All zeros are converted to `NaN`. Negative prices are flagged separately and not auto-corrected.

---

### Step 5 — Date alignment for late-issued bonds
**Both batches, same logic.**

**Problem:** For bonds issued after the sample start date (2024-03-01), Bloomberg left-aligns the price data to row 1 of the export regardless of issue date. A bond issued 2025-01-14 will have its first price sitting at row labeled 2024-03-01, shifted 219 rows too early.

**Fix:** For each bond where `issue_date > 2024-03-01` and `first_valid_index < issue_date`, compute `shift_amount = searchsorted(index, issue_date)` and shift the entire price column down by that many rows. The top rows are filled with NaN. Applied identically to Mid, Bid, and Ask.

> **Note:** The shift truncates the last `shift_amount` rows of the series. These correspond to dates beyond the analysis window (after 2026-02-26) and are correctly excluded.

| | Batch 1 | Batch 2 |
|---|---|---|
| Bonds shifted | 33 | ~19 |
| Metadata source | `Bonds_V2.Date` (issue date) | `Reduced_List.Issue Date` |

---

### Step 6 — MID/BID/ASK consistency and inverted spread correction
**Batch 1 only** (Batch 2's raw file has all three series pre-verified).

Bloomberg derives `ASK = 2 × MID − BID`. The pipeline:

1. **Verifies** the identity holds (max residual checked across all cells).
2. **Detects inverted spreads** — dates where `MID < BID`, which would produce `ASK < BID` (economically impossible).
3. **Imputes** rather than nulling: for each affected bond, the median half-spread `(MID − BID) / 2` is computed from its clean period (all dates where `MID ≥ BID`). On inverted days: `MID_imputed = BID + median_half_spread`.
4. **Recomputes** `ASK = 2 × MID − BID` using the corrected MID.

> **⚠ Known exception — 4 bonds:** `BO1649512`, `BW4937361`, `ZH5526616`, `ZJ0581547` have intermittent inverted spreads from ~Oct 2025 onward (30–36 bad dates each). Root cause is a Bloomberg composite pricing timing issue where BID and MID feeds drifted out of sync. These are imputed using each bond's own pre-Oct 2025 median half-spread.

---

### Step 7 — Drop short-window bonds
**Both batches.**  
Bonds whose last valid MID price ends more than 20 calendar days before the final index date are flagged and dropped. These are bonds that matured, were called, or went dark within the sample window.

> **Batch 1 vs Batch 2 philosophy:** Batch 2 (Arthur's pipeline) used a stricter filter requiring every bond's last price to equal the final sheet date, dropping 237 → 104 bonds. Batch 1 relaxes this — bonds with early ends due to maturity or Bloomberg coverage gaps are kept where possible, reducing survivorship bias.

---

### Step 8 — Final universe

| | Batch 1 | Batch 2 |
|---|---|---|
| Input bonds | 237 | 173 |
| After dedup | ~230 | 147 |
| Final clean universe | ~190 | ~147 |
| Date range | 2024-03-01 → 2026-02-26 | 2024-03-01 → 2026-03-05 |

---

## 3. Credit Spread (G-Spread) Calculation

Both pipelines compute G-Spread identically. Two versions are produced.

### What is G-Spread?
G-Spread = bond YTM minus the interpolated US Treasury yield at the same remaining maturity, in basis points. It measures how much extra yield the bond offers over risk-free.

---

### Step A — US Treasury curve (FRED)
11 constant-maturity Treasury series downloaded from FRED: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y. Forward-filled over weekends and holidays. Converted from percent to decimal.

---

### Step B — YTM solver (Bond Equivalent Yield convention)
For each bond × date where a price exists:

1. Generate all future coupon dates by stepping back from maturity by `12/frequency` months.
2. Build cash flows: coupon payment at each date, face value (100) returned at maturity.
3. Convert dates to time-in-years from valuation date.
4. Solve for `y` (BEY) such that:

$$\text{Price} = \sum_i \frac{CF_i}{\left(1 + \frac{y}{2}\right)^{2t_i}}$$

   using Brent's method. YTM is in the same BEY convention as FRED Treasury yields — directly comparable.

5. Linearly interpolate the Treasury curve at the bond's remaining maturity (years to maturity, capped to the 1M–30Y range).

6. **G-Spread (bps)** = `(YTM − Treasury yield) × 10,000`

---

### Version 1 — Clean price G-Spread (`Credit_Spread_bps`)
YTM is solved using Bloomberg's quoted **clean price** directly. Simple and fast, but produces a sawtooth pattern in the spread time series around coupon dates because the clean price drops by the coupon amount on ex-dividend days.

---

### Version 2 — Dirty price G-Spread (`Credit_Spread_Dirty`)
YTM is solved using **dirty price = clean price + accrued interest**.

Accrued interest formula:
$$AI = \frac{\text{Coupon payment}}{1} \times \frac{\text{Days since last coupon}}{\text{Days in coupon period}}$$

The last coupon date is found by stepping back from maturity in `12/frequency`-month intervals until crossing the valuation date. Day count is **actual/actual** in Batch 1 and **30/360** in Batch 2.

Using dirty price removes the sawtooth — the dirty price is smooth across coupon dates because the accrued interest offsets the clean price drop. **Recommended for time-series analysis.**

> **Difference between batches — day count convention:**
> - Batch 1 (`bloomberg_first_batch_cleaning`): actual/actual
> - Batch 2 (`bond_analysis`): 30/360 (US corporate bond market standard)
>
> For most bonds the numerical difference is < 1 bp. For precise attribution work, 30/360 is more consistent with market convention.

---

## 4. Output Sheets

| Sheet | Content | Both batches? |
|---|---|---|
| `Mid_Clean` | Cleaned daily mid prices | ✓ |
| `Bid_Clean` | Cleaned daily bid prices | ✓ |
| `Ask_Clean` | Recomputed ASK = 2×MID−BID | ✓ |
| `Credit_Spread_bps` | G-Spread from clean price (bps) | ✓ |
| `Credit_Spread_Dirty` | G-Spread from dirty price (bps) — preferred | ✓ |
| `Treasury_Curve` | FRED daily Treasury rates used | ✓ |
| `BidAsk_Spread_bps` | (Ask−Bid)/Mid × 10,000 | Batch 2 only |
| `Rolling_Vol_21d` | 21-day annualized rolling volatility | Batch 2 only |
