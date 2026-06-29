# Size of the Prize — Results Summary

---

## 1. Trade Quality (Cell 25 & 26)

- **211 active arcs**, $4.7B total notional on a $500M book (9.5× turnover over 2 years)
- **95.3% of arcs are profitable** — the LP almost never makes a losing trade
- **Median profit: 67.5 bps/dollar** — roughly equivalent to earning a full spread on every arc from timing alone
- **Mean hold duration: 76 days** — the optimizer is making multi-month strategic bets, not high-frequency flips

---

## 2. Hold Duration is the Strongest Predictor of Profit (r = 0.789)

Longer holds are more profitable. The primary lever is not rapid round-trips but strategic positioning over months. This is relevant for implementation: a realistic dynamic strategy should target medium-term holds, not intraday or weekly rotations.

---

## 3. Trading Intensity — Threshold Effect, Not Linear (Cell 30)

- Pearson correlation between weekly trade count and yield volatility: **r = 0.044** (near zero)
- But **9 out of 10 of the heaviest trading weeks fall in high-volatility periods**

The LP does not trade proportionally more as volatility increases — it barely trades during normal regimes and fires concentrated bursts only when volatility is extreme. The strategy is **volatility-triggered, not volatility-proportional**. Pearson r misses this entirely; the 9/10 overlap is the right number to cite.

---

## 4. IMR and NII are Anti-Correlated — Hypothesis Confirmed (Cell 33)

Monthly NII accrual vs. IMR realization: **r = −0.411**

Selling a bond generates IMR but simultaneously terminates its carry. The two income sources are structurally in tension: holding earns NII, selling generates IMR, but doing one reduces the other. Dynamic trading does not simply add IMR on top of carry — **it partially substitutes for it**. This should be highlighted in the paper.

---

## 5. Outstanding Issues

| Issue | Status | Action needed |
|---|---|---|
| BigQuery issuer name lookup | ❌ 404 error | Check `DATASET_ID` and region in `.env` — dataset not found at `insurance-backed-securities:fabn` in location `US` |
| Pandas `resample('M')` deprecation warning | ⚠️ FutureWarning | Replace both `.resample('M')` with `.resample('ME')` in Cell 33 |
| Pipeline `Issuer_name` field | ⏳ Pending | Add `Issuer_name` to `Agg_Fixed_Field` SELECT in `fabn_pipeline.py`, then regenerate `prize_panels.npz` |
