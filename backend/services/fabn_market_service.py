"""
FABN market history service — loads historical FABN price/yield/spread data
from FABN.xlsx (Bloomberg export) and pairs it with a hardcoded Prime Rate
step schedule for the "FABN vs Market" story chart.

The "BB Fixed" sheet holds resolved values; the "BB" sheet still contains
live Bloomberg formulas (#NAME? errors outside a Bloomberg Terminal) and
must not be used.
"""

from __future__ import annotations

import os
from bisect import bisect_right

import pandas as pd

PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FABN_XLSX_PATH = os.path.join(PROJECT_ROOT, 'FABN.xlsx')

# (effective date, prime rate %) — sorted ascending
PRIME_RATE_SCHEDULE: list[tuple[str, float]] = [
    ("2023-02-01", 7.75),
    ("2023-03-22", 8.00),
    ("2023-05-03", 8.25),
    ("2023-07-26", 8.50),
    ("2024-09-18", 8.00),
    ("2024-11-07", 7.75),
    ("2024-12-18", 7.50),
    ("2025-09-17", 7.25),
    ("2025-10-29", 7.00),
    ("2025-12-10", 6.75),
]
_PRIME_DATES = [pd.Timestamp(d) for d, _ in PRIME_RATE_SCHEDULE]
_PRIME_RATES = [r for _, r in PRIME_RATE_SCHEDULE]


def _prime_rate_on(date: pd.Timestamp) -> float | None:
    idx = bisect_right(_PRIME_DATES, date) - 1
    if idx < 0:
        return None
    return _PRIME_RATES[idx]


_history_cache: list[dict] | None = None


def _load_history() -> list[dict]:
    df = pd.read_excel(FABN_XLSX_PATH, sheet_name="BB Fixed", header=None)

    # Row 11 (0-indexed 10) is the header row; data starts at row 12 (0-indexed 11).
    # Column indices (0-indexed): 2/3 = Date/PX_LAST, 5/6 = Date/YLD_YTM_MID,
    # 11/12 = Date/BLP_SPRD_TO_BENCH_MID.
    data = df.iloc[11:]

    ytm = data[[5, 6]].dropna()
    ytm.columns = ["date", "fabn_ytm"]

    spread = data[[11, 12]].dropna()
    spread.columns = ["date", "spread_bps"]

    merged = pd.merge(ytm, spread, on="date", how="inner").sort_values("date")
    merged["treasury_ytm"] = merged["fabn_ytm"] - merged["spread_bps"] / 100.0
    merged["prime_rate"] = merged["date"].apply(_prime_rate_on)
    merged = merged.dropna(subset=["prime_rate"])

    return [
        {
            "date":         row.date.strftime("%Y-%m-%d"),
            "fabn_ytm":     round(float(row.fabn_ytm), 4),
            "treasury_ytm": round(float(row.treasury_ytm), 4),
            "spread_bps":   round(float(row.spread_bps), 2),
            "prime_rate":   float(row.prime_rate),
        }
        for row in merged.itertuples()
    ]


def get_history() -> list[dict]:
    global _history_cache
    if _history_cache is None:
        _history_cache = _load_history()
    return _history_cache
