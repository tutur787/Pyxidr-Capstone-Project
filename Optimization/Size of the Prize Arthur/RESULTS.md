# Size of the Prize — Results

Perfect-foresight upper bound on cumulative net statutory income (SAP NII + IMR-recognized trading
gains, net of bid-ask/2), full 303-bond universe, 2024-03-01 → 2026-02-26 (~2y), Gurobi (WLS).
Baselines: backtest **static $27.76M**, realistic tuned-dynamic **~$31M** (placeholder — update with
your run). All figures are cumulative net statutory income over the window.

## Headline (monthly grid — the defensible number)

| Run | Windowed | Full-IMR | Carry | Capital | Trading cost | IMR (window) |
|---|---|---|---|---|---|---|
| Foresight **STATIC** (floor) | $29.05M | $29.05M | $32.66M | −$2.86M | −$0.76M | $0 |
| Foresight **DYNAMIC** (prize) | **$41.99M** | $62.26M | $32.93M | −$2.42M | −$4.80M | +$16.27M |

- **Prize gap (dynamic − static) = $12.94M (+44.6%)** — value added purely by trading.
- **Head-room vs realistic dynamic (~$31M) = ~$11M (+35%)** — the "size of the prize."
- Foresight-static ($29.05M) ≈ backtest static ($27.76M): the arc model reproduces the trusted engine.
- Facility / PV-shortfall ON: prize unchanged ($41.95M), borrowing cost $0 → **liquidity is not binding.**

## Where the prize comes from (the key insight)

**Carry is essentially identical** static vs dynamic (~$32.9M). The entire dynamic edge is **realized
rate-driven gains harvested by trading (IMR): +$16.3M windowed**, bought with ~$4M of extra turnover.
So the prize is **rate-move rotation timing**, not bond/yield selection — a realistic strategy should
chase rate/curve signals with disciplined turnover, not bond-picking (the static book already owns the
carry). IMR amortizes gains over remaining life, so a 2-year window understates them: windowed $42M vs
fully-recognized $62M.

## Grid-sensitivity sweep (does NOT plateau — it keeps rising)

| grid | nodes | windowed | full-IMR |
|---|---|---|---|
| quarterly | 9 | $36.2M | $45.4M |
| monthly | 25 | $42.0M | $62.3M |
| biweekly | 51 | $47.1M | $80.6M |
| weekly | 101 | $54.0M | $106.3M |

Finer grid → more price wiggles to harvest → bigger number, with **no plateau**. So monthly is a
*conservative* lower estimate; the finer points are increasingly optimistic (no market-impact cost).

## DAILY × all bonds — the extreme ceiling (upper-bound ARTIFACT)

True unrestricted daily is intractable (~37M arcs); approximated with a max-hold cap `L` (flip within
`L` trading days or hold). **These are not realistic targets** — see why below.

| run | arcs | windowed | full-IMR | trading cost | traded notional |
|---|---|---|---|---|---|
| daily, L=10 | 1.61M | **$96.3M** | $248.3M | −$40.3M | **$52,082M** |
| daily, L=21 | (run yourself) | — | — | — | — |
| daily, L=42 | (run yourself) | — | — | — | — |

**Read carefully:** at L=10 the model trades **~$52 billion on a $500M book (~100× turnover)**, paying
$40M of bid-ask to harvest $111M of windowed IMR — and our model charges **only bid-ask/2 with zero
market impact**. No insurer can trade 100× its assets; real market impact would erode most of this.
Carry even *falls* to $27.7M (the book is flipping, not holding carry). The daily figure measures how
far the unconstrained-foresight / no-impact assumptions can be pushed, **not** business upside.

## Bottom line for the business case

- **Quote ~$42M (monthly) to ~$54M (weekly) windowed** as the prize; head-room over realistic dynamic
  is **~$11–23M (+35–75%)**. There *is* tradeable upside → the problem is worth pursuing.
- The upside is **rate-rotation timing (IMR), funded by turnover** — so the realistic strategy is
  **low-turnover, signal-driven rebalancing**, not daily churn.
- The daily/L-sweep numbers ($96M+) are **artifacts** that prove the apparent extra upside beyond
  weekly is a trading-cost / market-impact mirage. The natural next modeling step is a **market-impact
  / capacity cost** so the prize reflects realistic trade sizes.

## Honest limitations

Perfect foresight is unattainable (ceiling, not strategy). No market impact (bid-ask/2, infinite
liquidity) → optimistic, especially for fine grids. Clean prices. AVR out of scope (rate-driven IMR
only). Coarse grid under-states; daily over-states. Quarterly facility timing as in the backtest.
