"""
Bond service — per-CUSIP lookups over the full bond collateral universe.

Reads the same cached pipeline used by optimizer_service.py (no Gurobi solve
required), so a bond lookup is cheap whenever the pipeline for that date is
already warm (which it usually is, since App.tsx runs /api/optimize on load
and on every date change).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services import optimizer_service


def _clean_str(v) -> str:
    return str(v).strip() if pd.notna(v) else ""


def list_bonds(date: str) -> list[dict]:
    """Lightweight picker rows for every CUSIP in the universe for `date`."""
    pipeline = optimizer_service.get_pipeline(date)
    fixed_idx = pipeline["fixed"].set_index("CUSIP")
    CUSIPS, durs, spread, theta = pipeline["CUSIPS"], pipeline["durs"], pipeline["spread"], pipeline["theta"]

    rows: list[dict] = []
    for i, cusip in enumerate(CUSIPS):
        r = fixed_idx.loc[cusip]
        rows.append({
            "cusip":          cusip,
            "sector":         _clean_str(r["sector"]),
            "rating_sp":      _clean_str(r["rating_sp"]),
            "rating_moodys":  _clean_str(r["rating_moodys"]),
            "coupon_pct":     round(float(r["coupon"]), 4) if pd.notna(r["coupon"]) else None,
            "maturity":       str(r["maturity"])[:10] if pd.notna(r["maturity"]) else "",
            "par_amount":     round(float(r["amt_out"]), 2) if pd.notna(r["amt_out"]) else None,
            "duration":       round(float(durs[i]), 4),
            "spread_bps":     round(float(spread[i] * 1e4), 2),
            "rbc_factor_pct": round(float(theta[i] * 100), 4),
        })
    rows.sort(key=lambda r: r["cusip"])
    return rows


def get_bond_detail(date: str, cusip: str) -> dict | None:
    """Full pipeline-level detail for one CUSIP, or None if it's not in the
    universe for `date`. Does not include optimizer-derived fields (h_opt,
    weight, reduced_cost, reservation price) — those require a live Gurobi
    solve and are cross-referenced by the frontend from the OptimizerResult
    it already has, rather than triggering a second solve here."""
    pipeline = optimizer_service.get_pipeline(date)
    CUSIPS = pipeline["CUSIPS"]
    if cusip not in CUSIPS:
        return None
    i = CUSIPS.index(cusip)
    pipeline = optimizer_service.apply_portfolio_overrides(pipeline)

    fixed_row = pipeline["fixed"].set_index("CUSIP").loc[cusip]
    qtr_idx   = pipeline["qtr_idx"]
    qtr_cf    = pipeline["qtr_bond_cf"][:, i] * 100.0  # back to per-$100-face

    cashflow_schedule = [
        {"period": str(qtr_idx[q]), "cf_per_100_face": round(float(qtr_cf[q]), 4)}
        for q in range(len(qtr_idx)) if abs(qtr_cf[q]) > 1e-9
    ]

    bid = pipeline.get("bid")
    ask = pipeline.get("ask")
    bid_price = float(bid[i]) if bid is not None and not np.isnan(bid[i]) else None
    ask_price = float(ask[i]) if ask is not None and not np.isnan(ask[i]) else None

    return {
        "cusip":             cusip,
        "date":              date,
        "sector":            _clean_str(fixed_row["sector"]),
        "rating_sp":         _clean_str(fixed_row["rating_sp"]),
        "rating_moodys":     _clean_str(fixed_row["rating_moodys"]),
        "coupon_pct":        round(float(fixed_row["coupon"]), 4) if pd.notna(fixed_row["coupon"]) else None,
        "cpn_freq":          float(fixed_row["cpn_freq"]) if pd.notna(fixed_row["cpn_freq"]) else None,
        "maturity":          str(fixed_row["maturity"])[:10] if pd.notna(fixed_row["maturity"]) else "",
        "par_amount":        round(float(fixed_row["amt_out"]), 2) if pd.notna(fixed_row["amt_out"]) else None,
        "duration":          round(float(pipeline["durs"][i]), 4),
        "spread_bps":        round(float(pipeline["spread"][i] * 1e4), 2),
        "rbc_factor_pct":    round(float(pipeline["theta"][i] * 100), 4),
        "mid_price":         round(float(pipeline["price"][i]), 4),
        "bid_price":         round(bid_price, 4) if bid_price is not None else None,
        "ask_price":         round(ask_price, 4) if ask_price is not None else None,
        "bid_ask_cost_bps":  round(float(pipeline["tau"][i]) * 1e4, 2),
        "book_yield_pct":    round(float(pipeline["book_yield"][i]) * 100, 4),
        "coupon_income_pct": round(float(pipeline["coupon_inc"][i]) * 100, 4),
        "amort_income_pct":  round(float(pipeline["amort_inc"][i]) * 100, 4),
        "h_curr":            round(float(pipeline["h_curr"][i]), 2),
        "cashflow_schedule": cashflow_schedule,
    }
