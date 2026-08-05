# Size of the Prize

A perfect-foresight (clairvoyant) **upper bound** on cumulative SAP / NII for the FABN portfolio:
*if we knew the next two years of prices perfectly, what is the most we could earn by trading?* The
gap between this ceiling and the realistic dynamic backtest is the **size of the prize** — it tells us
whether smarter trading has enough upside to be worth building.

See **`prize_theory.md`** for the full rationale, formulation, and how to read the number.

## Files

| File | Role |
|---|---|
| `prize_foresight.py` | Pure, unit-tested arc model: `arc_economics` (per-dollar profit of one trade), `build_arcs` (enumerate the time-expanded network), `solve_prize` (the Gurobi LP). Reuses `fabn_finance` for all math. |
| `FABN_Size_of_Prize.ipynb` | Driver: loads the shared precompute panels, builds the grid, solves, and reports the prize, its carry/IMR/cost decomposition, a grid-sensitivity sweep, and the gap vs static / tuned dynamic. |
| `prize_theory.md` | Theory & business framing. |
| `RESULTS.md` | The computed numbers + interpretation (monthly/weekly/daily, decomposition, caveats). |
| `tests/test_prize_foresight.py` | pytest suite (single-arc identity vs the backtest accrual, IMR-window conservation, hold-to-maturity, foresight-beats-static, flat-path no-edge, budget feasibility). |

**Headline result:** windowed prize ~**$42M (monthly)**–**$54M (weekly)** vs realistic dynamic ~$31M —
a **~$11–23M (+35–75%)** prize, driven almost entirely by **rate-rotation trading gains (IMR)**, not
carry. See `RESULTS.md`. The daily/full-universe ceiling ($96M+ at ~100× turnover) is an upper-bound
**artifact** with no market-impact cost — not a target.

## How it works (one paragraph)

Perfect foresight makes each possible trade `(bond, buy date, sell/close date)` an **arc** with a
*constant* per-dollar profit = locked carry (net of capital) + the IMR-recognized rate-driven gain −
bid-ask/2 on each leg. We solve a linear program over these arcs that conserves **book value** (a
dollar freed when an arc closes can only then fund a new buy — so realized gains never inflate
redeployable principal), under the same soft duration band, issuer cap, and facility/shortfall
constraints as the optimizer. The result is the true clairvoyant ceiling.

## Running

```bash
# from the Optimization/ folder
pytest "Size of the Prize/tests/" -v          # fast; LP tests skip if Gurobi has no license

# then, with Gurobi WLS + GCP ADC auth (same as the other notebooks):
#   1. run FABN_Optimizer_SAP_Backtest.ipynb through its precompute + the export_panels() cell
#      -> writes Size of the Prize/prize_panels.npz
#   2. run FABN_Size_of_Prize.ipynb end-to-end
```

The notebook **asserts** `prize ≥ foresight-static` and `prize ≥ tuned dynamic` (it is an upper
bound). A violation means a modeling bug, not a result.

### Grid cadence & the `max_hold_nodes` knob
The sweep runs quarterly → weekly. **Daily × full universe** is intractable as a pure arc model
(~37M arcs), so the optional daily cell uses `build_arcs(..., max_hold_nodes=L)`: a bond is flipped
within `L` trading days or held to the terminal close, turning arc growth from `O(N·P²)` into
`O(N·P·L)`. Larger `L` → closer to unrestricted daily → bigger (and less realistic) number. Each `L`
is weekly-scale or heavier.

## Honest limitations

Ceiling, not a strategy. No market impact (bid-ask/2 only, so "trade a lot" is optimistic). Coarse
grid under-states slightly. Clean prices; AVR out of scope (rate-driven IMR only). See `prize_theory.md`.
